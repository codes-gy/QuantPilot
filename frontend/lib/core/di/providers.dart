import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../network/api_client.dart';
import '../network/ws_client.dart';

/// 앱 전역 의존성 루트. feature별 provider는 이 값들을 참조해 조립한다.
final secureStorageProvider = Provider((ref) => const FlutterSecureStorage());

final apiClientProvider = Provider((ref) => ApiClient(ref.watch(secureStorageProvider)));

final liveWsClientProvider = Provider<LiveWsClient>((ref) {
  final client = LiveWsClient()..connect();
  ref.onDispose(client.dispose);
  return client;
});
