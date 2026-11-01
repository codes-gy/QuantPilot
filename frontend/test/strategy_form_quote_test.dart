import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/features/market_watch/data/market_watch_repository.dart';
import 'package:quantpilot/features/strategy/presentation/strategy_form_screen.dart';

import 'support/fake_market_repository.dart';

Future<FakeMarketRepository> _open(WidgetTester tester) async {
  tester.view.physicalSize = const Size(800, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  final market = FakeMarketRepository();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [marketWatchRepositoryProvider.overrideWithValue(market)],
      child: const MaterialApp(home: StrategyFormScreen()),
    ),
  );
  return market;
}

String _text(WidgetTester tester, String key) =>
    tester.widget<TextFormField>(find.byKey(ValueKey(key))).controller!.text;

void main() {
  testWidgets('search by name, pick from list, then quote loads automatically', (tester) async {
    final market = await _open(tester);
    await tester.enterText(find.byKey(const ValueKey('field-symbol')), '삼성');
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pumpAndSettle();

    expect(market.searches, ['kr_stock/삼성']); // 디바운스: 한 번만 검색
    expect(find.byKey(const ValueKey('symbol-option-005930')), findsOneWidget);
    expect(find.byKey(const ValueKey('symbol-option-005935')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('symbol-option-005930')));
    await tester.pumpAndSettle();

    expect(_text(tester, 'field-symbol'), '삼성전자 (005930)');
    expect(find.byKey(const ValueKey('symbol-results')), findsNothing);
    expect(market.quoteRequests, ['kr_stock/005930']);
    expect(find.textContaining('현재가 220,500원'), findsOneWidget);
    expect(find.textContaining('-4.96%'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('use-buy--3')));
    await tester.tap(find.byKey(const ValueKey('use-sell-5')));
    await tester.pump();
    expect(_text(tester, 'field-buy'), '213885'); // 220,500 x 0.97, 내림
    expect(_text(tester, 'field-sell'), '231525'); // 220,500 x 1.05, 올림
  });

  testWidgets('new alphanumeric stock code can be found by name', (tester) async {
    await _open(tester);
    await searchAndSelect(tester, '덕양', '0001A0');
    expect(_text(tester, 'field-symbol'), '덕양에너젠 (0001A0)');
    expect(find.textContaining('현재가 7,120원'), findsOneWidget);
  });

  testWidgets('no results message', (tester) async {
    await _open(tester);
    await tester.enterText(find.byKey(const ValueKey('field-symbol')), '없는회사');
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('symbol-no-results')), findsOneWidget);
  });

  testWidgets('quote failure shows server message', (tester) async {
    await _open(tester);
    await searchAndSelect(tester, '시세없는', '999999');
    expect(find.text('종목코드를 찾을 수 없어요: 999999'), findsOneWidget);
    expect(find.byKey(const ValueKey('quote-price')), findsNothing);
  });

  testWidgets('clearing the selection resets symbol and quote', (tester) async {
    await _open(tester);
    await searchAndSelect(tester, '삼성', '005930');
    expect(find.text('삼성전자'), findsOneWidget); // 현재가 카드의 종목명

    await tester.tap(find.byKey(const ValueKey('clear-symbol')));
    await tester.pumpAndSettle();
    expect(_text(tester, 'field-symbol'), '');
    expect(find.byKey(const ValueKey('quote-price')), findsNothing);
  });

  testWidgets('switching to coins searches Upbit markets and keeps decimals', (tester) async {
    final market = await _open(tester);
    await tester.tap(find.text('코인 (업비트)'));
    await tester.pumpAndSettle();
    await searchAndSelect(tester, '비토르', 'KRW-VTHO');

    expect(market.searches, ['crypto/비토르']);
    await tester.tap(find.byKey(const ValueKey('use-buy--5')));
    await tester.pump();
    expect(_text(tester, 'field-buy'), '0.7231'); // 0.7612 x 0.95 = 0.72314, 내림
  });

  test('roundQuotePrice rounds buy down and sell up', () {
    expect(roundQuotePrice(213885.4, roundUp: false), 213885);
    expect(roundQuotePrice(231524.1, roundUp: true), 231525);
    expect(roundQuotePrice(0.72314, roundUp: false), 0.7231);
    expect(roundQuotePrice(0.72314, roundUp: true), 0.7232);
  });
}
