import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/di/providers.dart';
import '../../../core/network/api_client.dart';

class DashboardRepository {
  DashboardRepository(this._api);

  final ApiClient _api;

  Future<bool> isKillSwitchEngaged() async {
    final response = await _api.dio.get('/risk/kill-switch');
    return response.data['engaged'] as bool;
  }

  Future<void> engageKillSwitch(String reason) async {
    await _api.dio.post('/risk/kill-switch/engage', data: {'reason': reason});
  }

  Future<void> releaseKillSwitch() async {
    await _api.dio.post('/risk/kill-switch/release');
  }
}

final dashboardRepositoryProvider = Provider(
  (ref) => DashboardRepository(ref.watch(apiClientProvider)),
);
