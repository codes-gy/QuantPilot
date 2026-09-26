import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/auth_state_provider.dart';

// TODO: settings/data, settings/domain — 모의/실전 표시 배지, 증권사 API 키 등록,
// 알림 채널 설정 등. TRADING_MODE는 백엔드 .env에서만 전환하며 앱에서는 조회만 노출한다.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('설정')),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('현재 거래 모드 표시(모의/실전) 및 계정 설정 자리'),
            const SizedBox(height: 24),
            OutlinedButton.icon(
              onPressed: () => ref.read(authStateProvider.notifier).logout(),
              icon: const Icon(Icons.logout),
              label: const Text('로그아웃'),
            ),
          ],
        ),
      ),
    );
  }
}
