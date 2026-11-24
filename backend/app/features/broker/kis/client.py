"""한국투자증권 REST 주문/계좌 어댑터.

paper(모의투자)와 live(실전투자)는 base_url, app_key/secret, TR_ID 접두어가 전부 달라
동일 클래스를 credential 세트만 바꿔 재사용한다. live 여부는 반드시 factory.py를 통해서만
결정되며 이 클래스 스스로 TRADING_MODE를 읽지 않는다 (실수 방지).

주문번호(ODNO)만으로는 정정취소가 불가능하고 한국거래소전송주문조직번호
(KRX_FWDG_ORD_ORGNO)가 함께 필요하다 — 우리 공용 인터페이스(BrokerAdapter)는
broker_order_id 하나만 주고받으므로, place_order가 "{조직번호}:{주문번호}" 형태로
합쳐 반환하고 cancel_order에서 다시 분리한다.

중복 주문 방지: KIS 국내주식 주문(order-cash)에는 Upbit의 identifier 같은 "클라이언트
주문번호" 필드가 없어서 우리 client_order_id를 브로커에 실어 보낼 수 없다. 그래서 요청을
보낸 뒤 응답을 받지 못하면(타임아웃, 연결 끊김, 응답 파싱 실패) OrderOutcomeUnknownError를
던진다. 주문은 UNKNOWN(미확정)으로 남고, 다시 보내지 않는다. 대신 find_order()가 당일
주문체결조회에서 같은 주문(종목, 방향, 수량, 주문시각)을 찾아 결과를 확정한다.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.core.exceptions import BrokerAPIError, OrderOutcomeUnknownError, SymbolNotFoundError
from app.core.logging import get_logger
from app.features.broker.base import (
    AssetClass,
    Balance,
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    Quote,
)
from app.features.broker.kis.auth import KISAuth, KISCredentials

logger = get_logger(__name__)

_ORDER_DVSN_LIMIT = "00"  # 지정가
_ORDER_DVSN_MARKET = "01"  # 시장가
_KST = ZoneInfo("Asia/Seoul")

# 요청이 서버로 나가기 *전에* 실패한 것이 확실한 예외. 이때만 다시 보내도 안전하다.
# 그 밖의 전송 오류(ReadTimeout, WriteTimeout, ReadError, RemoteProtocolError 등)는
# 브로커가 주문을 받았는지 알 수 없으므로 미확정으로 처리한다.
_NOT_SENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.LocalProtocolError,
    httpx.UnsupportedProtocol,
)


def _ccld_row_to_result(broker_order_id: str, row: dict, raw: dict) -> OrderResult:
    """주문체결조회(inquire-daily-ccld) 응답 한 행을 공용 OrderResult로 바꾼다."""
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
        raw=raw,
    )


def _normalize_odno(odno: str) -> str:
    """주문번호는 응답에 따라 앞에 0이 채워져 오기도 해서, 비교 전에 정규화한다."""
    return (odno or "").strip().lstrip("0")


class KISBrokerAdapter(BrokerAdapter):
    asset_class = AssetClass.KR_STOCK

    def __init__(self, live: bool, http: httpx.AsyncClient | None = None) -> None:
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
        self._http = http or httpx.AsyncClient(base_url=creds.base_url, timeout=5.0)

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

    async def _request_json(
        self, method: str, path: str, tr_id: str, **kwargs: Any
    ) -> tuple[dict, httpx.Headers]:
        """조회/취소용 공통 요청. 네트워크 오류, JSON 파싱 실패, rt_cd != 0을 모두
        BrokerAPIError로 바꾼다. 주문 *제출*은 미확정 판단이 필요해서 place_order가 따로 처리한다.
        """
        try:
            response = await self._http.request(
                method, path, headers=await self._headers(tr_id), **kwargs
            )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BrokerAPIError(f"KIS {path} request failed: {exc!r}") from exc

        if not isinstance(data, dict) or response.status_code != 200 or data.get("rt_cd") != "0":
            message = data.get("msg1") if isinstance(data, dict) else None
            raise BrokerAPIError(f"KIS {path} failed: {message or response.text[:200]}")
        return data, response.headers

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """주문 제출. 실패 유형에 따라 예외가 다르다.

        - BrokerAPIError: 주문이 접수되지 않은 것이 확실함 (전송 전 실패, rt_cd != 0 거부).
          다시 보내도 중복 주문이 되지 않는다.
        - OrderOutcomeUnknownError: 요청은 나갔지만 결과를 모름. 다시 보내면 안 되고
          find_order()로 대사해야 한다.
        """
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

        try:
            headers = await self._headers(tr_id)
        except BrokerAPIError:
            raise
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            # 토큰 발급 단계에서 실패했다. 주문 요청은 아직 나가지 않았다.
            raise BrokerAPIError(f"KIS token unavailable, order not sent: {exc!r}") from exc

        try:
            response = await self._http.post(
                "/uapi/domestic-stock/v1/trading/order-cash",
                headers=headers,
                json=body,
            )
        except _NOT_SENT_ERRORS as exc:
            raise BrokerAPIError(f"KIS order-cash not sent: {exc!r}") from exc
        except httpx.HTTPError as exc:
            raise OrderOutcomeUnknownError(
                f"KIS order-cash response lost ({type(exc).__name__}): 접수 여부 미확정"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            if 400 <= response.status_code < 500 and response.status_code != 408:
                # 게이트웨이가 요청 자체를 거부했다 (인증 오류 등). 주문은 접수되지 않았다.
                raise BrokerAPIError(
                    f"KIS order-cash failed ({response.status_code}): {response.text[:200]}"
                ) from exc
            raise OrderOutcomeUnknownError(
                f"KIS order-cash returned unparseable response ({response.status_code}): 접수 여부 미확정"
            ) from exc

        if not isinstance(data, dict):
            raise OrderOutcomeUnknownError("KIS order-cash returned unexpected payload: 접수 여부 미확정")
        if data.get("rt_cd") != "0":
            # 브로커가 명시적으로 거부했다 (rt_cd != 0). 접수되지 않은 것이 확실하다.
            raise BrokerAPIError(f"KIS order-cash failed: {data.get('msg1', response.text[:200])}")

        output = data.get("output") or {}
        org_no, odno = output.get("KRX_FWDG_ORD_ORGNO"), output.get("ODNO")
        if response.status_code != 200 or not org_no or not odno:
            # 성공(rt_cd=0)인데 주문번호를 모른다. 접수됐을 수 있으니 대사로 확인한다.
            raise OrderOutcomeUnknownError(
                f"KIS order-cash succeeded without order number ({response.status_code}): 접수 여부 미확정"
            )
        broker_order_id = f"{org_no}:{odno}"
        # order-cash 응답은 접수 확인일 뿐 체결 여부를 포함하지 않는다 — 체결 확인은
        # get_order_fill_status()를 통해 trading/tasks.py의 poll_pending_order_fills가 주기적으로 확인한다.
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

        data, _ = await self._request_json(
            "POST", "/uapi/domestic-stock/v1/trading/order-rvsecncl", tr_id, json=body
        )
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
        today = datetime.now(tz=_KST).strftime("%Y%m%d")
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

        data, _ = await self._request_json(
            "GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld", tr_id, params=params
        )

        rows = data.get("output1", [])
        if not rows:
            # 이 시각 기준으로 아직 조회 결과가 없다 — 접수 상태 그대로 유지 (에러 아님)
            return OrderResult(broker_order_id=broker_order_id, status="accepted", raw=data)

        return _ccld_row_to_result(broker_order_id, rows[0], data)

    async def find_order(
        self,
        order: OrderRequest,
        *,
        placed_after: datetime,
        exclude_broker_order_ids: frozenset[str] = frozenset(),
    ) -> OrderResult | None:
        """미확정(UNKNOWN) 주문 대사: 당일 주문체결조회에서 같은 주문을 찾는다.

        KIS에는 클라이언트 주문번호가 없다. 그래서 종목, 매수/매도, 주문수량, 주문시각
        (placed_after 이후)으로 찾고, 이미 다른 주문에 연결된 주문번호
        (exclude_broker_order_ids)는 뺀다.
        - 정확히 한 건: 그 주문의 현재 상태를 돌려준다.
        - 0건: None (접수 기록 없음).
        - 2건 이상이거나 조회 결과가 다음 페이지로 이어짐: OrderOutcomeUnknownError.
          HTS에서 사람이 같은 조건으로 낸 주문과 구분할 수 없으니 수동으로 확인해야 한다.

        ⚠️ get_order_fill_status와 마찬가지로 응답 필드명(ord_dt, ord_tmd, odno,
        ord_gno_brno, sll_buy_dvsn_cd, orgn_odno 등)은 KIS 공식 문서 기준이고 실제 계좌로
        검증하지 못했다. 실거래 전에 모의투자 계좌로 먼저 확인할 것.
        """
        cano, prdt_cd = self._account_parts()
        tr_id = "TTTC8001R" if self._live else "VTTC8001R"
        placed_after_kst = placed_after.astimezone(_KST)
        today = datetime.now(tz=_KST).strftime("%Y%m%d")
        side_code = "02" if order.side == "buy" else "01"  # 01: 매도, 02: 매수
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "INQR_STRT_DT": placed_after_kst.strftime("%Y%m%d"),
            "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": side_code,
            "PDNO": order.symbol,
            "CCLD_DVSN": "00",  # 00: 전체(체결+미체결)
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN": "00",
            "INQR_DVSN_1": "",
            "INQR_DVSN_3": "00",
            "EXCG_ID_DVSN_CD": "KRX",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        data, response_headers = await self._request_json(
            "GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld", tr_id, params=params
        )

        threshold = placed_after_kst.strftime("%Y%m%d%H%M%S")
        excluded = {_normalize_odno(bid.partition(":")[2]) for bid in exclude_broker_order_ids}
        quantity = int(order.quantity)
        matches = [
            row
            for row in data.get("output1") or []
            if row.get("pdno") == order.symbol
            and row.get("sll_buy_dvsn_cd") == side_code
            and int(float(row.get("ord_qty") or 0)) == quantity
            and f"{row.get('ord_dt', '')}{row.get('ord_tmd', '')}" >= threshold
            and not (row.get("orgn_odno") or "").strip()  # 정정/취소 주문 행은 제외
            and _normalize_odno(row.get("odno", "")) not in excluded
        ]

        if len(matches) > 1:
            raise OrderOutcomeUnknownError(
                f"KIS 대사: {order.symbol} {order.side} {quantity}주 후보가 {len(matches)}건이라 "
                "특정할 수 없음"
            )
        if not matches:
            if response_headers.get("tr_cont") in ("F", "M"):
                # 다음 페이지가 있다. 이 페이지에 없다고 해서 접수 기록이 없다고 단정하면 안 된다.
                raise OrderOutcomeUnknownError(
                    "KIS 대사: 조회 결과가 여러 페이지라 접수 기록이 없다고 확정할 수 없음"
                )
            return None

        row = matches[0]
        broker_order_id = f"{row.get('ord_gno_brno', '')}:{row.get('odno', '')}"
        return _ccld_row_to_result(broker_order_id, row, data)

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

        data, _ = await self._request_json(
            "GET", "/uapi/domestic-stock/v1/trading/inquire-balance", tr_id, params=params
        )

        positions = {
            holding["pdno"]: float(holding["hldg_qty"])
            for holding in data.get("output1", [])
            if float(holding.get("hldg_qty", 0)) > 0
        }
        cash = float(data["output2"][0]["dnca_tot_amt"]) if data.get("output2") else 0.0
        return Balance(cash=cash, positions=positions)

    async def get_quote(self, symbol: str) -> Quote:
        """주식현재가 시세(FHKST01010100) + 종목명(상품기본조회 CTPF1002R).

        KIS는 없는 종목코드에도 rt_cd=0(정상)으로 응답하고 현재가만 0으로 돌려주므로,
        현재가가 0 이하면 없는 종목으로 본다. 시세 조회 TR은 모의/실전 구분 없이 같다.
        """
        response = await self._http.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=await self._headers("FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        data = response.json()
        if response.status_code != 200 or data.get("rt_cd") != "0":
            raise BrokerAPIError(f"KIS inquire-price failed: {data.get('msg1', response.text)}")

        output = data.get("output") or {}
        price = float(output.get("stck_prpr") or 0)
        if price <= 0:
            raise SymbolNotFoundError(f"종목코드를 찾을 수 없어요: {symbol}")
        change_rate = output.get("prdy_ctrt")

        return Quote(
            symbol=symbol,
            price=price,
            name=await self._stock_name(symbol),
            change_rate=float(change_rate) if change_rate not in (None, "") else None,
        )

    async def _stock_name(self, symbol: str) -> str | None:
        """종목명은 확인용 부가 정보라, 조회에 실패해도 현재가는 그대로 보여준다."""
        try:
            response = await self._http.get(
                "/uapi/domestic-stock/v1/quotations/search-stock-info",
                headers=await self._headers("CTPF1002R"),
                params={"PRDT_TYPE_CD": "300", "PDNO": symbol},
            )
            data = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("KIS stock name lookup failed for %s", symbol)
            return None
        if data.get("rt_cd") != "0":
            return None
        return (data.get("output") or {}).get("prdt_abrv_name") or None
