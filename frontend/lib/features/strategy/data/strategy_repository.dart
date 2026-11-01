import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/di/providers.dart';
import '../../../core/network/api_client.dart';
import '../domain/strategy.dart';

class StrategyRepository {
  StrategyRepository(this._api);

  final ApiClient _api;

  Future<List<Strategy>> fetchAll() async {
    final response = await _api.dio.get('/strategies');
    return (response.data as List).map((e) => Strategy.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// 전략을 켠다. 설정이 잘못돼 있으면 서버가 422와 함께 이유(detail)를 돌려준다.
  Future<Strategy> activate(int id) => _setStatus(id, 'activate');

  /// 전략을 끈다. 신규 주문뿐 아니라 보유 포지션의 손절/익절 감시도 멈춘다.
  Future<Strategy> pause(int id) => _setStatus(id, 'pause');

  Future<Strategy> _setStatus(int id, String action) async {
    final response = await _api.dio.post('/strategies/$id/$action');
    return Strategy.fromJson(response.data as Map<String, dynamic>);
  }
}

final strategyRepositoryProvider = Provider(
  (ref) => StrategyRepository(ref.watch(apiClientProvider)),
);

final strategyListProvider = FutureProvider(
  (ref) => ref.watch(strategyRepositoryProvider).fetchAll(),
);
