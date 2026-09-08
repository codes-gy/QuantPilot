import 'package:flutter/material.dart';

// TODO: settings/data, settings/domain — 모의/실전 표시 배지, 증권사 API 키 등록,
// 알림 채널 설정 등. TRADING_MODE는 백엔드 .env에서만 전환하며 앱에서는 조회만 노출한다.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('설정')),
      body: const Center(child: Text('현재 거래 모드 표시(모의/실전) 및 계정 설정 자리')),
    );
  }
}
