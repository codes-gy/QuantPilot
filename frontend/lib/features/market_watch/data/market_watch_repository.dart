import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/di/providers.dart';
import '../../../core/network/api_client.dart';
import '../domain/price_tick.dart';
import '../domain/quote.dart';
import '../domain/symbol_info.dart';

class MarketWatchRepository {
  MarketWatchRepository(this._api);

  final ApiClient _api;

  Future<PriceTick> fetchLatestPrice(String assetClass, String symbol) async {
    final response = await _api.dio.get('/market-data/$assetClass/$symbol/price');
    return PriceTick.fromJson(response.data as Map<String, dynamic>);
  }

  /// 증권사/거래소에 직접 현재가와 종목명을 조회한다. 시세 캐시(fetchLatestPrice)는 켜진
  /// 전략의 종목만 들어 있어서, 전략을 등록하기 전에는 이걸 쓴다. 없는 종목이면 404.
  Future<Quote> fetchQuote(String assetClass, String symbol) async {
    final response = await _api.dio.get('/market-data/$assetClass/$symbol/quote');
    return Quote.fromJson(response.data as Map<String, dynamic>);
  }

  /// 종목명 또는 코드 일부로 검색한다 (주식: KIS 종목 마스터, 코인: 업비트 원화 마켓).
  Future<List<SymbolInfo>> searchSymbols(String assetClass, String query, {int limit = 20}) async {
    final response = await _api.dio.get(
      '/market-data/$assetClass/symbols',
      queryParameters: {'q': query, 'limit': limit},
    );
    return (response.data as List).map((e) => SymbolInfo.fromJson(e as Map<String, dynamic>)).toList();
  }
}

final marketWatchRepositoryProvider = Provider(
  (ref) => MarketWatchRepository(ref.watch(apiClientProvider)),
);

/// 백엔드 WebSocket 릴레이를 구독해 심볼별 최신 틱을 실시간으로 흘려보낸다.
final priceTickStreamProvider = StreamProvider.family<PriceTick, String>((ref, symbol) {
  final ws = ref.watch(liveWsClientProvider);
  return ws.stream
      .where((event) => event['type'] == 'price' && event['symbol'] == symbol)
      .map(PriceTick.fromJson);
});
