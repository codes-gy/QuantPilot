import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../constants/api_constants.dart';

/// 백엔드 /ws/live 채널 구독. 시세·주문 상태 변경을 실시간으로 받아
/// market_watch, orders 등 여러 feature의 provider가 이 스트림을 공유해 구독한다.
class LiveWsClient {
  WebSocketChannel? _channel;
  final _controller = StreamController<Map<String, dynamic>>.broadcast();

  int _reconnectAttempts = 0;
  bool _reconnectScheduled = false;

  static const _baseDelay = Duration(seconds: 1);
  static const _maxDelay = Duration(seconds: 30);

  Stream<Map<String, dynamic>> get stream => _controller.stream;

  void connect() {
    _reconnectScheduled = false;
    _channel = WebSocketChannel.connect(Uri.parse(ApiConstants.wsUrl));
    _channel!.stream.listen(
      (raw) {
        // 메시지를 정상적으로 받았다는 건 연결이 살아있다는 뜻이므로, 다음 끊김에 대비해 백오프를 리셋한다.
        _reconnectAttempts = 0;
        _controller.add(jsonDecode(raw as String) as Map<String, dynamic>);
      },
      onError: (_) => _reconnect(),
      onDone: _reconnect,
    );
  }

  void _reconnect() {
    // 연결이 끊기면 onError와 onDone이 같은 끊김에 대해 둘 다 호출될 수 있어서,
    // 재연결이 중복 예약(동시에 여러 개의 WS 연결이 열리는 상황)되지 않도록 막는다.
    if (_reconnectScheduled) return;
    _reconnectScheduled = true;
    Future.delayed(_nextDelay(), connect);
  }

  /// 1초 -> 2초 -> 4초 -> 8초 -> 16초 -> 30초(상한)로 지수적으로 늘어나는 재연결 지연.
  Duration _nextDelay() {
    final multiplier = pow(2, _reconnectAttempts).toInt();
    _reconnectAttempts++;
    final delay = _baseDelay * multiplier;
    return delay > _maxDelay ? _maxDelay : delay;
  }

  void dispose() {
    _channel?.sink.close();
    _controller.close();
  }
}
