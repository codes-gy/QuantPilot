import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/dashboard_repository.dart';
import '../domain/daily_pnl_status.dart';
import '../domain/position_summary.dart';

/// 앱 첫 화면. 자산 요약과 함께 "비상 정지" 버튼을 항상 눈에 띄게 노출한다 —
/// 자동매매 서비스의 가장 중요한 안전장치이므로 메뉴 깊숙이 숨기지 않는다.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final killSwitchAsync = ref.watch(killSwitchStatusProvider);
    final dailyPnlAsync = ref.watch(dailyPnlProvider);
    final positionsAsync = ref.watch(positionsSummaryProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('QuantPilot')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(killSwitchStatusProvider);
          ref.invalidate(dailyPnlProvider);
          ref.invalidate(positionsSummaryProvider);
          await Future.wait([
            ref.read(killSwitchStatusProvider.future),
            ref.read(dailyPnlProvider.future),
            ref.read(positionsSummaryProvider.future),
          ]);
        },
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            killSwitchAsync.when(
              data: (engaged) => engaged
                  ? Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: _KillSwitchBanner(onRelease: () => _release(context, ref)),
                    )
                  : const SizedBox.shrink(),
              loading: () => const SizedBox.shrink(),
              error: (_, __) => const SizedBox.shrink(),
            ),
            _DailyPnlCard(async: dailyPnlAsync),
            const SizedBox(height: 24),
            Text('보유 포지션', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            _PositionsSection(async: positionsAsync),
            const SizedBox(height: 80), // FAB에 가리지 않도록 여백
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: Colors.red,
        icon: const Icon(Icons.stop_circle),
        label: const Text('비상 정지'),
        onPressed: () => _confirmAndEngage(context, ref),
      ),
    );
  }

  Future<void> _confirmAndEngage(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('비상 정지'),
        content: const Text('모든 자동매매 신규 주문이 즉시 차단됩니다. 계속할까요?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('정지')),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(dashboardRepositoryProvider).engageKillSwitch('user_manual_stop');
      ref.invalidate(killSwitchStatusProvider);
    }
  }

  Future<void> _release(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('비상 정지 해제'),
        content: const Text('자동매매 신규 주문이 다시 허용됩니다. 계속할까요?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('해제')),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(dashboardRepositoryProvider).releaseKillSwitch();
      ref.invalidate(killSwitchStatusProvider);
    }
  }
}

class _KillSwitchBanner extends StatelessWidget {
  const _KillSwitchBanner({required this.onRelease});

  final VoidCallback onRelease;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: ListTile(
        leading: Icon(Icons.warning_amber, color: Theme.of(context).colorScheme.error),
        title: const Text('비상 정지가 발동 중이에요'),
        subtitle: const Text('신규 주문이 모두 차단되고 있어요.'),
        trailing: TextButton(onPressed: onRelease, child: const Text('해제')),
      ),
    );
  }
}

class _DailyPnlCard extends StatelessWidget {
  const _DailyPnlCard({required this.async});

  final AsyncValue<DailyPnlStatus> async;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: async.when(
          data: (status) {
            final isLoss = status.realizedPnlKrw < 0;
            final color = isLoss ? Colors.red : Colors.blue;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('오늘 실현손익', style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 4),
                Text(
                  '${status.realizedPnlKrw.toStringAsFixed(0)}원',
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(color: color, fontWeight: FontWeight.bold),
                ),
                if (status.dailyLossLimitKrw != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    '일일 손실 한도: -${status.dailyLossLimitKrw!.toStringAsFixed(0)}원',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            );
          },
          loading: () => const SizedBox(
            height: 60,
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (err, _) => Text('손익 조회 실패: $err'),
        ),
      ),
    );
  }
}

class _PositionsSection extends StatelessWidget {
  const _PositionsSection({required this.async});

  final AsyncValue<List<PositionSummary>> async;

  @override
  Widget build(BuildContext context) {
    return async.when(
      data: (positions) {
        if (positions.isEmpty) {
          return const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Text('보유 중인 포지션이 없어요.'),
          );
        }
        return Column(
          children: positions
              .map(
                (p) => Card(
                  child: ListTile(
                    title: Text(p.symbol),
                    subtitle: Text('평단가 ${p.avgEntryPrice.toStringAsFixed(0)}원'),
                    trailing: Text('${p.quantity.toStringAsFixed(0)}주'),
                  ),
                ),
              )
              .toList(),
        );
      },
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: 16),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (err, _) => Text('포지션 조회 실패: $err'),
    );
  }
}
