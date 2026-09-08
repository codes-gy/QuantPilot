import 'package:flutter/material.dart';

// TODO: market_watch/strategy와 동일한 패턴으로 orders/data, orders/domain 구현
// (GET /orders 조회 + WebSocket 주문 상태 업데이트 구독)
class OrdersScreen extends StatelessWidget {
  const OrdersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('주문 내역')),
      body: const Center(child: Text('주문 목록 자리')),
    );
  }
}
