import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/features/market_watch/data/market_watch_repository.dart';
import 'package:quantpilot/features/market_watch/domain/quote.dart';
import 'package:quantpilot/features/market_watch/domain/symbol_info.dart';

/// 종목 검색/현재가 조회를 네트워크 없이 흉내 내는 가짜 저장소.
class FakeMarketRepository implements MarketWatchRepository {
  static const stocks = [
    SymbolInfo(symbol: '005930', name: '삼성전자', market: 'KOSPI'),
    SymbolInfo(symbol: '005935', name: '삼성전자우', market: 'KOSPI'),
    SymbolInfo(symbol: '0001A0', name: '덕양에너젠', market: 'KOSDAQ'),
    SymbolInfo(symbol: '999999', name: '시세없는종목', market: 'KOSPI'),
  ];
  static const coins = [
    SymbolInfo(symbol: 'KRW-BTC', name: '비트코인', market: 'UPBIT'),
    SymbolInfo(symbol: 'KRW-VTHO', name: '비토르토큰', market: 'UPBIT'),
  ];
  static const quotes = {
    '005930': Quote(symbol: '005930', name: '삼성전자', price: 220500, changeRate: -4.96),
    '0001A0': Quote(symbol: '0001A0', name: '덕양에너젠', price: 7120, changeRate: 1.5),
    'KRW-BTC': Quote(symbol: 'KRW-BTC', name: '비트코인', price: 100000000, changeRate: -0.15),
    'KRW-VTHO': Quote(symbol: 'KRW-VTHO', name: '비토르토큰', price: 0.7612, changeRate: 1.2),
  };

  final searches = <String>[];
  final quoteRequests = <String>[];

  @override
  Future<List<SymbolInfo>> searchSymbols(String assetClass, String query, {int limit = 20}) async {
    searches.add('$assetClass/$query');
    final pool = assetClass == 'crypto' ? coins : stocks;
    final q = query.toUpperCase();
    return pool.where((s) => s.name.contains(query) || s.symbol.contains(q)).toList();
  }

  @override
  Future<Quote> fetchQuote(String assetClass, String symbol) async {
    quoteRequests.add('$assetClass/$symbol');
    final quote = quotes[symbol];
    if (quote == null) {
      final options = RequestOptions(path: '/market-data/$assetClass/$symbol/quote');
      throw DioException(
        requestOptions: options,
        response: Response(requestOptions: options, statusCode: 404, data: {'detail': '종목코드를 찾을 수 없어요: $symbol'}),
      );
    }
    return quote;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 검색칸에 입력 -> 디바운스(300ms) 대기 -> 결과 목록에서 [symbol]을 고른다.
Future<void> searchAndSelect(WidgetTester tester, String query, String symbol) async {
  await tester.enterText(find.byKey(const ValueKey('field-symbol')), query);
  await tester.pump(const Duration(milliseconds: 350));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(ValueKey('symbol-option-$symbol')));
  await tester.pumpAndSettle();
}
