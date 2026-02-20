import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../services/api_client.dart';
import '../theme.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  // Shared
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _loading = false;
  String? _error;

  // Register only
  final _nameCtrl = TextEditingController();
  final _pass2Ctrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _tabs.addListener(() => setState(() => _error = null));
  }

  @override
  void dispose() {
    _tabs.dispose();
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _nameCtrl.dispose();
    _pass2Ctrl.dispose();
    super.dispose();
  }

  // ── actions ───────────────────────────────────────────────────────────────

  Future<void> _signIn() async {
    _clearError();
    if (_emailCtrl.text.trim().isEmpty || _passCtrl.text.isEmpty) {
      _setError('Please enter email and password.');
      return;
    }
    setState(() => _loading = true);
    try {
      await AuthService.instance.signIn(_emailCtrl.text, _passCtrl.text);
      await _initProfile();
    } on FirebaseAuthException catch (e) {
      _setError(_friendlyError(e));
    } catch (e) {
      _setError(e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _register() async {
    _clearError();
    if (_nameCtrl.text.trim().isEmpty) {
      _setError('Please enter your name.');
      return;
    }
    if (_emailCtrl.text.trim().isEmpty || _passCtrl.text.isEmpty) {
      _setError('Please enter email and password.');
      return;
    }
    if (_passCtrl.text != _pass2Ctrl.text) {
      _setError('Passwords do not match.');
      return;
    }
    if (_passCtrl.text.length < 6) {
      _setError('Password must be at least 6 characters.');
      return;
    }
    setState(() => _loading = true);
    try {
      await AuthService.instance.signUp(
        _emailCtrl.text,
        _passCtrl.text,
        _nameCtrl.text,
      );
      await _initProfile();
    } on FirebaseAuthException catch (e) {
      _setError(_friendlyError(e));
    } catch (e) {
      _setError(e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// After auth, create/fetch the backend profile so Firestore doc exists.
  Future<void> _initProfile() async {
    final token = await AuthService.instance.idToken;
    if (token == null) return;
    ApiClient().setToken(token);
    final displayName =
        AuthService.instance.currentUser?.displayName ?? _nameCtrl.text.trim();
    try {
      await ApiClient().createProfile(displayName);
    } catch (_) {
      // Non-fatal — profile will be fetched on dashboard load
    }
    // Auth state stream triggers routing in main.dart
  }

  void _setError(String msg) {
    if (mounted) setState(() => _error = msg);
  }

  void _clearError() {
    if (mounted) setState(() => _error = null);
  }

  String _friendlyError(FirebaseAuthException e) {
    switch (e.code) {
      case 'user-not-found':
      case 'wrong-password':
      case 'invalid-credential':
        return 'Incorrect email or password.';
      case 'email-already-in-use':
        return 'An account with this email already exists.';
      case 'weak-password':
        return 'Password is too weak (min 6 characters).';
      case 'invalid-email':
        return 'Please enter a valid email address.';
      case 'too-many-requests':
        return 'Too many attempts. Please try again later.';
      default:
        return e.message ?? 'Authentication failed.';
    }
  }

  // ── build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: C.bg,
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Logo / title
                const Icon(Icons.eco, color: C.green, size: 48),
                const SizedBox(height: 12),
                const Text(
                  'Plant Lab',
                  style: TextStyle(
                    color: C.green,
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.2,
                  ),
                ),
                const Text(
                  'Growth Simulation Platform',
                  style: TextStyle(color: C.textMuted, fontSize: 13),
                ),
                const SizedBox(height: 32),

                // Card
                Container(
                  decoration: BoxDecoration(
                    color: C.panel,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: C.border),
                  ),
                  child: Column(
                    children: [
                      // Tabs
                      TabBar(
                        controller: _tabs,
                        labelColor: C.green,
                        unselectedLabelColor: C.textMuted,
                        indicatorColor: C.green,
                        dividerColor: C.border,
                        labelStyle: const TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w600),
                        tabs: const [Tab(text: 'Sign In'), Tab(text: 'Create Account')],
                      ),
                      Padding(
                        padding: const EdgeInsets.all(20),
                        child: AnimatedSize(
                          duration: const Duration(milliseconds: 200),
                          child: _tabs.index == 0
                              ? _buildSignInForm()
                              : _buildRegisterForm(),
                        ),
                      ),
                    ],
                  ),
                ),

                // Error
                if (_error != null) ...[
                  const SizedBox(height: 14),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: C.danger.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: C.danger.withValues(alpha: 0.4)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.error_outline,
                            color: C.danger, size: 16),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(_error!,
                              style: const TextStyle(
                                  color: C.danger, fontSize: 12)),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSignInForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _field(_emailCtrl, 'Email', keyboardType: TextInputType.emailAddress),
        const SizedBox(height: 12),
        _field(_passCtrl, 'Password', obscure: true),
        const SizedBox(height: 20),
        _primaryButton('Sign In', _signIn),
      ],
    );
  }

  Widget _buildRegisterForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _field(_nameCtrl, 'Display Name'),
        const SizedBox(height: 12),
        _field(_emailCtrl, 'Email', keyboardType: TextInputType.emailAddress),
        const SizedBox(height: 12),
        _field(_passCtrl, 'Password', obscure: true),
        const SizedBox(height: 12),
        _field(_pass2Ctrl, 'Confirm Password', obscure: true),
        const SizedBox(height: 20),
        _primaryButton('Create Account', _register),
      ],
    );
  }

  Widget _field(
    TextEditingController ctrl,
    String label, {
    bool obscure = false,
    TextInputType? keyboardType,
  }) {
    return TextField(
      controller: ctrl,
      obscureText: obscure,
      keyboardType: keyboardType,
      style: const TextStyle(fontSize: 14),
      onSubmitted: (_) =>
          _tabs.index == 0 ? _signIn() : _register(),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: C.textMuted, fontSize: 13),
        filled: true,
        fillColor: C.panelAlt,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: C.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: C.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: C.green, width: 1.5),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      ),
    );
  }

  Widget _primaryButton(String label, VoidCallback onTap) {
    return SizedBox(
      height: 46,
      child: ElevatedButton(
        onPressed: _loading ? null : onTap,
        style: ElevatedButton.styleFrom(
          backgroundColor: C.green,
          disabledBackgroundColor: C.green.withValues(alpha: 0.4),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
        child: _loading
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: Colors.white),
              )
            : Text(label,
                style: const TextStyle(
                    fontWeight: FontWeight.w600, fontSize: 14)),
      ),
    );
  }
}
