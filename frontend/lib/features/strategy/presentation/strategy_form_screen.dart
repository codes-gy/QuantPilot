import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../market_watch/data/market_watch_repository.dart';
import '../../market_watch/domain/quote.dart';
import '../../market_watch/domain/symbol_info.dart';
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
  /// 선택된 종목 코드 (화면에는 직접 보이지 않고, 검색칸에는 "종목명 (코드)"가 보인다).
  final _symbol = TextEditingController();
  final _symbolQuery = TextEditingController();
  final _buyBelow = TextEditingController();
  final _sellAbove = TextEditingController();
  final _quantity = TextEditingController(text: '1');
  final _stopLoss = TextEditingController(text: '3');

  AssetClass _assetClass = AssetClass.krStock;
  bool _submitting = false;

  // 종목 검색 상태. 사용자가 목록에서 고른 종목만 등록할 수 있다 (코드 오타 방지).
  SymbolInfo? _selected;
  List<SymbolInfo> _results = const [];
  bool _searching = false;
  String? _searchError;
  Timer? _searchDebounce;
  int _searchSeq = 0; // 늦게 도착한 이전 검색 결과를 버리기 위한 순번

  // 현재가 조회 상태. 종목이나 거래소를 바꾸면 이전 결과는 지운다.
  Quote? _quote;
  String? _quoteError;
  bool _quoteLoading = false;

  bool get _isEdit => widget.initial != null;

  @override
  void initState() {
    super.initState();
    final initial = widget.initial;
    if (initial != null) {
      _assetClass = initial.assetClass;
      _name.text = initial.name;
      _symbol.text = initial.symbol;
      // 수정 화면: 종목명은 현재가 조회 응답으로 채운다 (전략에는 코드만 저장돼 있음).
      _selected = SymbolInfo(symbol: initial.symbol, name: initial.symbol);
      _symbolQuery.text = initial.symbol;
      WidgetsBinding.instance.addPostFrameCallback((_) => _lookupQuote());
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
    _searchDebounce?.cancel();
    for (final c in [_name, _symbol, _symbolQuery, _buyBelow, _sellAbove, _quantity, _stopLoss]) {
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
      name: name.isEmpty ? '${_selected?.name ?? _normalizedSymbol} 가격 전략' : name,
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
                _clearSelection();
                _quantity.text = _isCrypto ? '' : '1';
                _formKey.currentState?.validate();
              }),
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const ValueKey('field-symbol'),
              controller: _symbolQuery,
              readOnly: _selected != null,
              decoration: InputDecoration(
                labelText: '종목',
                hintText: _isCrypto ? '코인 이름이나 티커로 검색 (예: 비트코인, BTC)' : '종목명이나 코드로 검색 (예: 삼성전자)',
                border: const OutlineInputBorder(),
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _selected == null
                    ? (_searching
                        ? const Padding(
                            padding: EdgeInsets.all(12),
                            child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                          )
                        : null)
                    : IconButton(
                        key: const ValueKey('clear-symbol'),
                        tooltip: '다른 종목 선택',
                        icon: const Icon(Icons.close),
                        onPressed: () => setState(_clearSelection),
                      ),
              ),
              onChanged: _onQueryChanged,
              validator: (_) => _selected == null ? '종목을 검색해서 목록에서 선택하세요.' : null,
            ),
            if (_selected == null)
              _SymbolResults(
                query: _symbolQuery.text.trim(),
                results: _results,
                searching: _searching,
                error: _searchError,
                onSelect: _selectSymbol,
              ),
            _QuotePanel(
              quote: _quote,
              error: _quoteError,
              loading: _quoteLoading,
              onUseBuy: (pct) => _fillFromQuote(_buyBelow, pct, roundUp: false),
              onUseSell: (pct) => _fillFromQuote(_sellAbove, pct, roundUp: true),
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

  void _clearQuote() {
    _quote = null;
    _quoteError = null;
  }

  void _clearSelection() {
    _searchDebounce?.cancel();
    _searchSeq++;
    _selected = null;
    _symbol.clear();
    _symbolQuery.clear();
    _results = const [];
    _searching = false;
    _searchError = null;
    _clearQuote();
  }

  void _onQueryChanged(String text) {
    _searchDebounce?.cancel();
    final query = text.trim();
    setState(() {
      _searchError = null;
      if (query.isEmpty) {
        _results = const [];
        _searching = false;
      } else {
        _searching = true;
      }
    });
    if (query.isEmpty) return;
    // 글자를 칠 때마다 요청하지 않도록 잠깐 멈췄을 때만 검색한다.
    _searchDebounce = Timer(const Duration(milliseconds: 300), () => _search(query));
  }

  Future<void> _search(String query) async {
    final seq = ++_searchSeq;
    final assetClass = _assetClass;
    try {
      final results = await ref.read(marketWatchRepositoryProvider).searchSymbols(assetClass.apiValue, query);
      if (!mounted || seq != _searchSeq) return;
      setState(() => _results = results);
    } on DioException catch (e) {
      if (!mounted || seq != _searchSeq) return;
      final detail = e.response?.data is Map ? (e.response!.data as Map)['detail'] : null;
      setState(() {
        _results = const [];
        _searchError = '${detail ?? '종목을 검색하지 못했어요.'}';
      });
    } finally {
      if (mounted && seq == _searchSeq) setState(() => _searching = false);
    }
  }

  void _selectSymbol(SymbolInfo symbol) {
    _searchDebounce?.cancel();
    _searchSeq++;
    setState(() {
      _selected = symbol;
      _symbol.text = symbol.symbol;
      _symbolQuery.text = symbol.label;
      _results = const [];
      _searching = false;
      _clearQuote();
    });
    _formKey.currentState?.validate();
    _lookupQuote(); // 고르자마자 현재가를 보여준다
  }

  Future<void> _lookupQuote() async {
    if (_selected == null) return;
    final symbol = _normalizedSymbol;
    final assetClass = _assetClass;
    setState(() {
      _clearQuote();
      _quoteLoading = true;
    });
    try {
      final quote = await ref.read(marketWatchRepositoryProvider).fetchQuote(assetClass.apiValue, symbol);
      // 조회하는 사이 종목/거래소를 바꿨으면 결과를 버린다.
      if (!mounted || symbol != _normalizedSymbol || assetClass != _assetClass) return;
      setState(() {
        _quote = quote;
        // 수정 화면에서는 저장된 코드만 알고 있으므로 조회된 종목명으로 표시를 채운다.
        final selected = _selected;
        if (selected != null && selected.name == selected.symbol && quote.name != null) {
          _selected = SymbolInfo(symbol: selected.symbol, name: quote.name!, market: selected.market);
          _symbolQuery.text = _selected!.label;
        }
      });
    } on DioException catch (e) {
      final detail = e.response?.data is Map ? (e.response!.data as Map)['detail'] : null;
      if (mounted) setState(() => _quoteError = '${detail ?? '현재가를 불러오지 못했어요.'}');
    } finally {
      if (mounted) setState(() => _quoteLoading = false);
    }
  }

  /// 현재가 대비 pct(%)만큼 떨어진/오른 가격을 입력칸에 채운다. 매수 기준은 내림, 익절 기준은
  /// 올림으로 반올림해 "현재가 -3%"보다 더 비싸게 사거나 "+5%"보다 싸게 팔지 않게 한다.
  void _fillFromQuote(TextEditingController target, double pct, {required bool roundUp}) {
    final quote = _quote;
    if (quote == null) return;
    target.text = _plain(roundQuotePrice(quote.price * (1 + pct / 100), roundUp: roundUp));
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


/// 화면에 넣을 가격 단위: 100원 이상은 원 단위, 그보다 싼 코인은 소수점 4자리.
double roundQuotePrice(double value, {required bool roundUp}) {
  final scale = value >= 100 ? 1.0 : 10000.0;
  final scaled = value * scale;
  return (roundUp ? scaled.ceilToDouble() : scaled.floorToDouble()) / scale;
}

class _QuotePanel extends StatelessWidget {
  const _QuotePanel({
    required this.quote,
    required this.error,
    required this.loading,
    required this.onUseBuy,
    required this.onUseSell,
  });

  final Quote? quote;
  final String? error;
  final bool loading;
  final void Function(double pct) onUseBuy;
  final void Function(double pct) onUseSell;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (loading) {
      return const Padding(
        padding: EdgeInsets.only(top: 12),
        child: LinearProgressIndicator(),
      );
    }
    if (error != null) {
      return Padding(
        padding: const EdgeInsets.only(top: 8, left: 12),
        child: Text(error!, key: const ValueKey('quote-error'), style: TextStyle(color: theme.colorScheme.error)),
      );
    }
    final q = quote;
    if (q == null) return const SizedBox.shrink();

    final rate = q.changeRate;
    final rateColor = rate == null || rate == 0
        ? theme.colorScheme.onSurfaceVariant
        : (rate > 0 ? Colors.red : Colors.blue); // 국내 관례: 상승 빨강, 하락 파랑
    final rateText = rate == null ? '' : ' (${rate > 0 ? '+' : ''}${rate.toStringAsFixed(2)}%)';

    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(q.name ?? q.symbol, key: const ValueKey('quote-name'), style: theme.textTheme.titleMedium),
            const SizedBox(height: 4),
            Text.rich(
              key: const ValueKey('quote-price'),
              TextSpan(children: [
                TextSpan(text: '현재가 ${formatKrw(q.price)}원', style: theme.textTheme.titleLarge),
                TextSpan(text: rateText, style: TextStyle(color: rateColor)),
              ]),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final pct in const [-1.0, -3.0, -5.0])
                  ActionChip(
                    key: ValueKey('use-buy-${pct.toInt()}'),
                    avatar: const Icon(Icons.south, size: 16),
                    label: Text('매수 ${pct.toInt()}%'),
                    onPressed: () => onUseBuy(pct),
                  ),
                for (final pct in const [3.0, 5.0, 10.0])
                  ActionChip(
                    key: ValueKey('use-sell-${pct.toInt()}'),
                    avatar: const Icon(Icons.north, size: 16),
                    label: Text('익절 +${pct.toInt()}%'),
                    onPressed: () => onUseSell(pct),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}


class _SymbolResults extends StatelessWidget {
  const _SymbolResults({
    required this.query,
    required this.results,
    required this.searching,
    required this.error,
    required this.onSelect,
  });

  final String query;
  final List<SymbolInfo> results;
  final bool searching;
  final String? error;
  final ValueChanged<SymbolInfo> onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (query.isEmpty) return const SizedBox.shrink();
    if (error != null) {
      return Padding(
        padding: const EdgeInsets.only(top: 8, left: 12),
        child: Text(error!, style: TextStyle(color: theme.colorScheme.error)),
      );
    }
    if (searching && results.isEmpty) return const SizedBox.shrink();
    if (results.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 8, left: 12),
        child: Text('검색 결과가 없어요.', key: ValueKey('symbol-no-results')),
      );
    }
    return Card(
      key: const ValueKey('symbol-results'),
      margin: const EdgeInsets.only(top: 4),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 320),
        child: ListView(
          shrinkWrap: true,
          padding: EdgeInsets.zero,
          children: [
            for (final s in results)
              ListTile(
                key: ValueKey('symbol-option-${s.symbol}'),
                dense: true,
                title: Text(s.name),
                subtitle: Text(s.market.isEmpty ? s.symbol : '${s.symbol} · ${s.market}'),
                onTap: () => onSelect(s),
              ),
          ],
        ),
      ),
    );
  }
}
