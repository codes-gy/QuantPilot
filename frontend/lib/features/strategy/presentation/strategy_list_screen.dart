import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/strategy_repository.dart';

class StrategyListScreen extends ConsumerWidget {
  const StrategyListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strategies = ref.watch(strategyListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('내 전략')),
      body: strategies.when(
        data: (list) => ListView.builder(
          itemCount: list.length,
          itemBuilder: (context, i) => ListTile(
            title: Text(list[i].name),
            subtitle: Text(list[i].symbol),
            trailing: Text(list[i].status.name),
          ),
        ),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, _) => Center(child: Text('불러오기 실패: $err')),
      ),
      // TODO: 전략 생성/수정 화면으로 이동하는 FloatingActionButton
    );
  }
}
