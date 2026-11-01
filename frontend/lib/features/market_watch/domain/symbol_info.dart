/// 종목 검색 결과 (GET /market-data/{asset_class}/symbols?q=...).
class SymbolInfo {
  const SymbolInfo({required this.symbol, required this.name, this.market = ''});

  /// 주식: 6자리 종목코드 (예: 005930, 0001A0) / 코인: 원화 마켓 코드 (예: KRW-BTC)
  final String symbol;
  final String name;

  /// KOSPI / KOSDAQ / UPBIT
  final String market;

  String get label => '$name ($symbol)';

  factory SymbolInfo.fromJson(Map<String, dynamic> json) => SymbolInfo(
        symbol: json['symbol'] as String,
        name: json['name'] as String,
        market: json['market'] as String? ?? '',
      );
}
