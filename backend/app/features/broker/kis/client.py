"""한국투자증권 REST 주문/계좌 어댑터.

paper(모의투자)와 live(실전투자)는 base_url, app_key/secret, TR_ID 접두어가 전부 달라
동일 클래스를 credential 세트만 바꿔 재사용한다. live 여부는 반드시 factory.py를 통해서만
결정되며 이 클래스 스스로 TRADING_MODE를 읽지 않는다 (실수 방지).

주문번호(ODNO)만으로는 정정취소가 불가능하고 한국거래소전송주문조직번호
(KRX_FWDG_ORD_ORGNO)가 함께 필요하다 — 우리 공용 인터페이스(BrokerAdapter)는
broker_order_id 하나만 주고받으므로, place_order가 "{조직번호}:{주문번호}" 형태로
합쳐 반환하고 cancel_order에서 다시 분리한다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.core.exceptions import BrokerAPIError
from app.core.logging import get_logger
from app.features.broker.base import AssetClass, Balance, BrokerAdapter, OrderRequest, OrderResult
from app.features.broker.kis.auth import KISAuth, KISCredentials

logger = get_logger(__name__)

_ORDER_DVSN_LIMIT = "00"  # 지정가
_ORDER_DVSN_MARKET = "01"  # 시장가


class KISBrokerAdapter(BrokerAdapter):
    asset_class = AssetClass.KR_STOCK

    def __init__(self, live: bool) -> None:
        settings = get_settings()
        self._live = live
        creds = KISCredentials(
            app_key=settings.kis_live_app_key if live else settings.kis_paper_app_key,
            app_secret=settings.kis_live_app_secret if live else settings.kis_paper_app_secret,
            base_url=settings.kis_live_base_url if live else settings.kis_paper_base_url,
            account_no=settings.kis_live_account_no if live else settings.kis_paper_account_no,
        )
        self._creds = creds
        self._auth = KISAuth(creds, mode_key="live" if live else "paper")
        self._http = httpx.AsyncClient(base_url=creds.base_url, timeout=5.0)

    def _account_parts(self) -> tuple[str, str]:
        """계좌번호는 "종합계좌번호(CANO, 8자리)-계좌상품코드(ACNT_PRDT_CD, 2자리)" 형식으로
        .env에 저장한다 (예: 12345678-01).
        """
        cano, _, prdt_cd = self._creds.account_no.partition("-")
        return cano, prdt_cd

    async def _headers(self, tr_id: str) -> dict:
        token = await self._auth.get_access_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self._creds.app_key,
            "appsecret": self._creds.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    async def place_order(self, order: OrderRequest) -> OrderResult:
        cano, prdt_cd = self._account_parts()
        if order.side == "buy":
            tr_id = "TTTC0802U" if self._live else "VTTC0802U"
        else:
            tr_id = "TTTC0801U" if self._live else "VTTC0801U"

        ord_dvsn = _ORDER_DVSN_LIMIT if order.order_type == "limit" else _ORDER_DVSN_MARKET
        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "PDNO": order.symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(int(order.quantity)),
            "ORD_UNPR": str(int(order.price)) if order.price is not None else "0",
        }

        response = await self._http.post(
            "/uapi/domestic-stock/v1/trading/order-cash",
            headers=await self._headers(tr_id),
            json=body,
        )
        data = response.json()

        if response.status_code != 200 or data.get("rt_cd") != "0":
            raise BrokerAPIError(f"KIS order-cash failed: {data.get('msg1', response.text)}")

        output = data["output"]
        broker_order_id = f"{output['KRX_FWDG_ORD_ORGNO']}:{output['ODNO']}"
        # order-cash 응답은 접수 확인일 뿐 체결 여부를 포함하지 않는다 — 체결 확인은
        # 별도의 주문체결조회(inquire-daily-ccld) TR이 필요 (TODO: 체결 폴링/웹소켓 체결통보 연동)
        return OrderResult(broker_order_id=broker_order_id, status="accepted", raw=data)

    async def cancel_order(self, broker_order_id: str) -> OrderResult:
        cano, prdt_cd = self._account_parts()
        org_no, _, odno = broker_order_id.partition(":")
        if not org_no or not odno:
            raise BrokerAPIError(
                f"invalid KIS broker_order_id (expected 'ORGNO:ODNO'): {broker_order_id}"
            )

        tr_id = "TTTC0803U" if self._live else "VTTC0803U"
        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "KRX_FWDG_ORD_ORGNO": org_no,
            "ORGN_ODNO": odno,
            "ORD_DVSN": _ORDER_DVSN_LIMIT,
            "RVSE_CNCL_DVSN_CD": "02",  # 01: 정정, 02: 취소
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",  # 잔량 전부 취소
        }

        response = await self._http.post(
            "/uapi/domestic-stock/v1/trading/order-rvsecncl",
            headers=await self._headers(tr_id),
            json=body,
        )
        data = response.json()

        if response.status_code != 200 or data.get("rt_cd") != "0":
            raise BrokerAPIError(f"KIS order-rvsecncl failed: {data.get('msg1', response.text)}")

        return OrderResult(broker_order_id=broker_order_id, status="cancelled", raw=data)

    async def get_order_fill_status(self, broker_order_id: str) -> OrderResult:
        """당일 주문체결조회(inquire-daily-ccld)로 미체결/체결 여부를 확인한다.

        ⚠️ place_order/cancel_order/get_balance와 달리, 이 TR(TTTC8001R/VTTC8001R)과
        응답 필드명(tot_ccld_qty, ord_qty, avg_prvs 등)은 KIS 공식 문서를 기준으로
        작성했고 실제 계좌로 검증하지 못했습니다. 실거래 투입 전 모의투자 계좌로
        반드시 먼저 확인해주세요.
        """
        cano, prdt_cd = self._account_parts()
        org_no, _, odno = broker_order_id.partition(":")
        if not org_no or not odno:
            raise BrokerAPIError(
                f"invalid KIS broker_order_id (expected 'ORGNO:ODNO'): {broker_order_id}"
            )

        tr_id = "TTTC8001R" if self._live else "VTTC8001R"
        today = datetime.now(tz=ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "INQR_STRT_DT": today,
            "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": "00",  # 00: 전체(매도+매수)
            "PDNO": "",
            "CCLD_DVSN": "00",  # 00: 전체(체결+미체결)
            "ORD_GNO_BRNO": org_no,
            "ODNO": odno,
            "INQR_DVSN": "00",
            "INQR_DVSN_1": "",
            "INQR_DVSN_3": "00",
            "EXCG_ID_DVSN_CD": "KRX",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        response = await self._http.get(
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            headers=await self._headers(tr_id),
            params=params,
        )
        data = response.json()

        if response.status_code != 200 or data.get("rt_cd") != "0":
            raise BrokerAPIError(f"KIS inquire-daily-ccld failed: {data.get('msg1', response.text)}")

        rows = data.get("output1", [])
        if not rows:
            # 이 시각 기준으로 아직 조회 결과가 없다 — 접수 상태 그대로 유지 (에러 아님)
            return OrderResult(broker_order_id=broker_order_id, status="accepted", raw=data)

        row = rows[0]
        filled_qty = float(row.get("tot_ccld_qty") or 0)
        ord_qty = float(row.get("ord_qty") or 0)
        avg_price_raw = row.get("avg_prvs")
        avg_price = float(avg_price_raw) if filled_qty > 0 and avg_price_raw else None

        if filled_qty <= 0:
            status = "accepted"
        elif ord_qty > 0 and filled_qty >= ord_qty:
            status = "filled"
        else:
            status = "partially_filled"

        return OrderResult(
            broker_order_id=broker_order_id,
            status=status,
            filled_quantity=filled_qty,
            avg_fill_price=avg_price,
            raw=data,
        )

    async def get_balance(self) -> Balance:
        cano, prdt_cd = self._account_parts()
        tr_id = "TTTC8434R" if self._live else "VTTC8434R"
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        response = await self._http.get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=await self._headers(tr_id),
            params=params,
        )
        data = response.json()

        if response.status_code != 200 or data.get("rt_cd") != "0":
            raise BrokerAPIError(f"KIS inquire-balance failed: {data.get('msg1', response.text)}")

        positions = {
            holding["pdno"]: float(holding["hldg_qty"])
            for holding in data.get("output1", [])
            if float(holding.get("hldg_qty", 0)) > 0
        }
        cash = float(data["output2"][0]["dnca_tot_amt"]) if data.get("output2") else 0.0
        return Balance(cash=cash, positions=positions)
