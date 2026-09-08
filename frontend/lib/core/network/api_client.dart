import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../constants/api_constants.dart';

/// 모든 REST 호출이 거치는 단일 Dio 인스턴스.
/// JWT 첨부와 401 처리(로그아웃 트리거)를 여기 인터셉터 한 곳에서만 담당한다.
class ApiClient {
  ApiClient(this._storage) : dio = Dio(BaseOptions(baseUrl: ApiConstants.baseUrl)) {
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
          // TODO: 401 응답 시 저장된 토큰 삭제 후 로그인 화면으로 라우팅
          handler.next(error);
        },
      ),
    );
  }

  final Dio dio;
  final FlutterSecureStorage _storage;
}
