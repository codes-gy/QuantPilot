import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/auth/auth_state_provider.dart';
import 'core/theme/app_theme.dart';
import 'features/account/presentation/login_screen.dart';
import 'features/dashboard/presentation/dashboard_screen.dart';
import 'features/orders/presentation/orders_screen.dart';
import 'features/settings/presentation/settings_screen.dart';
import 'features/strategy/presentation/strategy_list_screen.dart';

void main() {
  runApp(const ProviderScope(child: QuantPilotApp()));
}

class QuantPilotApp extends ConsumerWidget {
  const QuantPilotApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authStatus = ref.watch(authStateProvider);

    return MaterialApp(
      title: 'QuantPilot',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      home: switch (authStatus) {
        AuthStatus.checking => const _SplashScreen(),
        AuthStatus.unauthenticated => const LoginScreen(),
        AuthStatus.authenticated => const RootShell(),
      },
    );
  }
}

/// secureStorage에서 저장된 토큰을 읽는 동안(비동기) 잠깐 보여주는 화면.
class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
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

  static const _destinations = [
    (icon: Icons.dashboard, label: '대시보드'),
    (icon: Icons.rule, label: '전략'),
    (icon: Icons.receipt_long, label: '주문'),
    (icon: Icons.settings, label: '설정'),
  ];

  /// 이 폭 이상(PC 브라우저/태블릿 가로)이면 하단 탭 대신 왼쪽 세로 메뉴를 쓴다.
  static const _wideBreakpoint = 840.0;

  /// 넓은 화면에서 목록/카드가 끝없이 늘어나 읽기 어려워지지 않도록 본문 폭을 제한한다.
  static const _maxContentWidth = 1100.0;

  void _select(int i) => setState(() => _index = i);

  @override
  Widget build(BuildContext context) {
    final content = IndexedStack(index: _index, children: _tabs);
    final isWide = MediaQuery.sizeOf(context).width >= _wideBreakpoint;

    if (!isWide) {
      return Scaffold(
        body: content,
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: _select,
          destinations: [
            for (final d in _destinations) NavigationDestination(icon: Icon(d.icon), label: d.label),
          ],
        ),
      );
    }

    return Scaffold(
      body: Row(
        children: [
          NavigationRail(
            selectedIndex: _index,
            onDestinationSelected: _select,
            labelType: NavigationRailLabelType.all,
            leading: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Icon(Icons.auto_graph, color: Theme.of(context).colorScheme.primary, size: 32),
            ),
            destinations: [
              for (final d in _destinations)
                NavigationRailDestination(icon: Icon(d.icon), label: Text(d.label)),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: _maxContentWidth),
                child: content,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
