class PriceTick {
  const PriceTick({required this.symbol, required this.price, required this.timestamp});

  final String symbol;
  final double price;
  final double timestamp;

  factory PriceTick.fromJson(Map<String, dynamic> json) => PriceTick(
        symbol: json['symbol'] as String,
        price: (json['price'] as num).toDouble(),
        timestamp: (json['timestamp'] as num).toDouble(),
      );
}
