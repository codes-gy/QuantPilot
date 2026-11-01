"""종목명/코드 검색용 종목 목록.

- 국내 주식: KIS가 공개하는 종목 마스터 파일(코스피/코스닥, cp949 고정폭 텍스트를 zip으로 배포).
  KIS REST API에는 이름으로 종목을 찾는 기능이 없어서 이 파일을 쓴다.
- 코인: Upbit 공개 마켓 목록(/v1/market/all)의 원화(KRW-*) 마켓.

목록은 API 프로세스 메모리에 CACHE_TTL_SECONDS 동안 보관하고, 만료되면 다음 검색 때 다시 받는다.
"""

import asyncio
import io
import time
import zipfile
from dataclasses import dataclass

import httpx

from app.core.exceptions import BrokerAPIError
from app.core.logging import get_logger
from app.features.broker.base import AssetClass

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 12 * 60 * 60

# (시장명, URL, 레코드 뒤쪽 고정폭 영역 길이) — KIS open-trading-api 예제의 파싱 규칙과 같다.
_KIS_MASTERS = (
    ("KOSPI", "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip", 228),
    ("KOSDAQ", "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip", 222),
)

# 일반 주문으로 사고팔 수 있는 증권 그룹만 검색에 노출한다.
# ST 주식, EF ETF, EN ETN, RT 리츠, FS 외국주권, DR 예탁증서
# (BC 수익증권은 9자리 코드라 주문 불가, SW/SR 신주인수권 등은 제외)
_TRADABLE_GROUPS = {"ST", "EF", "EN", "RT", "FS", "DR"}

UPBIT_MARKETS_URL = "https://api.upbit.com/v1/market/all"


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    name: str
    market: str  # KOSPI / KOSDAQ / UPBIT
    english_name: str | None = None


def parse_kis_master(text: str, market: str, tail_length: int) -> list[SymbolInfo]:
    """마스터 파일 한 줄 = [단축코드 9][표준코드 12][한글명 ...][고정폭 영역 tail_length].

    한글명 칸이 넘칠 만큼 긴 이름은 마지막 글자가 고정폭 영역의 첫 칸에 걸쳐 있어서
    (예: "...(합성" + ")"), 그 칸을 이름에 붙이고 증권 그룹 코드는 그 다음 두 칸에서 읽는다.
    """
    symbols: list[SymbolInfo] = []
    for row in text.splitlines():
        if len(row) <= tail_length + 21:
            continue
        head, tail = row[:-tail_length], row[-tail_length:]
        code = head[0:9].strip()
        name = (head[21:] + tail[0]).strip()
        group = tail[1:3]
        if group not in _TRADABLE_GROUPS or len(code) != 6 or not name:
            continue
        symbols.append(SymbolInfo(symbol=code, name=name, market=market))
    return symbols


def search_symbols(symbols: list[SymbolInfo], query: str, limit: int = 20) -> list[SymbolInfo]:
    """이름/코드 부분 일치 검색. 정확히 일치 > 앞부분 일치 > 포함 순, 같은 순위면 짧은 이름 우선."""
    q = query.strip().upper()
    if not q:
        return []

    ranked: list[tuple[int, int, str, SymbolInfo]] = []
    for s in symbols:
        name = s.name.upper()
        code = s.symbol.upper()
        # 코인은 "BTC"처럼 마켓 코드 뒷부분으로도 찾을 수 있게 한다.
        ticker = code.removeprefix("KRW-")
        english = (s.english_name or "").upper()
        if q in (name, code, ticker, english):
            rank = 0
        elif name.startswith(q) or code.startswith(q) or ticker.startswith(q) or english.startswith(q):
            rank = 1
        elif q in name or q in english:
            rank = 2
        else:
            continue
        ranked.append((rank, len(s.name), s.name, s))

    ranked.sort(key=lambda r: r[:3])
    return [r[3] for r in ranked[:limit]]


class SymbolDirectory:
    def __init__(self) -> None:
        self._cache: dict[AssetClass, tuple[float, list[SymbolInfo]]] = {}
        self._lock = asyncio.Lock()

    async def get(self, asset_class: AssetClass) -> list[SymbolInfo]:
        cached = self._cache.get(asset_class)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        async with self._lock:
            cached = self._cache.get(asset_class)
            if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
                return cached[1]
            try:
                symbols = await self._load(asset_class)
            except (httpx.HTTPError, zipfile.BadZipFile, ValueError, KeyError) as exc:
                if cached:  # 갱신 실패 시 이전 목록이라도 계속 쓴다
                    logger.warning("symbol list refresh failed (%s), using stale list: %s", asset_class, exc)
                    return cached[1]
                raise BrokerAPIError(f"종목 목록을 받아오지 못했어요: {exc}") from exc
            self._cache[asset_class] = (time.monotonic(), symbols)
            logger.info("loaded %d %s symbols", len(symbols), asset_class)
            return symbols

    async def search(self, asset_class: AssetClass, query: str, limit: int = 20) -> list[SymbolInfo]:
        return search_symbols(await self.get(asset_class), query, limit)

    async def _load(self, asset_class: AssetClass) -> list[SymbolInfo]:
        async with httpx.AsyncClient(timeout=20.0) as http:
            if asset_class is AssetClass.CRYPTO:
                response = await http.get(UPBIT_MARKETS_URL, params={"isDetails": "false"})
                response.raise_for_status()
                return [
                    SymbolInfo(
                        symbol=m["market"],
                        name=m["korean_name"],
                        market="UPBIT",
                        english_name=m.get("english_name"),
                    )
                    for m in response.json()
                    if m["market"].startswith("KRW-")
                ]

            symbols: list[SymbolInfo] = []
            for market, url, tail_length in _KIS_MASTERS:
                response = await http.get(url)
                response.raise_for_status()
                archive = zipfile.ZipFile(io.BytesIO(response.content))
                text = archive.read(archive.namelist()[0]).decode("cp949")
                symbols.extend(parse_kis_master(text, market, tail_length))
            return symbols


_directory = SymbolDirectory()


def get_symbol_directory() -> SymbolDirectory:
    return _directory
