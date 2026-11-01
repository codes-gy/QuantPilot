import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quantpilot/features/strategy/data/strategy_repository.dart';
import 'package:quantpilot/features/strategy/domain/strategy.dart';
import 'package:quantpilot/features/strategy/presentation/strategy_form_screen.dart';
import 'package:quantpilot/features/strategy/presentation/strategy_list_screen.dart';

const _paused = Strategy(
  id: 7,
  name: '삼성 저가매수',
  symbol: '005930',
  status: StrategyStatus.paused,
  assetClass: AssetClass.krStock,
  entryRule: {'type': 'price_threshold', 'below': 7000},
  exitRule: {'type': 'price_threshold', 'above': 7500},
  maxPositionSize: 1,
  stopLossPct: 0.03,
);

class _FakeRepository implements StrategyRepository {
  _FakeRepository(List<Strategy> items) : _items = [...items];

  final List<Strategy> _items;
  final updates = <(int, StrategyDraft)>[];
  final deletes = <int>[];

  @override
  Future<List<Strategy>> fetchAll() async => List.of(_items);

  @override
  Future<Strategy> update(int id, StrategyDraft draft) async {
    updates.add((id, draft));
    return _paused;
  }

  @override
  Future<void> delete(int id) async {
    deletes.add(id);
    _items.removeWhere((s) => s.id == id);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pump(WidgetTester tester, StrategyRepository repo, Widget home) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [strategyRepositoryProvider.overrideWithValue(repo)],
      child: MaterialApp(home: home),
    ),
  );
  await tester.pumpAndSettle();
}

String _fieldText(WidgetTester tester, String key) =>
    tester.widget<TextFormField>(find.byKey(ValueKey(key))).controller!.text;

void main() {
  testWidgets('edit form is prefilled and saves with PUT semantics', (tester) async {
    final repo = _FakeRepository([_paused]);
    await _pump(tester, repo, const StrategyFormScreen(initial: _paused));

    expect(find.text('전략 수정'), findsOneWidget);
    expect(_fieldText(tester, 'field-symbol'), '005930');
    expect(_fieldText(tester, 'field-buy'), '7000');
    expect(_fieldText(tester, 'field-sell'), '7500');
    expect(_fieldText(tester, 'field-quantity'), '1');
    expect(_fieldText(tester, 'field-stoploss'), '3');
    expect(_fieldText(tester, 'field-name'), '삼성 저가매수');

    await tester.enterText(find.byKey(const ValueKey('field-buy')), '6800');
    await tester.tap(find.byKey(const ValueKey('submit-strategy')));
    await tester.pumpAndSettle();

    expect(repo.updates, hasLength(1));
    final (id, draft) = repo.updates.single;
    expect(id, 7);
    expect(draft.entryRule, {'type': 'price_threshold', 'below': 6800.0});
    expect(draft.exitRule, {'type': 'price_threshold', 'above': 7500.0});
    expect(draft.name, '삼성 저가매수');
  });

  testWidgets('paused strategy can be deleted after confirmation', (tester) async {
    final repo = _FakeRepository([_paused]);
    await _pump(tester, repo, const StrategyListScreen());

    await tester.tap(find.text('삼성 저가매수'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('action-delete')));
    await tester.pumpAndSettle();
    expect(find.textContaining('되돌릴 수 없어요'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, '삭제'));
    await tester.pumpAndSettle();

    expect(repo.deletes, [7]);
    expect(find.text('삼성 저가매수'), findsNothing);
  });

  testWidgets('running strategy cannot be edited or deleted', (tester) async {
    const running = Strategy(
      id: 8,
      name: '실행 중 전략',
      symbol: 'KRW-BTC',
      status: StrategyStatus.active,
      assetClass: AssetClass.crypto,
      entryRule: {'type': 'price_threshold', 'below': 100000000},
      maxPositionSize: 0.0001,
      stopLossPct: 0.03,
    );
    final repo = _FakeRepository([running]);
    await _pump(tester, repo, const StrategyListScreen());

    await tester.tap(find.text('실행 중 전략'));
    await tester.pumpAndSettle();
    expect(find.textContaining('먼저 꺼 주세요'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('action-delete')));
    await tester.tap(find.byKey(const ValueKey('action-edit')));
    await tester.pumpAndSettle();

    expect(repo.deletes, isEmpty);
    expect(repo.updates, isEmpty);
    expect(find.byType(StrategyFormScreen), findsNothing);
  });

  test('only price_threshold strategies are editable in the form', () {
    expect(_paused.isEditableInForm, isTrue);
    const maCross = Strategy(
      id: 1,
      name: 'ma',
      symbol: '005930',
      status: StrategyStatus.paused,
      entryRule: {'type': 'ma_cross', 'fast': 5, 'slow': 20},
    );
    expect(maCross.isEditableInForm, isFalse);
  });
}
