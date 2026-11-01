import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/strategy_repository.dart';
import '../domain/strategy.dart';
import 'strategy_form_screen.dart';

class StrategyListScreen extends ConsumerWidget {
  const StrategyListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strategies = ref.watch(strategyListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('내 전략')),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(strategyListProvider.future),
        child: strategies.when(
          data: (list) => list.isEmpty
              ? ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  children: const [
                    Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: Text('등록된 전략이 없어요.\n오른쪽 아래 [전략 추가]로 만들어 보세요.', textAlign: TextAlign.center)),
                    ),
                  ],
                )
              : ListView.builder(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.only(bottom: 88), // 전략 추가 버튼에 마지막 항목이 가리지 않도록
                  itemCount: list.length,
                  itemBuilder: (context, i) => _StrategyTile(strategy: list[i]),
                ),
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (err, _) => Center(child: Text('불러오기 실패: $err')),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        key: const ValueKey('add-strategy'),
        icon: const Icon(Icons.add),
        label: const Text('전략 추가'),
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute<bool>(builder: (_) => const StrategyFormScreen()),
        ),
      ),
    );
  }
}

class _StrategyTile extends ConsumerStatefulWidget {
  const _StrategyTile({required this.strategy});

  final Strategy strategy;

  @override
  ConsumerState<_StrategyTile> createState() => _StrategyTileState();
}

class _StrategyTileState extends ConsumerState<_StrategyTile> {
  bool _busy = false;

  static const _statusLabel = {
    StrategyStatus.active: '실행 중',
    StrategyStatus.paused: '일시정지',
    StrategyStatus.stopped: '중지됨',
  };

  @override
  Widget build(BuildContext context) {
    final s = widget.strategy;
    final active = s.status == StrategyStatus.active;

    return ListTile(
      title: Text(s.name),
      subtitle: Text('${s.symbol} · ${_statusLabel[s.status]}\n${s.summary}'),
      isThreeLine: true,
      trailing: _busy
          ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
          : Switch(
              key: ValueKey('strategy-switch-${s.id}'),
              value: active,
              onChanged: (on) => _toggle(on),
            ),
    );
  }

  Future<void> _toggle(bool on) async {
    final s = widget.strategy;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(on ? '전략 켜기' : '전략 끄기'),
        content: Text(
          on
              ? '"${s.name}"(${s.symbol}) 전략이 조건을 만족하면 실제 돈으로 자동 주문이 나갑니다. 켤까요?'
              : '"${s.name}" 전략의 신규 주문이 멈춥니다. 이미 보유한 포지션의 손절/익절 감시도 함께 멈추니 주의하세요. 끌까요?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(on ? '켜기' : '끄기')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busy = true);
    try {
      final repo = ref.read(strategyRepositoryProvider);
      await (on ? repo.activate(s.id) : repo.pause(s.id));
      ref.invalidate(strategyListProvider);
    } on DioException catch (e) {
      final detail = e.response?.data is Map ? (e.response!.data as Map)['detail'] : null;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${on ? '켜기' : '끄기'} 실패: ${detail ?? e.message}')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}
