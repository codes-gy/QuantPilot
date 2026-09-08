import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/di/providers.dart';
import '../../../core/network/api_client.dart';
import '../domain/price_tick.dart';

class MarketWatchRepository {
  MarketWatchRepository(this._api);

  final ApiClient _api;

  Future<PriceTick> fetchLatestPrice(String assetClass, String symbol) async {
    final response = await _api.dio.get('/market-data/$assetClass/$symbol/price');
    return PriceTick.fromJson(response.data as Map<String, dynamic>);
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
