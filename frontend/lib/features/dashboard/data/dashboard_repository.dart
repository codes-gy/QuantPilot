import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/di/providers.dart';
import '../../../core/network/api_client.dart';
import '../domain/daily_pnl_status.dart';
import '../domain/position_summary.dart';

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

  Future<DailyPnlStatus> fetchDailyPnl() async {
    final response = await _api.dio.get('/risk/daily-pnl');
    return DailyPnlStatus.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<PositionSummary>> fetchPositions() async {
    final response = await _api.dio.get('/positions');
    return (response.data as List).map((e) => PositionSummary.fromJson(e as Map<String, dynamic>)).toList();
  }
}

final dashboardRepositoryProvider = Provider(
  (ref) => DashboardRepository(ref.watch(apiClientProvider)),
);

final killSwitchStatusProvider = FutureProvider.autoDispose(
  (ref) => ref.watch(dashboardRepositoryProvider).isKillSwitchEngaged(),
);

final dailyPnlProvider = FutureProvider.autoDispose(
  (ref) => ref.watch(dashboardRepositoryProvider).fetchDailyPnl(),
);

final positionsSummaryProvider = FutureProvider.autoDispose(
  (ref) => ref.watch(dashboardRepositoryProvider).fetchPositions(),
);
