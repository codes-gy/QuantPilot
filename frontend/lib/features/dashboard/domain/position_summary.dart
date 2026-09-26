class PositionSummary {
  const PositionSummary({
    required this.symbol,
    required this.assetClass,
    required this.quantity,
    required this.avgEntryPrice,
  });

  final String symbol;
  final String assetClass;
  final double quantity;
  final double avgEntryPrice;

  factory PositionSummary.fromJson(Map<String, dynamic> json) => PositionSummary(
        symbol: json['symbol'] as String,
        assetClass: json['asset_class'] as String,
        quantity: (json['quantity'] as num).toDouble(),
        avgEntryPrice: (json['avg_entry_price'] as num).toDouble(),
      );
}
