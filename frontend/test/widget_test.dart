import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/core/auth/auth_state_provider.dart';
import 'package:quantpilot/features/dashboard/data/dashboard_repository.dart';
import 'package:quantpilot/features/dashboard/domain/daily_pnl_status.dart';
import 'package:quantpilot/features/dashboard/domain/position_summary.dart';
import 'package:quantpilot/features/orders/data/orders_repository.dart';
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

/// 주문 탭도 IndexedStack에서 즉시 build되므로 실제 GET /orders 호출을 막는다.
class _FakeOrdersRepository implements OrdersRepository {
  @override
  dynamic noSuchMethod(Invocation invocation) {
    if (invocation.memberName == #fetchAll) return Future.value(<Never>[]);
    return super.noSuchMethod(invocation);
  }
}

/// 저장된 토큰이 있는 것처럼 응답하는 secureStorage 대체 — 실제 플랫폼 저장소에 접근하지 않는다.
class _TokenStorage implements FlutterSecureStorage {
  @override
  dynamic noSuchMethod(Invocation invocation) {
    if (invocation.memberName == #read) return Future<String?>.value('test-token');
    return super.noSuchMethod(invocation);
  }
}

/// 로그인 여부를 즉시 authenticated로 고정해, 이 위젯 테스트가 로그인 화면이 아니라
/// RootShell(대시보드 탭)을 바로 렌더링하게 한다. provider 타입(AuthStateNotifier)과
/// 맞아야 overrideWith가 허용되므로 실제 notifier를 상속한다.
class _FakeAuthStateNotifier extends AuthStateNotifier {
  _FakeAuthStateNotifier() : super(_TokenStorage()) {
    state = AuthStatus.authenticated;
  }
}

Widget _app() => ProviderScope(
      overrides: [
        strategyRepositoryProvider.overrideWithValue(_FakeStrategyRepository()),
        dashboardRepositoryProvider.overrideWithValue(_FakeDashboardRepository()),
        ordersRepositoryProvider.overrideWithValue(_FakeOrdersRepository()),
        authStateProvider.overrideWith((ref) => _FakeAuthStateNotifier()),
      ],
      child: const QuantPilotApp(),
    );

Future<void> _pumpAt(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(_app());
  await tester.pump();
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
          ordersRepositoryProvider.overrideWithValue(_FakeOrdersRepository()),
          authStateProvider.overrideWith((ref) => _FakeAuthStateNotifier()),
        ],
        child: const QuantPilotApp(),
      ),
    );
    await tester.pump();

    expect(find.text('QuantPilot'), findsOneWidget);
    expect(find.text('비상 정지'), findsOneWidget);
  });

  testWidgets('phone width uses bottom navigation bar', (WidgetTester tester) async {
    await _pumpAt(tester, const Size(400, 800));
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
  });

  testWidgets('PC width uses side navigation rail', (WidgetTester tester) async {
    await _pumpAt(tester, const Size(1440, 900));
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.text('비상 정지'), findsOneWidget);
  });
}
