import 'package:flutter/material.dart';

// TODO: account/data(POST /auth/login) + account/domain(User) 구현,
// 발급받은 access_token은 core/di의 secureStorageProvider에 저장
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('로그인')),
      body: const Center(child: Text('로그인 폼 자리')),
    );
  }
}
