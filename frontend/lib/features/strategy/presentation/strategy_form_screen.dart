import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/strategy_repository.dart';
import '../domain/strategy.dart';

/// Upbit 원화 마켓 최소 주문 금액 (백엔드 upbit/client.py의 MIN_ORDER_KRW와 같은 값).
const _upbitMinOrderKrw = 5000;

/// 가격 조건(price_threshold) 전략 등록/수정 폼. [initial]을 넘기면 그 전략의 값으로
/// 채워진 수정 화면이 되고, 저장 시 PUT으로 덮어쓴다 (꺼진 상태 유지).
///
/// 이동평균(ma_cross) 규칙은 지금 엔진이 틱 단위로 계산하고 매도 조건을 반대로 표현할 수
/// 없어서, 화면에서는 동작이 명확한 가격 조건만 지원한다. 등록된 전략은 항상 꺼진 상태로
/// 만들어지고, 켜는 것은 목록의 스위치에서 확인 창을 거쳐서만 가능하다.
class StrategyFormScreen extends ConsumerStatefulWidget {
  const StrategyFormScreen({super.key, this.initial});

  /// 수정할 전략. null이면 새로 등록. [Strategy.isEditableInForm]인 전략만 넘겨야 한다.
  final Strategy? initial;

  @override
  ConsumerState<StrategyFormScreen> createState() => _StrategyFormScreenState();
}

class _StrategyFormScreenState extends ConsumerState<StrategyFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _symbol = TextEditingController();
  final _buyBelow = TextEditingController();
  final _sellAbove = TextEditingController();
  final _quantity = TextEditingController(text: '1');
  final _stopLoss = TextEditingController(text: '3');

  AssetClass _assetClass = AssetClass.krStock;
  bool _submitting = false;

  bool get _isEdit => widget.initial != null;

  @override
  void initState() {
    super.initState();
    final initial = widget.initial;
    if (initial != null) {
      _assetClass = initial.assetClass;
      _name.text = initial.name;
      _symbol.text = initial.symbol;
      _buyBelow.text = _plain(initial.buyBelow);
      _sellAbove.text = _plain(initial.sellAbove);
      _quantity.text = initial.assetClass == AssetClass.krStock
          ? initial.maxPositionSize.toInt().toString()
          : _plain(initial.maxPositionSize);
      _stopLoss.text = _plain(initial.stopLossPct * 100);
    }
    for (final c in [_buyBelow, _sellAbove, _quantity, _stopLoss, _symbol]) {
      c.addListener(() => setState(() {})); // 요약/예상 금액 미리보기 갱신
    }
  }

  @override
  void dispose() {
    for (final c in [_name, _symbol, _buyBelow, _sellAbove, _quantity, _stopLoss]) {
      c.dispose();
    }
    super.dispose();
  }

  /// 입력칸에 넣을 숫자 문자열 (불필요한 소수점 0 제거, 부동소수 오차 정리).
  static String _plain(num? v) {
    if (v == null) return '';
    if (v == v.roundToDouble()) return v.toInt().toString();
    return double.parse(v.toStringAsFixed(8)).toString();
  }

  bool get _isCrypto => _assetClass == AssetClass.crypto;

  double? _num(TextEditingController c) => double.tryParse(c.text.replaceAll(',', '').trim());

  String get _normalizedSymbol => _symbol.text.trim().toUpperCase();

  /// 폼 값이 모두 유효할 때만 만들어진다 (미리보기와 제출이 같은 값을 쓰도록).
  StrategyDraft? get _draft {
    final buy = _num(_buyBelow);
    final qty = _num(_quantity);
    final stop = _num(_stopLoss);
    if (buy == null || qty == null || stop == null || _normalizedSymbol.isEmpty) return null;
    final name = _name.text.trim();
    return StrategyDraft(
      name: name.isEmpty ? '$_normalizedSymbol 가격 전략' : name,
      assetClass: _assetClass,
      symbol: _normalizedSymbol,
      buyBelow: buy,
      sellAbove: _sellAbove.text.trim().isEmpty ? null : _num(_sellAbove),
      quantity: qty,
      stopLossPct: stop / 100,
    );
  }

  @override
  Widget build(BuildContext context) {
    final draft = _draft;
    final buy = _num(_buyBelow);
    final qty = _num(_quantity);
    final estimated = (buy != null && qty != null) ? buy * qty : null;

    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? '전략 수정' : '전략 추가')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('거래소', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            SegmentedButton<AssetClass>(
              segments: [
                for (final a in AssetClass.values) ButtonSegment(value: a, label: Text(a.label)),
              ],
              selected: {_assetClass},
              onSelectionChanged: (s) => setState(() {
                _assetClass = s.first;
                _quantity.text = _isCrypto ? '' : '1';
                _formKey.currentState?.validate();
              }),
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const ValueKey('field-symbol'),
              controller: _symbol,
              decoration: InputDecoration(
                labelText: '종목',
                hintText: _isCrypto ? '예: KRW-BTC' : '예: 005930 (6자리 종목코드)',
                border: const OutlineInputBorder(),
              ),
              textCapitalization: TextCapitalization.characters,
              validator: (_) {
                final s = _normalizedSymbol;
                if (s.isEmpty) return '종목을 입력하세요.';
                if (_isCrypto && !RegExp(r'^KRW-[A-Z0-9]+$').hasMatch(s)) {
                  return '원화 마켓 코드만 가능해요 (예: KRW-BTC).';
                }
                if (!_isCrypto && !RegExp(r'^\d{6}$').hasMatch(s)) {
                  return '6자리 숫자 종목코드를 입력하세요.';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            _priceField(
              key: 'field-buy',
              controller: _buyBelow,
              label: '매수 가격 (원)',
              helper: '현재가가 이 가격 이하가 되면 매수해요.',
              validator: (v) => v == null || v <= 0 ? '0보다 큰 가격을 입력하세요.' : null,
            ),
            const SizedBox(height: 16),
            _priceField(
              key: 'field-sell',
              controller: _sellAbove,
              label: '익절 가격 (원, 선택)',
              helper: '보유 중 이 가격 이상이 되면 팔아요. 비우면 손절로만 매도해요.',
              validator: (v) {
                if (_sellAbove.text.trim().isEmpty) return null;
                if (v == null || v <= 0) return '0보다 큰 가격을 입력하세요.';
                final b = _num(_buyBelow);
                if (b != null && v <= b) return '익절 가격은 매수 가격보다 높아야 해요.';
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const ValueKey('field-quantity'),
              controller: _quantity,
              decoration: InputDecoration(
                labelText: _isCrypto ? '수량 (개)' : '수량 (주)',
                helperText: estimated == null ? null : '매수 가격 기준 약 ${formatKrw(estimated.round())}원',
                border: const OutlineInputBorder(),
              ),
              keyboardType: TextInputType.numberWithOptions(decimal: _isCrypto),
              inputFormatters: [
                FilteringTextInputFormatter.allow(_isCrypto ? RegExp(r'[0-9.]') : RegExp(r'[0-9]')),
              ],
              validator: (_) {
                final q = _num(_quantity);
                if (q == null || q <= 0) return '0보다 큰 수량을 입력하세요.';
                final b = _num(_buyBelow);
                if (_isCrypto && b != null && b * q < _upbitMinOrderKrw) {
                  return '업비트 최소 주문 금액은 ${formatKrw(_upbitMinOrderKrw)}원이에요.';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const ValueKey('field-stoploss'),
              controller: _stopLoss,
              decoration: const InputDecoration(
                labelText: '손절 비율 (%)',
                helperText: '매수가 대비 이만큼 떨어지면 자동으로 팔아요.',
                suffixText: '%',
                border: OutlineInputBorder(),
              ),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
              validator: (_) {
                final v = _num(_stopLoss);
                if (v == null || v <= 0 || v >= 100) return '0보다 크고 100보다 작은 값을 입력하세요.';
                return null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const ValueKey('field-name'),
              controller: _name,
              decoration: const InputDecoration(
                labelText: '전략 이름 (선택)',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 24),
            Card(
              child: ListTile(
                leading: const Icon(Icons.summarize_outlined),
                title: Text(draft == null ? '입력하면 요약이 표시돼요' : draft.summary),
                subtitle: Text(
                  _isEdit
                      ? '저장해도 꺼진 상태 그대로예요. 목록에서 직접 켜야 매매가 시작돼요.'
                      : '꺼진 상태로 등록돼요. 목록에서 직접 켜야 매매가 시작돼요.',
                ),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              key: const ValueKey('submit-strategy'),
              onPressed: _submitting ? null : _submit,
              icon: _submitting
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : Icon(_isEdit ? Icons.save : Icons.add),
              label: Text(_isEdit ? '저장' : '등록'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _priceField({
    required String key,
    required TextEditingController controller,
    required String label,
    required String helper,
    required String? Function(double? value) validator,
  }) {
    return TextFormField(
      key: ValueKey(key),
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        helperText: helper,
        suffixText: '원',
        border: const OutlineInputBorder(),
      ),
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
      validator: (_) => validator(_num(controller)),
    );
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final draft = _draft;
    if (draft == null) return;

    setState(() => _submitting = true);
    try {
      final repo = ref.read(strategyRepositoryProvider);
      final initial = widget.initial;
      if (initial != null) {
        await repo.update(initial.id, draft);
      } else {
        await repo.create(draft);
      }
      ref.invalidate(strategyListProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            initial != null ? '전략을 저장했어요.' : '전략을 꺼진 상태로 등록했어요. 목록에서 켜면 매매가 시작돼요.',
          ),
        ),
      );
      Navigator.of(context).pop(true);
    } on DioException catch (e) {
      final detail = e.response?.data is Map ? (e.response!.data as Map)['detail'] : null;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${_isEdit ? '저장' : '등록'} 실패: ${detail ?? e.message}')),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }
}
