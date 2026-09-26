import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../auth/auth_state_provider.dart';
import '../network/api_client.dart';
import '../network/ws_client.dart';

/// 앱 전역 의존성 루트. feature별 provider는 이 값들을 참조해 조립한다.
final secureStorageProvider = Provider((ref) => const FlutterSecureStorage());

final apiClientProvider = Provider((ref) => ApiClient(
      ref.watch(secureStorageProvider),
      // 401을 받으면 인증 상태를 되돌린다 -> main.dart가 자동으로 LoginScreen으로 전환한다.
      onUnauthorized: () => ref.read(authStateProvider.notifier).logout(),
    ));

final liveWsClientProvider = Provider<LiveWsClient>((ref) {
  final client = LiveWsClient()..connect();
  ref.onDispose(client.dispose);
  return client;
});
