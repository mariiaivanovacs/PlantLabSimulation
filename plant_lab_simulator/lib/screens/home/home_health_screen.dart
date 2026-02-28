// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../theme.dart';
import '../../services/auth_service.dart';
import '../../services/api_client.dart';
import '../auth_screen.dart';
import '../../services/firestore_service.dart';
import '../../services/gemini_service.dart';
import '../../models/plant_record.dart';
import '../../models/health_check.dart';
import 'plant_onboarding_screen.dart';
import '../../widgets/shared.dart';

const int _kFreePlanLimit = 3;

// ── Hover-scale wrapper for web / desktop cards ───────────────────────────────

class _HoverCard extends StatefulWidget {
  final Widget child;
  const _HoverCard({required this.child});

  @override
  State<_HoverCard> createState() => _HoverCardState();
}

class _HoverCardState extends State<_HoverCard> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: AnimatedScale(
        scale: _hovered ? 1.018 : 1.0,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        child: widget.child,
      ),
    );
  }
}

// ── Screen ────────────────────────────────────────────────────────────────────

class HomeHealthScreen extends StatefulWidget {
  final PlantRecord? initialPlant;
  const HomeHealthScreen({super.key, this.initialPlant});

  @override
  State<HomeHealthScreen> createState() => _HomeHealthScreenState();
}

class _HomeHealthScreenState extends State<HomeHealthScreen>
    with SingleTickerProviderStateMixin {
  // ── Plant list & selection ────────────────────────────────────────────────────
  List<PlantRecord> _plants = [];
  PlantRecord? _current;
  bool _loadingPlants = true;

  // ── Image upload ──────────────────────────────────────────────────────────────
  Uint8List? _imageBytes;
  String? _imageB64;

  // ── Optional env hints ────────────────────────────────────────────────────────
  int? _lastWateringDays;

  // ── Health check state ────────────────────────────────────────────────────────
  bool _checking = false;
  String? _checkError;
  HealthCheck? _latestResult;

  // ── History ───────────────────────────────────────────────────────────────────
  List<HealthCheck> _history = [];
  bool _loadingHistory = false;

  // ── Subscription ──────────────────────────────────────────────────────────────
  bool _isPro = false;
  bool _upgradingToPro = false;

  // ── Background animation controller ──────────────────────────────────────────
  late final AnimationController _bgController;

  bool get _atPlantLimit => !_isPro && _plants.length >= _kFreePlanLimit;

  // ── Lifecycle ─────────────────────────────────────────────────────────────────

  @override
  void initState() {
    super.initState();
    _bgController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat(reverse: true);
    _init();
  }

  @override
  void dispose() {
    _bgController.dispose();
    super.dispose();
  }

  // ── Init ──────────────────────────────────────────────────────────────────────

  Future<void> _init() async {
    final uri = Uri.parse(html.window.location.href);
    if (uri.queryParameters['subscription'] == 'success') {
      html.window.history.replaceState(null, '', '/');
    }
    _loadSubscriptionStatus();
    if (widget.initialPlant != null) {
      setState(() {
        _plants = [widget.initialPlant!];
        _current = widget.initialPlant;
        _loadingPlants = false;
      });
      _loadAllPlants();
      _loadHistory();
    } else {
      await _loadAllPlants();
    }
  }

  Future<void> _loadSubscriptionStatus() async {
    try {
      final status = await ApiClient().getSubscriptionStatus();
      if (!mounted) return;
      setState(() => _isPro = status['plan'] == 'pro');
    } catch (_) {}
  }

  Future<void> _upgradeToPro() async {
    setState(() => _upgradingToPro = true);
    try {
      final url = await ApiClient().createCheckoutSession();
      html.window.location.href = url;
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('Could not start checkout: $e'),
            backgroundColor: C.danger),
      );
      setState(() => _upgradingToPro = false);
    }
  }

  Future<void> _loadAllPlants() async {
    try {
      final plants = await FirestoreService.instance.getPlants();
      setState(() {
        _plants = plants;
        _current ??= plants.isNotEmpty ? plants.first : null;
        _loadingPlants = false;
      });
      if (_current != null && _history.isEmpty) _loadHistory();
    } catch (e) {
      setState(() => _loadingPlants = false);
    }
  }

  Future<void> _loadHistory() async {
    final plant = _current;
    if (plant == null) return;
    setState(() => _loadingHistory = true);
    try {
      final checks = await FirestoreService.instance.getHealthChecks(plant.id);
      if (!mounted) return;
      setState(() {
        _history = checks;
        _loadingHistory = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loadingHistory = false);
    }
  }

  // ── Image pick ────────────────────────────────────────────────────────────────

  Future<void> _pickImage() async {
    final input = html.FileUploadInputElement()
      ..accept = 'image/*'
      ..click();
    await input.onChange.first;
    final file = input.files?.first;
    if (file == null) return;
    final reader = html.FileReader();
    reader.readAsArrayBuffer(file);
    await reader.onLoad.first;
    final bytes = Uint8List.fromList(reader.result as List<int>);
    setState(() {
      _imageBytes = bytes;
      _imageB64 = base64Encode(bytes);
      _checkError = null;
      _latestResult = null;
    });
  }

  // ── Health check ──────────────────────────────────────────────────────────────

  Future<void> _checkHealth() async {
    final plant = _current;
    if (plant == null) return;
    if (_imageB64 == null) {
      setState(() => _checkError = 'Please upload a photo first.');
      return;
    }
    setState(() {
      _checking = true;
      _checkError = null;
    });
    try {
      final result = await GeminiService.instance.checkHealth(
        imageB64: _imageB64!,
        plantType: plant.identifiedAs,
        ageDays: plant.ageDays,
        plantId: plant.id,
        lastWateringDays: _lastWateringDays?.toDouble(),
      );
      if (!mounted) return;
      setState(() {
        _latestResult = result;
        _history = [result, ..._history];
        _checking = false;
        _imageBytes = null;
        _imageB64 = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _checking = false;
        _checkError = e.toString();
      });
    }
  }

  // ── Plant management ──────────────────────────────────────────────────────────

  void _switchPlant(PlantRecord plant) {
    setState(() {
      _current = plant;
      _history = [];
      _latestResult = null;
      _imageBytes = null;
      _imageB64 = null;
      _checkError = null;
      _lastWateringDays = null;
    });
    _loadHistory();
  }

  Future<void> _addNewPlant() async {
    if (_atPlantLimit) {
      _showPlantLimitDialog();
      return;
    }
    final result = await Navigator.push<PlantRecord>(
      context,
      MaterialPageRoute(
          builder: (_) => const PlantOnboardingScreen(isFirstPlant: false)),
    );
    if (result != null && mounted) {
      setState(() => _plants = [..._plants, result]);
      _switchPlant(result);
    }
  }

  void _showPlantLimitDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: C.panel,
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: const Row(
          children: [
            Icon(Icons.workspace_premium, color: C.warn, size: 22),
            SizedBox(width: 10),
            Text('Plant limit reached',
                style:
                    TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          ],
        ),
        content: Text(
          'Free plan supports up to $_kFreePlanLimit plants.\n'
          'Upgrade to Pro for unlimited plants and advanced AI analysis.',
          style: const TextStyle(
              color: C.textMuted, fontSize: 14, height: 1.5),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Maybe later',
                style: TextStyle(color: C.textMuted)),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              _upgradeToPro();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: C.green,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8)),
            ),
            child: const Text('Upgrade to Pro',
                style: TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  // ── Health score helpers ──────────────────────────────────────────────────────

  int _healthScore(HealthCheck check) {
    final avg = (check.waterStress + check.nutrientStress +
            check.temperatureStress) /
        3.0;
    return ((1.0 - avg.clamp(0.0, 1.0)) * 100).round();
  }

  String _healthLabel(int score) {
    if (score >= 80) return 'Thriving';
    if (score >= 60) return 'Good';
    if (score >= 40) return 'Needs care';
    return 'Struggling';
  }

  Color _healthColor(int score) {
    if (score >= 80) return C.green;
    if (score >= 60) return const Color(0xFF8BC34A);
    if (score >= 40) return C.warn;
    return C.danger;
  }

  // ── Glassmorphism card ────────────────────────────────────────────────────────

  Widget _glassCard({
    required Widget child,
    EdgeInsetsGeometry padding = const EdgeInsets.all(18),
    BorderRadius? radius,
    Color? borderColor,
    bool highlight = false,
  }) {
    final br = radius ?? BorderRadius.circular(16);
    return ClipRRect(
      borderRadius: br,
      child: BackdropFilter(
        filter: ui.ImageFilter.blur(sigmaX: 14, sigmaY: 14),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            color: highlight
                ? C.green.withOpacity(0.07)
                : Colors.white.withOpacity(0.045),
            borderRadius: br,
            border: Border.all(
              color: borderColor ??
                  (highlight
                      ? C.green.withOpacity(0.22)
                      : Colors.white.withOpacity(0.10)),
            ),
          ),
          child: child,
        ),
      ),
    );
  }

  // ── Build ─────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    if (_loadingPlants) {
      return const Scaffold(
        backgroundColor: C.bg,
        body: Center(child: CircularProgressIndicator(color: C.green)),
      );
    }

    if (_current == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          Navigator.pushReplacement(
            context,
            MaterialPageRoute(
                builder: (_) =>
                    const PlantOnboardingScreen(isFirstPlant: true)),
          );
        }
      });
      return const Scaffold(
        backgroundColor: C.bg,
        body: Center(child: CircularProgressIndicator(color: C.green)),
      );
    }

    return Scaffold(
      backgroundColor: C.bg,
      appBar: _buildAppBar(),
      body: Stack(
        children: [
          // ── Animated gradient background ──────────────────────────────────────
          // pattern here for debug
          AnimatedBuilder(
  animation: _bgController,
  builder: (context, _) {
    final t = _bgController.value;

    final sweepX = -1.0 + (2.0 * t); // moving light sweep

    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF0B0F14), // deep dark base
            Color.lerp(
              const Color(0xFF0F2027),
              const Color(0xFF0D3018),
              t,
            )!,
            const Color(0xFF0F1115),
          ],
        ),
      ),
      child: Stack(
        children: [
          // Moving cyber glow
          Align(
            alignment: Alignment(sweepX, -0.3),
            child: Container(
              width: 500,
              height: 500,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    Colors.tealAccent.withOpacity(0.15),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  },
),

          // ── Dark overlay for readability ──────────────────────────────────────
          Container(
            width: double.infinity,
            height: double.infinity,
            color: Colors.black.withOpacity(0.38),
          ),

          // ── Main content ──────────────────────────────────────────────────────
          LayoutBuilder(
            builder: (context, constraints) {
              final hPad = constraints.maxWidth < 600 ? 16.0 : 24.0;
              return Center(
                child: SingleChildScrollView(
                  padding: EdgeInsets.symmetric(
                      horizontal: hPad, vertical: 20),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 680),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _buildPlantHeader()
                            .animate()
                            .fadeIn(duration: 420.ms, curve: Curves.easeOut)
                            .slideY(
                                begin: -0.06,
                                end: 0,
                                duration: 420.ms,
                                curve: Curves.easeOut),
                        const SizedBox(height: 20),
                        _buildLastWateringSelector()
                            .animate(delay: 60.ms)
                            .fadeIn(duration: 360.ms)
                            .slideY(
                                begin: 0.05,
                                end: 0,
                                duration: 360.ms,
                                curve: Curves.easeOut),
                        const SizedBox(height: 16),
                        _buildUploadZone()
                            .animate(delay: 100.ms)
                            .fadeIn(duration: 360.ms)
                            .slideY(
                                begin: 0.05,
                                end: 0,
                                duration: 360.ms,
                                curve: Curves.easeOut),
                        if (_checkError != null) ...[
                          const SizedBox(height: 10),
                          _errorBox(_checkError!),
                        ],
                        const SizedBox(height: 14),
                        _buildAnalyseButton()
                            .animate(delay: 140.ms)
                            .fadeIn(duration: 360.ms),
                        if (!_isPro) ...[
                          const SizedBox(height: 16),
                          _buildUpgradeBanner()
                              .animate(delay: 180.ms)
                              .fadeIn(duration: 360.ms)
                              .slideY(
                                  begin: 0.05,
                                  end: 0,
                                  duration: 360.ms,
                                  curve: Curves.easeOut),
                        ],
                        if (_latestResult != null) ...[
                          const SizedBox(height: 28),
                          _buildResultCard(_latestResult!, isLatest: true)
                              .animate()
                              .fadeIn(
                                  duration: 500.ms, curve: Curves.easeOut)
                              .scale(
                                begin: const Offset(0.97, 0.97),
                                end: const Offset(1.0, 1.0),
                                duration: 500.ms,
                                curve: Curves.easeOut,
                              ),
                        ],
                        const SizedBox(height: 32),
                        _buildHistorySection(),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  // ── AppBar ────────────────────────────────────────────────────────────────────

  AppBar _buildAppBar() {
    final plant = _current!;
    return AppBar(
      backgroundColor: C.bg.withOpacity(0.88),
      elevation: 0,
      title: Row(
        children: [
          const AppLogoImage(size: 40),
          const SizedBox(width: 8),
          Text(
            'My Garden',
            style: GoogleFonts.outfit(
              fontSize: 25,
              fontWeight: FontWeight.w700,
              color: C.textPrimary,
              letterSpacing: 1.2,
            ),
          ),
        ],
      ),
      actions: [
        if (!_isPro)
          GestureDetector(
            onTap: _upgradingToPro ? null : _upgradeToPro,
            child: Container(
              margin: const EdgeInsets.only(right: 8),
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: C.warn.withOpacity(0.12),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: C.warn.withOpacity(0.4)),
              ),
              child: Text(
                'FREE',
                style: GoogleFonts.outfit(
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  color: C.warn,
                  letterSpacing: 1.0,
                ),
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.only(right: 12),
          child: PopupMenuButton<String>(
            offset: const Offset(0, 48),
            color: C.panel,
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10)),
            tooltip: 'Switch plant',
            child: CircleAvatar(
              radius: 18,
              backgroundColor: C.green.withOpacity(0.15),
              child: ClipOval(
                child: Image.asset(
                  plant.plantImagePath,
                  width: 35,
                  height: 35,
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) =>
                      Text(plant.emoji, style: const TextStyle(fontSize: 17)),
                ),
              ),
            ),
            itemBuilder: (_) => [
              PopupMenuItem<String>(
                enabled: false,
                height: 36,
                child: Row(
                  children: [
                    Text(
                      'MY PLANTS',
                      style: GoogleFonts.outfit(
                        fontSize: 14,
                        color: C.textMuted,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      _isPro
                          ? '${_plants.length}'
                          : '${_plants.length} / $_kFreePlanLimit',
                      style:
                          const TextStyle(fontSize: 16, color: C.textDim),
                    ),
                  ],
                ),
              ),
              ..._plants.map(
                (p) => PopupMenuItem<String>(
                  value: 'plant_${p.id}',
                  child: Row(
                    children: [
                      SizedBox(
                        width: 30,
                        height: 30,
                        child: Image.asset(
                          p.plantImagePath,
                          fit: BoxFit.contain,
                          errorBuilder: (_, __, ___) =>
                              Text(p.emoji, style: const TextStyle(fontSize: 21)),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          p.name,
                          style: TextStyle(
                            color: p.id == _current!.id
                                ? C.green
                                : C.textPrimary,
                            fontWeight: p.id == _current!.id
                                ? FontWeight.w600
                                : FontWeight.normal,
                          ),
                        ),
                      ),
                      if (p.id == _current!.id)
                        const Icon(Icons.check,
                            size: 14, color: C.green),
                    ],
                  ),
                ),
              ),
              const PopupMenuDivider(),
              PopupMenuItem<String>(
                value: 'add_plant',
                child: Row(
                  children: [
                    _atPlantLimit
                        ? const Icon(Icons.lock_outline,
                            size: 15, color: C.textMuted)
                        : const Icon(Icons.add,
                            size: 16, color: C.green),
                    const SizedBox(width: 10),
                    Text(
                      'Add new plant',
                      style: TextStyle(
                          color: _atPlantLimit ? C.textMuted : C.green,
                          fontSize: 18),
                    ),
                    if (_atPlantLimit) ...[
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 5, vertical: 2),
                        decoration: BoxDecoration(
                          color: C.warn.withOpacity(0.12),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          'PRO',
                          style: GoogleFonts.outfit(
                              fontSize: 13,
                              color: C.warn,
                              fontWeight: FontWeight.w800),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const PopupMenuDivider(),
              PopupMenuItem<String>(
                value: 'sign_out',
                child: Row(children: const [
                  Icon(Icons.logout, size: 16, color: C.textMuted),
                  SizedBox(width: 10),
                  Text('Sign out',
                      style:
                          TextStyle(color: C.textMuted, fontSize: 18)),
                ]),
              ),
            ],
            onSelected: (value) async {
              if (value == 'sign_out') {
                try {
                  await AuthService.instance.signOut();
                  if (mounted) {
                    Navigator.of(context).pushAndRemoveUntil(
                      MaterialPageRoute(
                          builder: (_) => const AuthScreen()),
                      (_) => false,
                    );
                  }
                } catch (e) {
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text('Error signing out: $e'),
                        backgroundColor: C.danger));
                  }
                }
              } else if (value == 'add_plant') {
                await _addNewPlant();
              } else if (value.startsWith('plant_')) {
                final id = value.substring(6);
                final p = _plants.firstWhere((p) => p.id == id,
                    orElse: () => _current!);
                _switchPlant(p);
              }
            },
          ),
        ),
      ],
    );
  }

  // ── Plant header ──────────────────────────────────────────────────────────────

  Widget _buildPlantHeader() {
    final plant = _current!;
    final weeks = plant.ageDays ~/ 7;
    final ageLabel = plant.ageDays < 7
        ? '${plant.ageDays} day${plant.ageDays == 1 ? '' : 's'} old'
        : weeks < 4
            ? '$weeks week${weeks == 1 ? '' : 's'} old'
            : '${plant.ageDays ~/ 30} month${plant.ageDays ~/ 30 == 1 ? '' : 's'} old';

    return _glassCard(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: C.green.withOpacity(0.12),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: C.green.withOpacity(0.25)),
            ),
            child: Image.asset(
              plant.plantImagePath,
              width: 45,
              height: 45,
              fit: BoxFit.contain,
              errorBuilder: (_, __, ___) =>
                  Text(plant.emoji, style: const TextStyle(fontSize: 31)),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(plant.name,
                    style: GoogleFonts.outfit(
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                        color: C.textPrimary)),
                Text(
                  '${plant.identifiedAs[0].toUpperCase()}${plant.identifiedAs.substring(1)} · $ageLabel',
                  style: GoogleFonts.outfit(
                      color: C.textMuted, fontSize: 17),
                ),
              ],
            ),
          ),
          if (_latestResult != null)
            _buildScoreChip(_healthScore(_latestResult!)),
        ],
      ),
    );
  }

  Widget _buildScoreChip(int score) {
    final color = _healthColor(score);
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.35)),
      ),
      child: Column(
        children: [
          Text(
            '$score',
            style: GoogleFonts.outfit(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: color),
          ),
          Text('/ 100',
              style: TextStyle(
                  fontSize: 14, color: color.withOpacity(0.7))),
        ],
      ),
    ).animate().scale(
          begin: const Offset(0.6, 0.6),
          end: const Offset(1.0, 1.0),
          duration: 450.ms,
          curve: Curves.elasticOut,
        );
  }

  // ── Last watering selector ────────────────────────────────────────────────────

  Widget _buildLastWateringSelector() {
    const options = [
      (label: 'Today', days: 0),
      (label: 'Yesterday', days: 1),
      (label: '2 days ago', days: 2),
      (label: '3+ days ago', days: 3),
    ];

    return _glassCard(
      padding:
          const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'LAST WATERED',
            style: GoogleFonts.outfit(
                fontSize: 14,
                color: C.textMuted,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.0),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            children: options.map((opt) {
              final selected = _lastWateringDays == opt.days;
              return ChoiceChip(
                label: Text(opt.label,
                    style: GoogleFonts.outfit(
                        fontSize: 17,
                        color: selected ? Colors.white : C.textMuted)),
                selected: selected,
                onSelected: (_) => setState(() {
                  _lastWateringDays = selected ? null : opt.days;
                }),
                selectedColor: C.water,
                backgroundColor: Colors.white.withOpacity(0.05),
                side: BorderSide(
                    color: selected
                        ? C.water.withOpacity(0.6)
                        : Colors.white.withOpacity(0.12)),
                showCheckmark: false,
                padding: const EdgeInsets.symmetric(
                    horizontal: 10, vertical: 4),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  // ── Upload zone ───────────────────────────────────────────────────────────────

  Widget _buildUploadZone() {
    return GestureDetector(
      onTap: _checking ? null : _pickImage,
      child: _glassCard(
        padding: EdgeInsets.zero,
        child: SizedBox(
          height: 180,
          width: double.infinity,
          child: _imageBytes != null
              ? Stack(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: Image.memory(_imageBytes!,
                          fit: BoxFit.cover, width: double.infinity),
                    ),
                    Positioned(
                      top: 8,
                      right: 8,
                      child: GestureDetector(
                        onTap: () => setState(() {
                          _imageBytes = null;
                          _imageB64 = null;
                        }),
                        child: Container(
                          padding: const EdgeInsets.all(4),
                          decoration: BoxDecoration(
                              color: Colors.black54,
                              borderRadius: BorderRadius.circular(6)),
                          child: const Icon(Icons.close,
                              color: Colors.white, size: 16),
                        ),
                      ),
                    ),
                  ],
                )
              : Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.camera_alt_outlined,
                        color: C.textMuted, size: 38),
                    const SizedBox(height: 10),
                    Text(
                      'Tap to upload a photo of your plant',
                      style: GoogleFonts.outfit(
                          color: C.textMuted, fontSize: 18),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'JPG · PNG · WEBP',
                      style: GoogleFonts.outfit(
                          color: C.textDim, fontSize: 16),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  // ── Analyse button ────────────────────────────────────────────────────────────

  Widget _buildAnalyseButton() {
    return SizedBox(
      height: 50,
      child: ElevatedButton.icon(
        onPressed: (_checking || _imageB64 == null) ? null : _checkHealth,
        icon: _checking
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: Colors.white))
            : const Icon(Icons.search, color: Colors.white, size: 18),
        label: Text(
          _checking ? 'Analysing…' : 'Analyse Plant',
          style: GoogleFonts.outfit(
              fontWeight: FontWeight.w700,
              fontSize: 20,
              color: Colors.white),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: C.green,
          disabledBackgroundColor: C.green.withOpacity(0.3),
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10)),
        ),
      ),
    );
  }

  // ── Result card ───────────────────────────────────────────────────────────────

  Widget _buildResultCard(HealthCheck check, {bool isLatest = false}) {
    final score = _healthScore(check);
    final label = _healthLabel(score);
    final scoreColor = _healthColor(score);
    final timeLabel = _formatTime(check.timestamp);

    return _HoverCard(
      child: _glassCard(
        highlight: isLatest,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Score circle + status + timestamp ─────────────────────────────
            Row(
              children: [
                Container(
                  width: 58,
                  height: 58,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: scoreColor.withOpacity(0.12),
                    border: Border.all(
                        color: scoreColor.withOpacity(0.40), width: 2),
                  ),
                  child: Center(
                    child: Text(
                      '$score',
                      style: GoogleFonts.outfit(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          color: scoreColor),
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(label,
                          style: GoogleFonts.outfit(
                              fontSize: 21,
                              fontWeight: FontWeight.w700,
                              color: scoreColor)),
                      Text(
                        isLatest
                            ? 'Latest analysis · $timeLabel'
                            : timeLabel,
                        style: GoogleFonts.outfit(
                            fontSize: 17, color: C.textMuted),
                      ),
                    ],
                  ),
                ),
                if (check.phenologicalStage.isNotEmpty)
                  _smallBadge(Icons.eco_outlined,
                      check.phenologicalStage, C.green),
              ],
            ),

            // ── Care indicators ───────────────────────────────────────────────
            if (check.waterStress > 0 ||
                check.nutrientStress > 0 ||
                check.temperatureStress > 0) ...[
              const SizedBox(height: 18),
              _sectionLabel('CARE INDICATORS'),
              const SizedBox(height: 10),
              _careBar('💧  Hydration', check.waterStress,
                  check.waterStressCat, C.water),
              const SizedBox(height: 8),
              _careBar('🌱  Nutrition', check.nutrientStress,
                  check.nutrientStressCat, C.nutrient),
              const SizedBox(height: 8),
              _careBar('🌡️  Climate', check.temperatureStress,
                  check.temperatureStressCat, C.hvac),
            ],

            // ── AI insights ───────────────────────────────────────────────────
            if (check.healthSummary.isNotEmpty) ...[
              const SizedBox(height: 18),
              _sectionLabel('AI INSIGHTS'),
              const SizedBox(height: 8),
              Text(check.healthSummary,
                  style: GoogleFonts.outfit(
                      fontSize: 18,
                      height: 1.6,
                      color: C.textPrimary)),
            ],

            // ── What to do ────────────────────────────────────────────────────
            if (check.recommendedActions.isNotEmpty) ...[
              const SizedBox(height: 18),
              _sectionLabel('WHAT TO DO'),
              const SizedBox(height: 10),
              ...check.recommendedActions.map(
                (action) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.check_circle_outline,
                          color: C.green, size: 15),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(action,
                            style: GoogleFonts.outfit(
                                fontSize: 18,
                                color: C.textPrimary,
                                height: 1.4)),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  // ── Care bar ──────────────────────────────────────────────────────────────────

  Widget _careBar(
      String label, double value, String cat, Color baseColor) {
    final catColor = switch (cat) {
      'high' => C.danger,
      'medium' => C.warn,
      _ => C.green,
    };

    return Row(
      children: [
        SizedBox(
          width: 110,
          child: Text(label,
              style: GoogleFonts.outfit(
                  fontSize: 17, color: C.textMuted)),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value.clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: Colors.white.withOpacity(0.07),
              valueColor: AlwaysStoppedAnimation<Color>(catColor),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 48,
          child: Text(cat,
              textAlign: TextAlign.right,
              style: GoogleFonts.outfit(
                  fontSize: 16,
                  color: catColor,
                  fontWeight: FontWeight.w600)),
        ),
      ],
    );
  }

  // ── Small badge ───────────────────────────────────────────────────────────────

  Widget _smallBadge(IconData icon, String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 4),
          Text(text,
              style: GoogleFonts.outfit(
                  fontSize: 16,
                  color: color,
                  fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }

  // ── Section label ─────────────────────────────────────────────────────────────

  Widget _sectionLabel(String text) {
    return Text(
      text,
      style: GoogleFonts.outfit(
        fontSize: 14,
        color: C.textMuted,
        fontWeight: FontWeight.w700,
        letterSpacing: 1.2,
      ),
    );
  }

  // ── History section ───────────────────────────────────────────────────────────

  Widget _buildHistorySection() {
    final historyToShow =
        _latestResult != null ? _history.skip(1).toList() : _history;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'HISTORY',
              style: GoogleFonts.outfit(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: C.textPrimary,
                  letterSpacing: 1.0),
            ),
            if (_loadingHistory) ...[
              const SizedBox(width: 10),
              const SizedBox(
                  width: 12,
                  height: 12,
                  child: CircularProgressIndicator(
                      strokeWidth: 1.5, color: C.textMuted)),
            ],
          ],
        ),
        const SizedBox(height: 14),
        if (!_loadingHistory && historyToShow.isEmpty)
          SizedBox(
            width: double.infinity,
            child: _glassCard(
              padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
              child: Column(
                children: [
                  const Text('📊', style: TextStyle(fontSize: 28)),
                  const SizedBox(height: 10),
                  Text('No previous checks yet',
                      style: GoogleFonts.outfit(
                          color: C.textMuted,
                          fontSize: 14,
                          fontWeight: FontWeight.w500)),
                  const SizedBox(height: 4),
                  Text(
                    'Upload a photo and analyse your plant to get started',
                    style: GoogleFonts.outfit(color: C.textDim, fontSize: 12),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          )
        else
          ...historyToShow.indexed.map(
            (entry) {
              final (idx, check) = entry;
              return Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: _buildResultCard(check),
              )
                  .animate(
                      delay: Duration(milliseconds: 60 + idx * 70))
                  .fadeIn(
                      duration: 360.ms, curve: Curves.easeOut)
                  .slideY(
                      begin: 0.06,
                      end: 0,
                      duration: 360.ms,
                      curve: Curves.easeOut);
            },
          ),
      ],
    );
  }

  // ── Upgrade banner ────────────────────────────────────────────────────────────

  Widget _buildUpgradeBanner() {
    return _HoverCard(
      child: _glassCard(
        padding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        borderColor: C.green.withOpacity(0.28),
        child: Row(
          children: [
            const Icon(Icons.workspace_premium,
                color: C.warn, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Upgrade to Plant Pro',
                      style: GoogleFonts.outfit(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: C.textPrimary)),
                  const SizedBox(height: 2),
                  Text('Unlimited plants · Advanced AI analysis',
                      style: GoogleFonts.outfit(
                          fontSize: 16, color: C.textMuted)),
                ],
              ),
            ),
            const SizedBox(width: 12),
            _upgradingToPro
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: C.green))
                : TextButton(
                    onPressed: _upgradeToPro,
                    style: TextButton.styleFrom(
                      backgroundColor: C.green,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 8),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(6)),
                    ),
                    child: Text('Upgrade',
                        style: GoogleFonts.outfit(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w700)),
                  ),
          ],
        ),
      ),
    );
  }

  // ── Helpers ───────────────────────────────────────────────────────────────────

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inHours < 1) return '${diff.inMinutes}m ago';
    if (diff.inDays < 1) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${dt.day}/${dt.month}/${dt.year}';
  }

  Widget _errorBox(String msg) {
    return _glassCard(
      padding: const EdgeInsets.all(12),
      borderColor: C.danger.withOpacity(0.4),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: C.danger, size: 16),
          const SizedBox(width: 8),
          Expanded(
              child: Text(msg,
                  style: GoogleFonts.outfit(
                      color: C.danger, fontSize: 18))
          ),
        ],
      ),
    );
  }
}
