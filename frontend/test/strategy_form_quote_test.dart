import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/features/market_watch/data/market_watch_repository.dart';
import 'package:quantpilot/features/market_watch/domain/quote.dart';
import 'package:quantpilot/features/strategy/presentation/strategy_form_screen.dart';

class _FakeMarketRepository implements MarketWatchRepository {
  final requests = <String>[];

  @override
  Future<Quote> fetchQuote(String assetClass, String symbol) async {
    requests.add('$assetClass/$symbol');
    if (symbol == '999999') {
      final options = RequestOptions(path: '/market-data/$assetClass/$symbol/quote');
      throw DioException(
        requestOptions: options,
        response: Response(requestOptions: options, statusCode: 404, data: {'detail': '종목코드를 찾을 수 없어요: 999999'}),
      );
    }
    if (assetClass == 'crypto') {
      return const Quote(symbol: 'KRW-VTHO', name: '비토르토큰', price: 0.7612, changeRate: 1.2);
    }
    return const Quote(symbol: '005930', name: '삼성전자', price: 220500, changeRate: -4.96);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<_FakeMarketRepository> _open(WidgetTester tester) async {
  tester.view.physicalSize = const Size(800, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  final market = _FakeMarketRepository();
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

Future<void> _lookup(WidgetTester tester, String symbol) async {
  await tester.enterText(find.byKey(const ValueKey('field-symbol')), symbol);
  await tester.pump();
  await tester.tap(find.byKey(const ValueKey('lookup-quote')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('lookup shows name, price and change rate, chips fill prices', (tester) async {
    final market = await _open(tester);
    await _lookup(tester, '005930');

    expect(market.requests, ['kr_stock/005930']);
    expect(find.text('삼성전자'), findsOneWidget);
    expect(find.textContaining('현재가 220,500원'), findsOneWidget);
    expect(find.textContaining('-4.96%'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('use-buy--3')));
    await tester.tap(find.byKey(const ValueKey('use-sell-5')));
    await tester.pump();
    expect(_text(tester, 'field-buy'), '213885'); // 220,500 x 0.97, 내림
    expect(_text(tester, 'field-sell'), '231525'); // 220,500 x 1.05, 올림
  });

  testWidgets('lookup button is disabled until the symbol format is valid', (tester) async {
    final market = await _open(tester);
    await tester.enterText(find.byKey(const ValueKey('field-symbol')), '0059');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('lookup-quote')));
    await tester.pumpAndSettle();
    expect(market.requests, isEmpty);
  });

  testWidgets('unknown symbol shows server message', (tester) async {
    await _open(tester);
    await _lookup(tester, '999999');
    expect(find.text('종목코드를 찾을 수 없어요: 999999'), findsOneWidget);
    expect(find.byKey(const ValueKey('quote-price')), findsNothing);
  });

  testWidgets('changing the symbol clears the previous quote', (tester) async {
    await _open(tester);
    await _lookup(tester, '005930');
    expect(find.text('삼성전자'), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('field-symbol')), '00066');
    await tester.pump();
    expect(find.text('삼성전자'), findsNothing);
  });

  testWidgets('cheap coins keep decimal precision', (tester) async {
    final market = await _open(tester);
    await tester.tap(find.text('코인 (업비트)'));
    await tester.pumpAndSettle();
    await _lookup(tester, 'krw-vtho');

    expect(market.requests, ['crypto/KRW-VTHO']);
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
