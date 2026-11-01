from app.features.market_data.symbols import SymbolInfo, parse_kis_master, search_symbols

TAIL = 228


def _row(code: str, name: str, group: str, spill: str = " ") -> str:
    """마스터 파일 한 줄을 흉내 낸다: [코드 9][표준코드 12][이름][spill + 그룹 + 나머지 고정폭]."""
    tail = (spill + group).ljust(TAIL, "0")
    return code.ljust(9) + "KR7000000000" + name + tail


def test_parse_keeps_tradable_groups_and_fixes_spilled_names():
    text = "\n".join(
        [
            _row("005930", "삼성전자", "ST"),
            _row("0001A0", "덕양에너젠", "ST"),  # 영문 섞인 신규 종목코드
            _row("069500", "KODEX 200", "EF"),
            _row("0000D0", "TIGER 엔비디아미국채커버드콜밸런스(합성", "EF", spill=")"),
            _row("088260", "이리츠코크렙", "RT"),
            _row("F70100034", "한투한미넥스트혁신성장1(A)", "BC"),  # 수익증권: 제외
            _row("123456", "어떤신주인수권", "SW"),  # 신주인수권: 제외
        ]
    )
    parsed = parse_kis_master(text, "KOSPI", TAIL)
    assert [(s.symbol, s.name) for s in parsed] == [
        ("005930", "삼성전자"),
        ("0001A0", "덕양에너젠"),
        ("069500", "KODEX 200"),
        ("0000D0", "TIGER 엔비디아미국채커버드콜밸런스(합성)"),
        ("088260", "이리츠코크렙"),
    ]
    assert {s.market for s in parsed} == {"KOSPI"}


STOCKS = [
    SymbolInfo("005930", "삼성전자", "KOSPI"),
    SymbolInfo("005935", "삼성전자우", "KOSPI"),
    SymbolInfo("028260", "삼성물산", "KOSPI"),
    SymbolInfo("006400", "삼성SDI", "KOSPI"),
    SymbolInfo("000660", "SK하이닉스", "KOSPI"),
    SymbolInfo("207940", "삼성바이오로직스", "KOSPI"),
]


def test_exact_name_ranks_first_then_prefix_then_contains():
    names = [s.name for s in search_symbols(STOCKS, "삼성전자")]
    assert names == ["삼성전자", "삼성전자우"]

    names = [s.name for s in search_symbols(STOCKS, "삼성")]
    assert names[0] == "삼성물산"  # 앞부분 일치 중 가장 짧은 이름 (4글자)
    assert set(names) == {"삼성전자", "삼성전자우", "삼성물산", "삼성SDI", "삼성바이오로직스"}

    assert [s.name for s in search_symbols(STOCKS, "하이닉스")] == ["SK하이닉스"]  # 포함


def test_search_by_code_and_case_insensitive():
    assert [s.symbol for s in search_symbols(STOCKS, "0059")] == ["005930", "005935"]
    assert [s.name for s in search_symbols(STOCKS, "sk")] == ["SK하이닉스"]


def test_limit_and_empty_query():
    assert len(search_symbols(STOCKS, "삼성", limit=2)) == 2
    assert search_symbols(STOCKS, "   ") == []
    assert search_symbols(STOCKS, "없는종목") == []


def test_crypto_matches_ticker_and_english_name():
    coins = [
        SymbolInfo("KRW-BTC", "비트코인", "UPBIT", "Bitcoin"),
        SymbolInfo("KRW-BCH", "비트코인캐시", "UPBIT", "Bitcoin Cash"),
        SymbolInfo("KRW-ETH", "이더리움", "UPBIT", "Ethereum"),
    ]
    assert [s.symbol for s in search_symbols(coins, "btc")] == ["KRW-BTC"]
    assert [s.symbol for s in search_symbols(coins, "비트코인")] == ["KRW-BTC", "KRW-BCH"]
    assert [s.symbol for s in search_symbols(coins, "ether")] == ["KRW-ETH"]
