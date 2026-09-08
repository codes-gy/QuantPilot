import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/dashboard_repository.dart';

/// 앱 첫 화면. 자산 요약과 함께 "비상 정지" 버튼을 항상 눈에 띄게 노출한다 —
/// 자동매매 서비스의 가장 중요한 안전장치이므로 메뉴 깊숙이 숨기지 않는다.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('QuantPilot')),
      body: const Center(child: Text('계좌 요약 / 손익 위젯 자리')),
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
    }
  }
}
