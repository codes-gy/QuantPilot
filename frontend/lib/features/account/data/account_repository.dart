import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/di/providers.dart';
import '../../../core/network/api_client.dart';

class AccountRepository {
  AccountRepository(this._api);

  final ApiClient _api;

  /// 로그인 성공 시 access_token을 반환한다. 저장은 호출부(LoginScreen)가
  /// AuthStateNotifier.markAuthenticated를 통해 한다 — 이 레포지토리는 순수하게 API 호출만 담당.
  Future<String> login(String email, String password) async {
    final response = await _api.dio.post('/auth/login', data: {
      'email': email,
      'password': password,
    });
    return response.data['access_token'] as String;
  }
}

final accountRepositoryProvider = Provider(
  (ref) => AccountRepository(ref.watch(apiClientProvider)),
);
