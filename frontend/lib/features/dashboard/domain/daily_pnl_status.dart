class DailyPnlStatus {
  const DailyPnlStatus({required this.realizedPnlKrw, required this.dailyLossLimitKrw});

  final double realizedPnlKrw;
  final double? dailyLossLimitKrw;

  factory DailyPnlStatus.fromJson(Map<String, dynamic> json) => DailyPnlStatus(
        realizedPnlKrw: (json['realized_pnl_krw'] as num).toDouble(),
        dailyLossLimitKrw: (json['daily_loss_limit_krw'] as num?)?.toDouble(),
      );
}
