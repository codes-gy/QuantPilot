import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/features/market_watch/data/market_watch_repository.dart';
import 'package:quantpilot/features/strategy/data/strategy_repository.dart';
import 'package:quantpilot/features/strategy/domain/strategy.dart';
import 'package:quantpilot/features/strategy/presentation/strategy_form_screen.dart';

import 'support/fake_market_repository.dart';

class _CapturingRepository implements StrategyRepository {
  final created = <StrategyDraft>[];

  @override
  Future<Strategy> create(StrategyDraft draft) async {
    created.add(draft);
    return Strategy(id: 1, name: draft.name, symbol: draft.symbol, status: StrategyStatus.paused);
  }

  @override
  Future<List<Strategy>> fetchAll() async => const [];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _open(WidgetTester tester, StrategyRepository repo) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        strategyRepositoryProvider.overrideWithValue(repo),
        marketWatchRepositoryProvider.overrideWithValue(FakeMarketRepository()),
      ],
      child: const MaterialApp(home: StrategyFormScreen()),
    ),
  );
}

Future<void> _enter(WidgetTester tester, String key, String text) =>
    tester.enterText(find.byKey(ValueKey(key)), text);

Future<void> _submit(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('submit-strategy')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('stock strategy is submitted as price_threshold rules', (tester) async {
    final repo = _CapturingRepository();
    await _open(tester, repo);

    await searchAndSelect(tester, '삼성', '005930');
    await _enter(tester, 'field-buy', '7,000');
    await _enter(tester, 'field-sell', '7500');
    await tester.pump();
    expect(find.text('7,000원 이하 매수 · 7,500원 이상 매도 · 손절 3% · 1주'), findsOneWidget);

    await _submit(tester);

    expect(repo.created, hasLength(1));
    expect(repo.created.single.toJson(), {
      'name': '삼성전자 가격 전략', // 이름을 비우면 선택한 종목명으로
      'asset_class': 'kr_stock',
      'symbol': '005930',
      'entry_rule': {'type': 'price_threshold', 'below': 7000.0},
      'exit_rule': {'type': 'price_threshold', 'above': 7500.0},
      'max_position_size': 1.0,
      'stop_loss_pct': 0.03,
    });
  });

  testWidgets('invalid input is blocked before anything is sent', (tester) async {
    final repo = _CapturingRepository();
    await _open(tester, repo);

    // 종목을 고르지 않은 채 등록
    await _enter(tester, 'field-buy', '7000');
    await _enter(tester, 'field-sell', '6000');
    await _enter(tester, 'field-stoploss', '150');
    await _submit(tester);

    expect(repo.created, isEmpty);
    expect(find.text('종목을 검색해서 목록에서 선택하세요.'), findsOneWidget);
    expect(find.text('익절 가격은 매수 가격보다 높아야 해요.'), findsOneWidget);
    expect(find.text('0보다 크고 100보다 작은 값을 입력하세요.'), findsOneWidget);
  });

  testWidgets('crypto order below Upbit minimum is rejected', (tester) async {
    final repo = _CapturingRepository();
    await _open(tester, repo);

    await tester.tap(find.text('코인 (업비트)'));
    await tester.pumpAndSettle();
    await searchAndSelect(tester, 'btc', 'KRW-BTC');
    await _enter(tester, 'field-buy', '100000000');
    await _enter(tester, 'field-quantity', '0.00001'); // 1,000원어치
    await _submit(tester);

    expect(repo.created, isEmpty);
    expect(find.text('업비트 최소 주문 금액은 5,000원이에요.'), findsOneWidget);

    await _enter(tester, 'field-quantity', '0.00006'); // 6,000원어치
    await _submit(tester);

    expect(repo.created, hasLength(1));
    final draft = repo.created.single;
    expect(draft.symbol, 'KRW-BTC');
    expect(draft.assetClass, AssetClass.crypto);
    expect(draft.exitRule, isEmpty); // 익절 비우면 손절만
  });

  test('summary formats stock and crypto quantities', () {
    const stock = StrategyDraft(
      name: 'a', assetClass: AssetClass.krStock, symbol: '005930',
      buyBelow: 7000, sellAbove: null, quantity: 2, stopLossPct: 0.025,
    );
    expect(stock.summary, '7,000원 이하 매수 · 손절 2.5% · 2주');

    const coin = StrategyDraft(
      name: 'b', assetClass: AssetClass.crypto, symbol: 'KRW-BTC',
      buyBelow: 100000000, sellAbove: 110000000, quantity: 0.00006, stopLossPct: 0.03,
    );
    expect(coin.summary, '100,000,000원 이하 매수 · 110,000,000원 이상 매도 · 손절 3% · 0.00006개');
  });
}
