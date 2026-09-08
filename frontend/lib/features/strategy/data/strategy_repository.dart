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
}

final strategyRepositoryProvider = Provider(
  (ref) => StrategyRepository(ref.watch(apiClientProvider)),
);

final strategyListProvider = FutureProvider(
  (ref) => ref.watch(strategyRepositoryProvider).fetchAll(),
);
