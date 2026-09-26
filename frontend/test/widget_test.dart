import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/core/auth/auth_state_provider.dart';
import 'package:quantpilot/features/dashboard/data/dashboard_repository.dart';
import 'package:quantpilot/features/dashboard/domain/daily_pnl_status.dart';
import 'package:quantpilot/features/dashboard/domain/position_summary.dart';
import 'package:quantpilot/features/strategy/data/strategy_repository.dart';
import 'package:quantpilot/features/strategy/domain/strategy.dart';
import 'package:quantpilot/main.dart';

class _FakeStrategyRepository implements StrategyRepository {
  @override
  Future<List<Strategy>> fetchAll() async => const [];
}

/// 대시보드가 실제 REST 호출(kill switch 상태/오늘 손익/포지션)을 하지 않도록 대체한다 —
/// 전략 탭과 동일한 이유로, 위젯 테스트에서 진짜 네트워크 요청이 나가면 안 된다.
class _FakeDashboardRepository implements DashboardRepository {
  @override
  Future<bool> isKillSwitchEngaged() async => false;

  @override
  Future<void> engageKillSwitch(String reason) async {}

  @override
  Future<void> releaseKillSwitch() async {}

  @override
  Future<DailyPnlStatus> fetchDailyPnl() async =>
      const DailyPnlStatus(realizedPnlKrw: 0, dailyLossLimitKrw: null);

  @override
  Future<List<PositionSummary>> fetchPositions() async => const [];
}

/// 로그인 여부를 secureStorage 비동기 조회 없이 즉시 authenticated로 고정해,
/// 이 위젯 테스트가 로그인 화면이 아니라 RootShell(대시보드 탭)을 바로 렌더링하게 한다.
class _FakeAuthStateNotifier extends StateNotifier<AuthStatus> {
  _FakeAuthStateNotifier() : super(AuthStatus.authenticated);
}

void main() {
  testWidgets('app renders the dashboard tab shell when authenticated', (WidgetTester tester) async {
    // IndexedStack이 모든 탭을 즉시 build하므로, 전략/대시보드 탭의 실제 네트워크 호출을
    // 위젯 테스트에서는 fake로 대체해 배지 없는 pending timer를 피한다.
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          strategyRepositoryProvider.overrideWithValue(_FakeStrategyRepository()),
          dashboardRepositoryProvider.overrideWithValue(_FakeDashboardRepository()),
          authStateProvider.overrideWith((ref) => _FakeAuthStateNotifier()),
        ],
        child: const QuantPilotApp(),
      ),
    );
    await tester.pump();

    expect(find.text('QuantPilot'), findsOneWidget);
    expect(find.text('비상 정지'), findsOneWidget);
  });
}
