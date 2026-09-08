import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../constants/api_constants.dart';

/// 백엔드 /ws/live 채널 구독. 시세·주문 상태 변경을 실시간으로 받아
/// market_watch, orders 등 여러 feature의 provider가 이 스트림을 공유해 구독한다.
class LiveWsClient {
  WebSocketChannel? _channel;
  final _controller = StreamController<Map<String, dynamic>>.broadcast();

  Stream<Map<String, dynamic>> get stream => _controller.stream;

  void connect() {
    _channel = WebSocketChannel.connect(Uri.parse(ApiConstants.wsUrl));
    _channel!.stream.listen(
      (raw) => _controller.add(jsonDecode(raw as String) as Map<String, dynamic>),
      onError: (_) => _reconnect(),
      onDone: _reconnect,
    );
  }

  void _reconnect() {
    // TODO: 지수 백오프 재연결
    Future.delayed(const Duration(seconds: 3), connect);
  }

  void dispose() {
    _channel?.sink.close();
    _controller.close();
  }
}
