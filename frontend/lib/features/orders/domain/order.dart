enum OrderStatus { pending, accepted, filled, partiallyFilled, rejected, cancelled }

OrderStatus _orderStatusFromJson(String value) {
  switch (value) {
    case 'pending':
      return OrderStatus.pending;
    case 'accepted':
      return OrderStatus.accepted;
    case 'filled':
      return OrderStatus.filled;
    case 'partially_filled':
      return OrderStatus.partiallyFilled;
    case 'rejected':
      return OrderStatus.rejected;
    case 'cancelled':
      return OrderStatus.cancelled;
    default:
      throw ArgumentError('unknown order status: $value');
  }
}

class Order {
  const Order({
    required this.id,
    required this.clientOrderId,
    required this.symbol,
    required this.side,
    required this.quantity,
    required this.status,
    required this.filledQuantity,
    required this.tradingMode,
  });

  final int id;
  final String clientOrderId;
  final String symbol;
  final String side; // buy | sell
  final double quantity;
  final OrderStatus status;
  final double filledQuantity;
  final String tradingMode; // paper | live

  factory Order.fromJson(Map<String, dynamic> json) => Order(
        id: json['id'] as int,
        clientOrderId: json['client_order_id'] as String,
        symbol: json['symbol'] as String,
        side: json['side'] as String,
        quantity: (json['quantity'] as num).toDouble(),
        status: _orderStatusFromJson(json['status'] as String),
        filledQuantity: (json['filled_quantity'] as num).toDouble(),
        tradingMode: json['trading_mode'] as String,
      );
}
