import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/di/providers.dart';
import '../../../core/network/api_client.dart';
import '../domain/order.dart';

class OrdersRepository {
  OrdersRepository(this._api);

  final ApiClient _api;

  Future<List<Order>> fetchAll() async {
    final response = await _api.dio.get('/orders');
    return (response.data as List).map((e) => Order.fromJson(e as Map<String, dynamic>)).toList();
  }
}

final ordersRepositoryProvider = Provider(
  (ref) => OrdersRepository(ref.watch(apiClientProvider)),
);

/// 백엔드가 아직 주문 상태 변경을 /ws/live로 내보내지 않아서(시세/리스크 알림만 브로드캐스트됨),
/// 지금은 화면 진입 시 조회 + 아래로 당겨서 새로고침 방식만 지원한다. 실시간 업데이트는
/// 백엔드에 주문 이벤트 브로드캐스트가 추가되면 market_watch의 priceTickStreamProvider와
/// 같은 패턴으로 확장할 수 있다.
final ordersListProvider = FutureProvider.autoDispose(
  (ref) => ref.watch(ordersRepositoryProvider).fetchAll(),
);
