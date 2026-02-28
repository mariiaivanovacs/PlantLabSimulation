import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'firebase_options.dart';
import 'services/auth_service.dart';
import 'services/api_client.dart';
import 'theme.dart';
import 'screens/auth_screen.dart';
import 'screens/mode_selection_screen.dart';

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

// _AuthGate is StatefulWidget so we can cache the getIdToken() future.
// Without caching, every authStateChanges emission (e.g. updateDisplayName
// during registration fires a second event) creates a NEW FutureBuilder
// that resets to ConnectionState.waiting — causing the redirect to be
// skipped or the loading screen to flash back after ModeSelectionScreen
// has already rendered.
class _AuthGate extends StatefulWidget {
  const _AuthGate();

  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  Future<String?>? _tokenFuture;
  String? _cachedUid;

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
          _tokenFuture = null;
          _cachedUid = null;
          return const AuthScreen();
        }
        // Only re-fetch the token when the user identity changes (new login).
        // Profile updates (updateDisplayName) re-emit the same uid — we ignore
        // those so the FutureBuilder is not recreated and the redirect holds.
        if (_cachedUid != user.uid) {
          _cachedUid = user.uid;
          _tokenFuture = user.getIdToken();
        }
        return FutureBuilder<String?>(
          future: _tokenFuture,
          builder: (context, tokenSnap) {
            if (tokenSnap.connectionState == ConnectionState.waiting) {
              return _loadingScaffold();
            }
            ApiClient().setToken(tokenSnap.data);
            return const ModeSelectionScreen();
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
