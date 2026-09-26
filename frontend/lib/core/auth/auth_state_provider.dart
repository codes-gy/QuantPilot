import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../di/providers.dart';

/// 앱 전체의 로그인 여부. main.dart가 이 값에 따라 LoginScreen/RootShell을 스위칭하고,
/// ApiClient는 401 응답을 받으면 이 상태를 unauthenticated로 되돌린다 (providers.dart 참고).
enum AuthStatus { checking, authenticated, unauthenticated }

class AuthStateNotifier extends StateNotifier<AuthStatus> {
  AuthStateNotifier(this._storage) : super(AuthStatus.checking) {
    _checkInitialAuth();
  }

  final FlutterSecureStorage _storage;

  Future<void> _checkInitialAuth() async {
    final token = await _storage.read(key: 'access_token');
    state = token != null ? AuthStatus.authenticated : AuthStatus.unauthenticated;
  }

  /// 로그인 성공 시 LoginScreen이 호출한다.
  Future<void> markAuthenticated(String accessToken) async {
    await _storage.write(key: 'access_token', value: accessToken);
    state = AuthStatus.authenticated;
  }

  /// 사용자가 직접 로그아웃하거나(설정 화면), ApiClient가 401을 감지했을 때 호출된다.
  Future<void> logout() async {
    await _storage.delete(key: 'access_token');
    state = AuthStatus.unauthenticated;
  }
}

final authStateProvider = StateNotifierProvider<AuthStateNotifier, AuthStatus>(
  (ref) => AuthStateNotifier(ref.watch(secureStorageProvider)),
);
