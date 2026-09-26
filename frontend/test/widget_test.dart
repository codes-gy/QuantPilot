import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/core/auth/auth_state_provider.dart';
import 'package:quantpilot/features/strategy/data/strategy_repository.dart';
import 'package:quantpilot/features/strategy/domain/strategy.dart';
import 'package:quantpilot/main.dart';

class _FakeStrategyRepository implements StrategyRepository {
  @override
  Future<List<Strategy>> fetchAll() async => const [];
}

/// 로그인 여부를 secureStorage 비동기 조회 없이 즉시 authenticated로 고정해,
/// 이 위젯 테스트가 로그인 화면이 아니라 RootShell(대시보드 탭)을 바로 렌더링하게 한다.
class _FakeAuthStateNotifier extends StateNotifier<AuthStatus> {
  _FakeAuthStateNotifier() : super(AuthStatus.authenticated);
}

void main() {
  testWidgets('app renders the dashboard tab shell when authenticated', (WidgetTester tester) async {
    // IndexedStack이 모든 탭을 즉시 build하므로, 전략 탭의 실제 네트워크 호출을
    // 위젯 테스트에서는 fake로 대체해 배지 없는 pending timer를 피한다.
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          strategyRepositoryProvider.overrideWithValue(_FakeStrategyRepository()),
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
