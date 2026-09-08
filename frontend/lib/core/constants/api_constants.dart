class ApiConstants {
  ApiConstants._();

  // TODO: 빌드 플레이버(dev/prod)별로 --dart-define 으로 주입
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  static const String wsUrl = String.fromEnvironment(
    'WS_URL',
    defaultValue: 'ws://localhost:8000/ws/live',
  );
}
