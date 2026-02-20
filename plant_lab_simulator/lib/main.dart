import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'firebase_options.dart';
import 'services/auth_service.dart';
import 'services/api_client.dart';
import 'theme.dart';
import 'screens/auth_screen.dart';
import 'screens/dashboard.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(const PlantLabApp());
}

class PlantLabApp extends StatelessWidget {
  const PlantLabApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Plant Lab Simulator',
      debugShowCheckedModeBanner: false,
      theme: PlantLabTheme.darkTheme,
      home: const _AuthGate(),
    );
  }
}

class _AuthGate extends StatelessWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<User?>(
      stream: AuthService.instance.authStateChanges,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _loadingScaffold();
        }
        final user = snapshot.data;
        if (user == null) {
          ApiClient().setToken(null);
          return const AuthScreen();
        }
        // Await the Firebase ID token BEFORE routing — prevents a race where
        // DashboardScreen calls getProfile() before the token is stored.
        return FutureBuilder<String?>(
          future: user.getIdToken(),
          builder: (context, tokenSnap) {
            if (tokenSnap.connectionState == ConnectionState.waiting) {
              return _loadingScaffold();
            }
            ApiClient().setToken(tokenSnap.data);
            return const DashboardScreen();
          },
        );
      },
    );
  }

  Widget _loadingScaffold() => const Scaffold(
        backgroundColor: C.bg,
        body: Center(child: CircularProgressIndicator(color: C.green)),
      );
}
