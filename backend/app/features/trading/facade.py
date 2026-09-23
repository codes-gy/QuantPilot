"""주문 실행 파사드.

trading/tasks.py의 Celery task는 이 파사드 하나만 호출한다 — 리스크 재확인, 멱등성 체크,
브로커 API 호출, 주문/포지션 상태 갱신이라는 여러 단계를 하나의 유스케이스로 묶어
호출부(Celery task)가 각 컴포넌트를 직접 조립할 필요가 없게 한다.

파사드 자신은 SQLAlchemy도, Redis도, 특정 브로커도 모른다 — 생성자로 주입받은
포트(OrderRepository, PositionRepository, RiskGuard, BrokerAdapter)에만 의존한다.
"""

import uuid

from app.core.logging import get_logger
from app.features.broker.base import BrokerAdapter, OrderRequest
from app.features.risk.guard import RiskGuard
from app.features.trading.models import Order, OrderStatus, Position
from app.features.trading.ports import OrderRepository, PositionRepository

logger = get_logger(__name__)


class OrderExecutionFacade:
    def __init__(
        self,
        orders: OrderRepository,
        positions: PositionRepository,
        risk_guard: RiskGuard,
        broker: BrokerAdapter,
    ) -> None:
        self._orders = orders
        self._positions = positions
        self._risk_guard = risk_guard
        self._broker = broker

    async def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        asset_class: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        client_order_id: str | None = None,
        strategy_id: int | None = None,
        trading_mode: str = "paper",
    ) -> Order:
        """신호 발생 -> 리스크 재확인 -> 주문 기록 -> 브로커 제출 -> 결과 반영까지 전 과정을 담당.

        client_order_id는 호출부(전략 러너 등 최초 신호 발생 지점)에서 미리 발급해
        넘기는 것을 권장한다 — Celery 재시도 시에도 동일 키를 유지해야 브로커 측
        중복 주문을 막을 수 있기 때문이다. 넘기지 않으면 이 호출 한정으로 새로 발급한다
        (재시도 없는 단발성 호출에서만 안전).
        """
        client_order_id = client_order_id or str(uuid.uuid4())

        # 1. 멱등성 체크 — 재시도로 같은 client_order_id가 다시 들어오면 새로 만들지 않는다.
        existing = await self._orders.get_by_client_order_id(client_order_id)
        if existing is not None and existing.status != OrderStatus.PENDING:
            logger.info("order already processed, skipping resubmission: %s", client_order_id)
            return existing

        # 2. 리스크 재확인 — kill switch는 신호 평가 시점과 실행 시점 사이에 바뀔 수 있어
        #    반드시 여기서 다시 체크한다 (KillSwitchEngagedError/RiskLimitExceededError는
        #    재시도 대상이 아니므로 호출부에서 autoretry_for에 포함시키지 않는다).
        await self._risk_guard.assert_can_trade()

        # 3. 주문 레코드 선기록 (status=pending) — 브로커 호출 전에 먼저 남겨야 감사 추적이 된다.
        order = existing or Order(
            client_order_id=client_order_id,
            strategy_id=strategy_id,
            asset_class=asset_class,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
            trading_mode=trading_mode,
        )
        if existing is None:
            order = await self._orders.add(order)

        # 4. 브로커 제출 (BrokerAPIError는 여기서 그대로 전파돼 Celery 재시도를 유도한다)
        result = await self._broker.place_order(
            OrderRequest(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                client_order_id=client_order_id,
            )
        )

        # 5. 결과 반영
        order.broker_order_id = result.broker_order_id
        order.status = OrderStatus(result.status)
        order.filled_quantity = result.filled_quantity
        order.avg_fill_price = result.avg_fill_price
        order = await self._orders.update(order)

        # 6. 체결분만큼 포지션 갱신 + 매도 체결이면 실현손익을 일일 손실 한도 추적에 반영
        if result.filled_quantity > 0 and result.avg_fill_price is not None:
            realized_pnl = await self._apply_fill_to_position(
                asset_class=asset_class,
                symbol=symbol,
                side=side,
                filled_quantity=result.filled_quantity,
                fill_price=result.avg_fill_price,
            )
            if side == "sell" and realized_pnl != 0.0:
                await self._risk_guard.record_fill_pnl(realized_pnl)

        return order

    async def _apply_fill_to_position(
        self, *, asset_class: str, symbol: str, side: str, filled_quantity: float, fill_price: float
    ) -> float:
        """포지션을 갱신하고, 매도 체결이면 실현손익(원)을 반환한다 (매수는 0.0)."""
        signed_qty = filled_quantity if side == "buy" else -filled_quantity
        existing = await self._positions.get_by_symbol(symbol)

        if existing is None:
            if signed_qty <= 0:
                # 보유 포지션이 없는데 매도 체결 — 데이터 불일치. 감사 로그만 남기고 무시.
                logger.warning("sell fill with no existing position: %s", symbol)
                return 0.0
            position = Position(
                asset_class=asset_class,
                symbol=symbol,
                quantity=signed_qty,
                avg_entry_price=fill_price,
            )
            await self._positions.upsert(position)
            return 0.0

        realized_pnl = 0.0
        new_quantity = existing.quantity + signed_qty
        if side == "buy":
            # 가중평균 진입가 재계산
            total_cost = existing.avg_entry_price * existing.quantity + fill_price * filled_quantity
            existing.avg_entry_price = total_cost / new_quantity if new_quantity > 0 else fill_price
        else:
            # 매도는 진입가를 바꾸지 않는다 — 남은 수량 기준 평단가는 그대로 유지.
            realized_pnl = (fill_price - existing.avg_entry_price) * filled_quantity
        existing.quantity = new_quantity
        await self._positions.upsert(existing)
        return realized_pnl
