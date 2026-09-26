import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/orders_repository.dart';
import '../domain/order.dart';

const _statusLabels = {
  OrderStatus.pending: '대기',
  OrderStatus.accepted: '접수됨',
  OrderStatus.filled: '체결완료',
  OrderStatus.partiallyFilled: '부분체결',
  OrderStatus.rejected: '거부됨',
  OrderStatus.cancelled: '취소됨',
};

class OrdersScreen extends ConsumerWidget {
  const OrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ordersAsync = ref.watch(ordersListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('주문 내역')),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(ordersListProvider.future),
        child: ordersAsync.when(
          data: (orders) {
            if (orders.isEmpty) {
              return LayoutBuilder(
                builder: (context, constraints) => SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(minHeight: constraints.maxHeight),
                    child: const Center(child: Text('아직 주문 내역이 없어요.')),
                  ),
                ),
              );
            }
            return ListView.builder(
              physics: const AlwaysScrollableScrollPhysics(),
              itemCount: orders.length,
              itemBuilder: (context, i) => _OrderTile(order: orders[i]),
            );
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (err, _) => LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Center(child: Text('불러오기 실패: $err')),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OrderTile extends StatelessWidget {
  const _OrderTile({required this.order});

  final Order order;

  @override
  Widget build(BuildContext context) {
    final isBuy = order.side == 'buy';
    final sideColor = isBuy ? Colors.red : Colors.blue; // 국내 증권가 관례: 매수 빨강, 매도 파랑
    final sideLabel = isBuy ? '매수' : '매도';

    return ListTile(
      leading: CircleAvatar(
        backgroundColor: sideColor.withOpacity(0.15),
        child: Text(sideLabel, style: TextStyle(color: sideColor, fontSize: 12, fontWeight: FontWeight.bold)),
      ),
      title: Text(order.symbol),
      subtitle: Text('수량 ${order.quantity.toStringAsFixed(0)} · 체결 ${order.filledQuantity.toStringAsFixed(0)}'),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(_statusLabels[order.status] ?? order.status.name),
          if (order.tradingMode == 'paper')
            Text('모의', style: Theme.of(context).textTheme.labelSmall?.copyWith(color: Colors.grey)),
        ],
      ),
    );
  }
}
