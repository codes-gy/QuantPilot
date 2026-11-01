import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/features/strategy/data/strategy_repository.dart';
import 'package:quantpilot/features/strategy/domain/strategy.dart';
import 'package:quantpilot/features/strategy/presentation/strategy_list_screen.dart';

class _RecordingStrategyRepository implements StrategyRepository {
  _RecordingStrategyRepository(this._status);

  StrategyStatus _status;
  final calls = <String>[];

  Strategy get _current => Strategy(id: 1, name: '테스트 전략', symbol: '005930', status: _status);

  @override
  Future<List<Strategy>> fetchAll() async => [_current];

  @override
  Future<Strategy> activate(int id) async {
    calls.add('activate:$id');
    _status = StrategyStatus.active;
    return _current;
  }

  @override
  Future<Strategy> pause(int id) async {
    calls.add('pause:$id');
    _status = StrategyStatus.paused;
    return _current;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pump(WidgetTester tester, StrategyRepository repo) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [strategyRepositoryProvider.overrideWithValue(repo)],
      child: const MaterialApp(home: StrategyListScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('turning a strategy on asks for confirmation, then activates it', (tester) async {
    final repo = _RecordingStrategyRepository(StrategyStatus.paused);
    await _pump(tester, repo);
    expect(find.textContaining('일시정지'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('strategy-switch-1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('실제 돈으로'), findsOneWidget);

    await tester.tap(find.text('켜기'));
    await tester.pumpAndSettle();
    expect(repo.calls, ['activate:1']);
    expect(find.textContaining('실행 중'), findsOneWidget);
  });

  testWidgets('cancelling the confirmation does not change the strategy', (tester) async {
    final repo = _RecordingStrategyRepository(StrategyStatus.paused);
    await _pump(tester, repo);

    await tester.tap(find.byKey(const ValueKey('strategy-switch-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();

    expect(repo.calls, isEmpty);
    expect(find.textContaining('일시정지'), findsOneWidget);
  });

  testWidgets('turning a running strategy off pauses it', (tester) async {
    final repo = _RecordingStrategyRepository(StrategyStatus.active);
    await _pump(tester, repo);

    await tester.tap(find.byKey(const ValueKey('strategy-switch-1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('손절/익절 감시도'), findsOneWidget);
    await tester.tap(find.text('끄기'));
    await tester.pumpAndSettle();

    expect(repo.calls, ['pause:1']);
    expect(find.textContaining('일시정지'), findsOneWidget);
  });
}
