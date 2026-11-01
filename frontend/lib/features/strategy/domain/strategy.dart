enum StrategyStatus { active, paused, stopped }

/// 백엔드 AssetClass와 같은 값(kr_stock / crypto)을 쓴다.
enum AssetClass {
  krStock('kr_stock', '주식 (KIS)'),
  crypto('crypto', '코인 (업비트)');

  const AssetClass(this.apiValue, this.label);

  final String apiValue;
  final String label;

  static AssetClass fromApi(String value) =>
      AssetClass.values.firstWhere((a) => a.apiValue == value, orElse: () => AssetClass.krStock);
}

class Strategy {
  const Strategy({
    required this.id,
    required this.name,
    required this.symbol,
    required this.status,
    this.assetClass = AssetClass.krStock,
    this.entryRule = const {},
    this.exitRule = const {},
    this.maxPositionSize = 0,
    this.stopLossPct = 0,
  });

  final int id;
  final String name;
  final String symbol;
  final StrategyStatus status;
  final AssetClass assetClass;
  final Map<String, dynamic> entryRule;
  final Map<String, dynamic> exitRule;
  final double maxPositionSize;

  /// 0.03 = 3%
  final double stopLossPct;

  factory Strategy.fromJson(Map<String, dynamic> json) => Strategy(
        id: json['id'] as int,
        name: json['name'] as String,
        symbol: json['symbol'] as String,
        status: StrategyStatus.values.byName(json['status'] as String),
        assetClass: AssetClass.fromApi(json['asset_class'] as String? ?? 'kr_stock'),
        entryRule: (json['entry_rule'] as Map?)?.cast<String, dynamic>() ?? const {},
        exitRule: (json['exit_rule'] as Map?)?.cast<String, dynamic>() ?? const {},
        maxPositionSize: (json['max_position_size'] as num?)?.toDouble() ?? 0,
        stopLossPct: (json['stop_loss_pct'] as num?)?.toDouble() ?? 0,
      );

  /// 등록 화면(가격 조건 폼)으로 다시 열어 수정할 수 있는 규칙인지.
  /// 이동평균 등 폼이 표현하지 못하는 규칙은 수정 화면에서 값을 잃지 않도록 막는다.
  bool get isEditableInForm =>
      entryRule['type'] == 'price_threshold' &&
      entryRule['below'] is num &&
      (exitRule.isEmpty || (exitRule['type'] == 'price_threshold' && exitRule['above'] is num));

  double? get buyBelow => (entryRule['below'] as num?)?.toDouble();

  double? get sellAbove => exitRule.isEmpty ? null : (exitRule['above'] as num?)?.toDouble();

  /// 목록에서 한눈에 보는 요약. 예: "7,000원 이하 매수 · 7,500원 이상 매도 · 손절 3% · 1주"
  String get summary => describeRules(
        assetClass: assetClass,
        entryRule: entryRule,
        exitRule: exitRule,
        quantity: maxPositionSize,
        stopLossPct: stopLossPct,
      );
}

/// 새로 등록할 전략. 서버에는 항상 꺼진(paused) 상태로 생성된다.
class StrategyDraft {
  const StrategyDraft({
    required this.name,
    required this.assetClass,
    required this.symbol,
    required this.buyBelow,
    required this.sellAbove,
    required this.quantity,
    required this.stopLossPct,
  });

  final String name;
  final AssetClass assetClass;
  final String symbol;

  /// 현재가가 이 가격 이하가 되면 매수.
  final double buyBelow;

  /// 보유 중 현재가가 이 가격 이상이 되면 매도(익절). null이면 익절 없이 손절만 사용.
  final double? sellAbove;

  final double quantity;

  /// 0.03 = 3%
  final double stopLossPct;

  Map<String, dynamic> get entryRule => {'type': 'price_threshold', 'below': buyBelow};

  Map<String, dynamic> get exitRule =>
      sellAbove == null ? const {} : {'type': 'price_threshold', 'above': sellAbove};

  Map<String, dynamic> toJson() => {
        'name': name,
        'asset_class': assetClass.apiValue,
        'symbol': symbol,
        'entry_rule': entryRule,
        'exit_rule': exitRule,
        'max_position_size': quantity,
        'stop_loss_pct': stopLossPct,
      };

  String get summary => describeRules(
        assetClass: assetClass,
        entryRule: entryRule,
        exitRule: exitRule,
        quantity: quantity,
        stopLossPct: stopLossPct,
      );
}

String formatKrw(num value) {
  final fixed = value == value.roundToDouble() ? value.toInt().toString() : value.toStringAsFixed(2);
  final parts = fixed.split('.');
  final grouped = parts[0].replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
  return parts.length > 1 ? '$grouped.${parts[1]}' : grouped;
}

String formatQuantity(AssetClass assetClass, num quantity) {
  if (assetClass == AssetClass.krStock) return '${quantity.toInt()}주';
  var text = quantity.toStringAsFixed(8);
  text = text.replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '');
  return '$text개';
}

String describeRules({
  required AssetClass assetClass,
  required Map<String, dynamic> entryRule,
  required Map<String, dynamic> exitRule,
  required num quantity,
  required num stopLossPct,
}) {
  String rule(Map<String, dynamic> r, String action) {
    if (r.isEmpty) return '';
    if (r['type'] == 'price_threshold') {
      if (r['below'] != null) return '${formatKrw(r['below'] as num)}원 이하 $action';
      if (r['above'] != null) return '${formatKrw(r['above'] as num)}원 이상 $action';
    }
    if (r['type'] == 'ma_cross') return '이동평균(${r['fast']}/${r['slow']}) $action';
    return '${r['type']} $action';
  }

  final pct = (stopLossPct * 100);
  final pctText = pct == pct.roundToDouble() ? pct.toInt().toString() : pct.toStringAsFixed(1);
  return [
    rule(entryRule, '매수'),
    rule(exitRule, '매도'),
    '손절 $pctText%',
    formatQuantity(assetClass, quantity),
  ].where((s) => s.isNotEmpty).join(' · ');
}
