import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/app_theme.dart';
import 'features/dashboard/presentation/dashboard_screen.dart';
import 'features/orders/presentation/orders_screen.dart';
import 'features/settings/presentation/settings_screen.dart';
import 'features/strategy/presentation/strategy_list_screen.dart';

void main() {
  runApp(const ProviderScope(child: QuantPilotApp()));
}

class QuantPilotApp extends StatelessWidget {
  const QuantPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'QuantPilot',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      // TODO: account/data의 저장된 토큰 유무에 따라 LoginScreen과 분기
      home: const RootShell(),
    );
  }
}

class RootShell extends StatefulWidget {
  const RootShell({super.key});

  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _index = 0;

  static const _tabs = [
    DashboardScreen(),
    StrategyListScreen(),
    OrdersScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard), label: '대시보드'),
          NavigationDestination(icon: Icon(Icons.rule), label: '전략'),
          NavigationDestination(icon: Icon(Icons.receipt_long), label: '주문'),
          NavigationDestination(icon: Icon(Icons.settings), label: '설정'),
        ],
      ),
    );
  }
}
