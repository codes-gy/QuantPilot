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
