import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../constants/api_constants.dart';

/// 모든 REST 호출이 거치는 단일 Dio 인스턴스.
/// JWT 첨부와 401 처리(로그아웃 트리거)를 여기 인터셉터 한 곳에서만 담당한다.
///
/// onUnauthorized는 Riverpod을 전혀 모르는 이 클래스가 인증 상태를 직접 바꾸지 않고도
/// 401을 알릴 수 있게 하는 콜백이다 — 실제 연결은 조립 지점인 core/di/providers.dart가 담당한다.
class ApiClient {
  ApiClient(this._storage, {this.onUnauthorized}) : dio = Dio(BaseOptions(baseUrl: ApiConstants.baseUrl)) {
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _storage.read(key: 'access_token');
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) {
          if (error.response?.statusCode == 401) {
            onUnauthorized?.call();
          }
          handler.next(error);
        },
      ),
    );
  }

  final Dio dio;
  final FlutterSecureStorage _storage;
  final void Function()? onUnauthorized;
}
