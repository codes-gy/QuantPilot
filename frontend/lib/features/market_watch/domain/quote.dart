/// 증권사/거래소에서 직접 조회한 현재가 (GET /market-data/{asset_class}/{symbol}/quote).
class Quote {
  const Quote({required this.symbol, required this.price, this.name, this.changeRate});

  final String symbol;

  /// 종목명 — 종목코드를 잘못 입력하지 않았는지 확인하는 용도. 조회 실패 시 null.
  final String? name;
  final double price;

  /// 전일 대비 등락률(%) 예: -4.96
  final double? changeRate;

  factory Quote.fromJson(Map<String, dynamic> json) => Quote(
        symbol: json['symbol'] as String,
        name: json['name'] as String?,
        price: (json['price'] as num).toDouble(),
        changeRate: (json['change_rate'] as num?)?.toDouble(),
      );
}
