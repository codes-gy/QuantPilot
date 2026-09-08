import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/market_watch_repository.dart';

class MarketWatchScreen extends ConsumerWidget {
  const MarketWatchScreen({super.key, required this.symbol});

  final String symbol;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tickAsync = ref.watch(priceTickStreamProvider(symbol));

    return Scaffold(
      appBar: AppBar(title: Text(symbol)),
      body: Center(
        child: tickAsync.when(
          data: (tick) => Text(
            tick.price.toStringAsFixed(0),
            style: Theme.of(context).textTheme.displayMedium,
          ),
          loading: () => const CircularProgressIndicator(),
          error: (err, _) => Text('시세 연결 오류: $err'),
        ),
      ),
    );
  }
}
