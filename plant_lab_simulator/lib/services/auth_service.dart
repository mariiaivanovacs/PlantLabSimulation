import 'package:firebase_auth/firebase_auth.dart';

/// Thin wrapper around FirebaseAuth.
/// Exposes sign-in, sign-up, sign-out, and the current ID token.
class AuthService {
  AuthService._();
  static final AuthService instance = AuthService._();

  final FirebaseAuth _auth = FirebaseAuth.instance;

  // ── streams ──────────────────────────────────────────────────────────────

  Stream<User?> get authStateChanges => _auth.authStateChanges();

  User? get currentUser => _auth.currentUser;

  /// Returns a fresh ID token for the current user, or null if not signed in.
  Future<String?> get idToken async {
    final user = _auth.currentUser;
    if (user == null) return null;
    try {
      return await user.getIdToken();
    } catch (_) {
      return null;
    }
  }

  // ── auth actions ─────────────────────────────────────────────────────────

  /// Sign in with email + password.
  /// Throws [FirebaseAuthException] on failure.
  Future<UserCredential> signIn(String email, String password) {
    return _auth.signInWithEmailAndPassword(
      email: email.trim(),
      password: password,
    );
  }

  /// Register a new account, then update the display name.
  /// Throws [FirebaseAuthException] on failure.
  Future<UserCredential> signUp(
    String email,
    String password,
    String displayName,
  ) async {
    final cred = await _auth.createUserWithEmailAndPassword(
      email: email.trim(),
      password: password,
    );
    await cred.user?.updateDisplayName(displayName.trim());
    return cred;
  }

  Future<void> signOut() => _auth.signOut();
}
