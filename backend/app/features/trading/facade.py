"""주문 실행 파사드.

trading/tasks.py의 Celery task는 이 파사드 하나만 호출한다 — 리스크 재확인, 멱등성 체크,
브로커 API 호출, 주문/포지션 상태 갱신이라는 여러 단계를 하나의 유스케이스로 묶어
호출부(Celery task)가 각 컴포넌트를 직접 조립할 필요가 없게 한다.

파사드 자신은 SQLAlchemy도, Redis도, 특정 브로커도 모른다 — 생성자로 주입받은
포트(OrderRepository, PositionRepository, RiskGuard, BrokerAdapter)에만 의존한다.

주문 상태와 재전송 규칙 (중복 주문 방지의 핵심):
- PENDING: 기록만 됐고 브로커에 접수되지 않은 것이 확실함. 같은 client_order_id로 다시
  보내도 안전하다 (Celery 재시도).
- UNKNOWN(미확정): 브로커로 보내기 직전에 먼저 이 상태로 저장한다(write-ahead). 응답을
  받으면 결과 상태로 바꾸고, 거부/전송 전 실패가 확실하면 PENDING으로 되돌린다. 응답이
  유실됐거나(타임아웃 등) 워커가 그 사이에 죽으면 UNKNOWN으로 남는다. UNKNOWN 주문은
  절대 자동으로 재전송하지 않고, reconcile_unknown_order()가 브로커 주문 조회로 확정한다.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.exceptions import BrokerAPIError, OrderOutcomeUnknownError, RiskLimitExceededError
from app.core.logging import get_logger
from app.features.broker.base import BrokerAdapter, OrderRequest
from app.features.notification.service import NotificationService
from app.features.risk.guard import RiskGuard
from app.features.trading.models import Order, OrderStatus, Position
from app.features.trading.ports import OrderRepository, PositionRepository

logger = get_logger(__name__)

# 전송 중인 주문(UNKNOWN으로 선기록된 직후)을 대사가 건드리지 않도록 이 시간이 지난 것만 대사한다.
# 브로커 HTTP 타임아웃(5초)보다 충분히 길게 잡는다.
RECONCILE_MIN_AGE = timedelta(seconds=30)
# 브로커 조회에서 못 찾아도, 접수 기록이 조회에 늦게 반영될 수 있어 이 시간이 지나기 전에는
# "접수 안 됨"으로 확정하지 않는다.
RECONCILE_NOT_FOUND_GRACE = timedelta(minutes=2)
# 서버와 브로커 사이 시계 차이를 감안해 조회 시작 시각을 조금 앞당긴다.
_CLOCK_SKEW = timedelta(seconds=30)


def _utcnow() -> datetime:
    """Order.created_at/updated_at과 같은 naive UTC (models.py가 datetime.utcnow를 쓴다)."""
    return datetime.now(UTC).replace(tzinfo=None)


class OrderExecutionFacade:
    def __init__(
        self,
        orders: OrderRepository,
        positions: PositionRepository,
        risk_guard: RiskGuard,
        broker: BrokerAdapter,
        notifier: NotificationService | None = None,
    ) -> None:
        self._orders = orders
        self._positions = positions
        self._risk_guard = risk_guard
        self._broker = broker
        self._notifier = notifier

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
        넘기는 것을 권장한다 — Celery 재시도 시에도 동일 키를 유지해야 같은 주문 레코드를
        다시 찾을 수 있기 때문이다. 넘기지 않으면 이 호출 한정으로 새로 발급한다
        (재시도 없는 단발성 호출에서만 안전).

        결과가 UNKNOWN이면 예외 없이 그 주문을 돌려준다 (Celery가 재시도하지 않게).
        """
        client_order_id = client_order_id or str(uuid.uuid4())

        # 1. 멱등성 체크 — 재시도로 같은 client_order_id가 다시 들어와도, 브로커에 접수되지
        #    않은 것이 확실한 PENDING일 때만 다시 보낸다. UNKNOWN은 대사 전까지 재전송 금지.
        existing = await self._orders.get_by_client_order_id(client_order_id)
        if existing is not None and existing.status != OrderStatus.PENDING:
            logger.info(
                "order already processed (%s), skipping resubmission: %s",
                existing.status,
                client_order_id,
            )
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

        # 4. 전송 직전에 UNKNOWN으로 저장한다. 이 뒤에 워커가 죽어도 "보냈을 수도 있는 주문"으로
        #    남아 재전송되지 않고 대사 대상이 된다.
        order.status = OrderStatus.UNKNOWN
        order = await self._orders.update(order)

        try:
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
        except OrderOutcomeUnknownError as exc:
            # 응답 유실: 접수됐는지 모른다. 다시 보내지 않고 UNKNOWN으로 남겨 대사에 맡긴다.
            logger.error("order outcome unknown, left for reconciliation: %s (%s)", client_order_id, exc)
            await self._notify(
                "order_state_unknown",
                f"{symbol} {side} {quantity} 주문의 접수 여부를 확인하지 못했습니다. "
                f"브로커 주문 조회로 확인할 때까지 이 종목은 새 주문을 내지 않습니다. ({exc})",
            )
            return order
        except BrokerAPIError:
            # 브로커가 거부했거나 요청이 나가기 전에 실패했다 — 접수되지 않은 것이 확실하므로
            # PENDING으로 되돌려 Celery 재시도가 다시 보낼 수 있게 한다.
            order.status = OrderStatus.PENDING
            await self._orders.update(order)
            raise
        except (RiskLimitExceededError, NotImplementedError):
            # 어댑터가 전송 전에 거절했다 (최소 주문 금액 미달, paper 모드 Upbit 등).
            # 재시도해도 해결되지 않으니 거부로 확정한다.
            order.status = OrderStatus.REJECTED
            await self._orders.update(order)
            raise
        # 그 밖의 예외(응답 처리 중 버그 등)는 UNKNOWN을 그대로 두고 전파한다 — 안전한 쪽.

        # 5. 결과 반영
        order.broker_order_id = result.broker_order_id
        order.status = OrderStatus(result.status)
        order.filled_quantity = result.filled_quantity
        order.avg_fill_price = result.avg_fill_price
        order = await self._orders.update(order)

        # 6. 체결분만큼 포지션 갱신 + 매도 체결이면 실현손익을 일일 손실 한도 추적에 반영
        if result.filled_quantity > 0 and result.avg_fill_price is not None:
            await self._settle_fill(order, filled_quantity=result.filled_quantity, fill_price=result.avg_fill_price)

        return order

    async def reconcile_unknown_order(self, order: Order, *, now: datetime | None = None) -> Order:
        """UNKNOWN 주문을 브로커 주문 조회로 확정한다. 재전송은 하지 않는다.

        - 브로커에서 찾음: broker_order_id와 상태/체결을 반영한다. 이후에는 일반 체결 폴링 대상이다.
        - 못 찾음 + RECONCILE_NOT_FOUND_GRACE 경과: REJECTED(접수 안 됨)로 확정한다. 그 뒤
          전략 러너가 다음 신호에서 새 주문을 낼 수 있다. 이것이 "대사 후 재시도" 경로다.
        - 판단 불가(조회 실패, 후보 여러 건, 대사 미지원 어댑터): UNKNOWN을 유지한다.
          해당 종목은 계속 막히므로 사람이 확인해야 한다.
        """
        now = now or _utcnow()
        sent_at = order.updated_at or order.created_at or now
        if now - sent_at < RECONCILE_MIN_AGE:
            return order  # 아직 전송 중일 수 있다

        search_from = (order.created_at or sent_at) - _CLOCK_SKEW
        known_ids = await self._orders.list_broker_order_ids(
            order.symbol, since=search_from - timedelta(hours=1)
        )
        request = OrderRequest(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.price,
            client_order_id=order.client_order_id,
        )
        try:
            found = await self._broker.find_order(
                request,
                placed_after=search_from.replace(tzinfo=UTC),
                exclude_broker_order_ids=frozenset(known_ids),
            )
        except NotImplementedError:
            logger.error(
                "broker %s cannot reconcile orders; order %s needs manual check",
                self._broker.asset_class,
                order.client_order_id,
            )
            return order
        except (BrokerAPIError, OrderOutcomeUnknownError) as exc:
            logger.warning("reconciliation inconclusive for %s: %s", order.client_order_id, exc)
            return order

        if found is None:
            if now - sent_at < RECONCILE_NOT_FOUND_GRACE:
                return order
            logger.warning("order %s not found at broker; marking rejected", order.client_order_id)
            order.status = OrderStatus.REJECTED
            return await self._orders.update(order)

        logger.info(
            "reconciled order %s -> %s (%s)", order.client_order_id, found.broker_order_id, found.status
        )
        order.broker_order_id = found.broker_order_id
        return await self.apply_broker_fill_update(
            order,
            status=OrderStatus(found.status),
            filled_quantity=found.filled_quantity,
            avg_fill_price=found.avg_fill_price,
        )

    async def cancel_open_order(self, order: Order) -> Order:
        """미체결 주문 취소 (kill switch 발동 시 사용). 취소 직후 체결 상태를 다시 조회해,
        취소 요청 직전에 체결된 수량도 포지션/손익에 빠짐없이 반영한다.
        """
        await self._broker.cancel_order(order.broker_order_id)
        latest = await self._broker.get_order_fill_status(order.broker_order_id)
        filled = max(latest.filled_quantity, order.filled_quantity)
        status = OrderStatus.FILLED if latest.status == "filled" else OrderStatus.CANCELLED
        return await self.apply_broker_fill_update(
            order,
            status=status,
            filled_quantity=filled,
            avg_fill_price=latest.avg_fill_price or order.avg_fill_price,
        )

    async def apply_broker_fill_update(
        self,
        order: Order,
        *,
        status: OrderStatus,
        filled_quantity: float,
        avg_fill_price: float | None,
    ) -> Order:
        """체결 확인 폴링(trading/tasks.py의 poll_pending_order_fills)이 새로 알아낸 체결
        정보를 기존 주문에 반영한다.

        place_order 응답이 접수 확인뿐인 브로커(KIS)는 submit_order() 안에서 포지션을
        갱신하지 못하므로, 이 메서드가 그 뒷단을 대신한다. order.filled_quantity에는
        지금까지 이미 반영된 누적 체결 수량이 들어있다 — 이번 조회로 알아낸
        filled_quantity와의 차이(신규 체결분)만 포지션/손익에 반영해서, 폴링 주기마다
        같은 체결을 중복 반영하지 않는다.
        """
        previously_filled = order.filled_quantity or 0.0
        newly_filled = filled_quantity - previously_filled

        order.status = status
        order.filled_quantity = filled_quantity
        order.avg_fill_price = avg_fill_price
        order = await self._orders.update(order)

        if newly_filled > 0 and avg_fill_price is not None:
            await self._settle_fill(order, filled_quantity=newly_filled, fill_price=avg_fill_price)

        return order

    async def poll_and_apply_fill(self, order: Order) -> Order:
        """미체결 주문의 체결 여부를 브로커에 확인하고, 변화가 있으면 반영한다.
        trading/tasks.py의 poll_pending_order_fills가 미체결 주문마다 호출한다.
        변화가 없으면(아직 그대로 미체결) order를 그대로 반환한다.
        """
        result = await self._broker.get_order_fill_status(order.broker_order_id)
        if result.filled_quantity == order.filled_quantity and OrderStatus(result.status) == order.status:
            return order

        return await self.apply_broker_fill_update(
            order,
            status=OrderStatus(result.status),
            filled_quantity=result.filled_quantity,
            avg_fill_price=result.avg_fill_price,
        )

    async def _notify(self, event_type: str, message: str) -> None:
        if self._notifier is None:
            return
        try:
            await self._notifier.notify(event_type, message)
        except Exception:  # 알림 실패가 주문 상태 기록을 망치면 안 된다
            logger.exception("failed to send %s notification", event_type)

    async def _settle_fill(self, order: Order, *, filled_quantity: float, fill_price: float) -> None:
        """체결 수량만큼 포지션을 갱신하고, 매도 체결이면 실현손익을 리스크 가드(일일 손실
        한도 서킷브레이커)에 반영한다. submit_order()의 즉시 체결 응답 처리와
        apply_broker_fill_update()의 폴링 결과 처리가 이 메서드를 공유한다.
        """
        realized_pnl = await self._apply_fill_to_position(
            asset_class=order.asset_class,
            symbol=order.symbol,
            side=order.side,
            filled_quantity=filled_quantity,
            fill_price=fill_price,
        )
        if order.side == "sell" and realized_pnl != 0.0:
            await self._risk_guard.record_fill_pnl(realized_pnl)

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
