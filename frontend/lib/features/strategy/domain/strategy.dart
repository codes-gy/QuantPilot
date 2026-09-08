enum StrategyStatus { active, paused, stopped }

class Strategy {
  const Strategy({
    required this.id,
    required this.name,
    required this.symbol,
    required this.status,
  });

  final int id;
  final String name;
  final String symbol;
  final StrategyStatus status;

  factory Strategy.fromJson(Map<String, dynamic> json) => Strategy(
        id: json['id'] as int,
        name: json['name'] as String,
        symbol: json['symbol'] as String,
        status: StrategyStatus.values.byName(json['status'] as String),
      );
}
