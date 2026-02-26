// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../theme.dart';
import '../../services/auth_service.dart';
import '../../services/api_client.dart';
import '../auth_screen.dart';
import '../../services/firestore_service.dart';
import '../../services/gemini_service.dart';
import '../../models/plant_record.dart';
import '../../models/health_check.dart';
import 'plant_onboarding_screen.dart';

const int _kFreePlanLimit = 3;

class HomeHealthScreen extends StatefulWidget {
  final PlantRecord? initialPlant;

  const HomeHealthScreen({super.key, this.initialPlant});

  @override
  State<HomeHealthScreen> createState() => _HomeHealthScreenState();
}

class _HomeHealthScreenState extends State<HomeHealthScreen> {
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

  bool get _atPlantLimit => !_isPro && _plants.length >= _kFreePlanLimit;

  @override
  void initState() {
    super.initState();
    _init();
  }

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
        SnackBar(content: Text('Could not start checkout: $e'), backgroundColor: C.danger),
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
      MaterialPageRoute(builder: (_) => const PlantOnboardingScreen(isFirstPlant: false)),
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
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: const Row(
          children: [
            Icon(Icons.workspace_premium, color: C.warn, size: 22),
            SizedBox(width: 10),
            Text('Plant limit reached',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          ],
        ),
        content: Text(
          'Free plan supports up to $_kFreePlanLimit plants.\n'
          'Upgrade to Pro for unlimited plants and advanced AI analysis.',
          style: const TextStyle(color: C.textMuted, fontSize: 14, height: 1.5),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Maybe later', style: TextStyle(color: C.textMuted)),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              _upgradeToPro();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: C.green,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: const Text('Upgrade to Pro',
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  // ── Health score helpers ──────────────────────────────────────────────────────

  int _healthScore(HealthCheck check) {
    final avg = (check.waterStress + check.nutrientStress + check.temperatureStress) / 3.0;
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
                builder: (_) => const PlantOnboardingScreen(isFirstPlant: true)),
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
      body: LayoutBuilder(
        builder: (context, constraints) {
          final hPad = constraints.maxWidth < 600 ? 16.0 : 24.0;
          return Center(
            child: SingleChildScrollView(
              padding: EdgeInsets.symmetric(horizontal: hPad, vertical: 20),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 680),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildPlantHeader(),
                    const SizedBox(height: 20),
                    _buildLastWateringSelector(),
                    const SizedBox(height: 16),
                    _buildUploadZone(),
                    if (_checkError != null) ...[
                      const SizedBox(height: 10),
                      _errorBox(_checkError!),
                    ],
                    const SizedBox(height: 14),
                    _buildAnalyseButton(),
                    if (!_isPro) ...[
                      const SizedBox(height: 16),
                      _buildUpgradeBanner(),
                    ],
                    if (_latestResult != null) ...[
                      const SizedBox(height: 28),
                      _buildResultCard(_latestResult!, isLatest: true),
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
    );
  }

  // ── AppBar ────────────────────────────────────────────────────────────────────

  AppBar _buildAppBar() {
    final plant = _current!;
    return AppBar(
      backgroundColor: C.bg,
      elevation: 0,
      title: const Row(
        children: [
          Text('🌿', style: TextStyle(fontSize: 18)),
          SizedBox(width: 8),
          Text('My Garden',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        ],
      ),
      actions: [
        if (!_isPro)
          GestureDetector(
            onTap: _upgradingToPro ? null : _upgradeToPro,
            child: Container(
              margin: const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: C.warn.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: C.warn.withValues(alpha: 0.4)),
              ),
              child: const Text(
                'FREE',
                style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                    color: C.warn,
                    letterSpacing: 0.8),
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.only(right: 12),
          child: PopupMenuButton<String>(
            offset: const Offset(0, 48),
            color: C.panel,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            tooltip: 'Switch plant',
            child: CircleAvatar(
              radius: 18,
              backgroundColor: C.green.withValues(alpha: 0.15),
              child: Text(plant.emoji, style: const TextStyle(fontSize: 17)),
            ),
            itemBuilder: (_) => [
              PopupMenuItem<String>(
                enabled: false,
                height: 36,
                child: Row(
                  children: [
                    const Text(
                      'My plants',
                      style: TextStyle(
                          fontSize: 11,
                          color: C.textMuted,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.8),
                    ),
                    const Spacer(),
                    Text(
                      _isPro
                          ? '${_plants.length}'
                          : '${_plants.length} / $_kFreePlanLimit',
                      style: const TextStyle(fontSize: 11, color: C.textDim),
                    ),
                  ],
                ),
              ),
              ..._plants.map(
                (p) => PopupMenuItem<String>(
                  value: 'plant_${p.id}',
                  child: Row(
                    children: [
                      Text(p.emoji, style: const TextStyle(fontSize: 16)),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          p.name,
                          style: TextStyle(
                            color: p.id == _current!.id ? C.green : C.textPrimary,
                            fontWeight: p.id == _current!.id
                                ? FontWeight.w600
                                : FontWeight.normal,
                          ),
                        ),
                      ),
                      if (p.id == _current!.id)
                        const Icon(Icons.check, size: 14, color: C.green),
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
                        : const Icon(Icons.add, size: 16, color: C.green),
                    const SizedBox(width: 10),
                    Text(
                      'Add new plant',
                      style: TextStyle(
                          color: _atPlantLimit ? C.textMuted : C.green,
                          fontSize: 13),
                    ),
                    if (_atPlantLimit) ...[
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 5, vertical: 2),
                        decoration: BoxDecoration(
                          color: C.warn.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text('PRO',
                            style: TextStyle(
                                fontSize: 9,
                                color: C.warn,
                                fontWeight: FontWeight.w800)),
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
                      style: TextStyle(color: C.textMuted, fontSize: 13)),
                ]),
              ),
            ],
            onSelected: (value) async {
              if (value == 'sign_out') {
                try {
                  await AuthService.instance.signOut();
                  if (mounted) {
                    Navigator.of(context).pushAndRemoveUntil(
                      MaterialPageRoute(builder: (_) => const AuthScreen()),
                      (_) => false,
                    );
                  }
                } catch (e) {
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                          content: Text('Error signing out: $e'),
                          backgroundColor: C.danger),
                    );
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

    return Row(
      children: [
        Container(
          width: 52,
          height: 52,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: C.green.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: C.green.withValues(alpha: 0.2)),
          ),
          child: Text(plant.emoji, style: const TextStyle(fontSize: 26)),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(plant.name,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w700)),
              Text(
                '${plant.identifiedAs[0].toUpperCase()}${plant.identifiedAs.substring(1)} · $ageLabel',
                style: const TextStyle(color: C.textMuted, fontSize: 13),
              ),
            ],
          ),
        ),
        if (_latestResult != null) _buildScoreChip(_healthScore(_latestResult!)),
      ],
    );
  }

  Widget _buildScoreChip(int score) {
    final color = _healthColor(score);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          Text('$score',
              style: TextStyle(
                  fontSize: 18, fontWeight: FontWeight.w800, color: color)),
          Text('/ 100',
              style: TextStyle(
                  fontSize: 9, color: color.withValues(alpha: 0.7))),
        ],
      ),
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

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Last watered',
            style: TextStyle(
                fontSize: 12,
                color: C.textMuted,
                fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: options.map((opt) {
            final selected = _lastWateringDays == opt.days;
            return ChoiceChip(
              label: Text(opt.label,
                  style: TextStyle(
                      fontSize: 12,
                      color: selected ? Colors.white : C.textMuted)),
              selected: selected,
              onSelected: (_) => setState(() {
                _lastWateringDays = selected ? null : opt.days;
              }),
              selectedColor: C.water,
              backgroundColor: C.panelAlt,
              side: BorderSide(
                  color: selected
                      ? C.water.withValues(alpha: 0.6)
                      : C.border),
              showCheckmark: false,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            );
          }).toList(),
        ),
      ],
    );
  }

  // ── Upload zone ───────────────────────────────────────────────────────────────

  Widget _buildUploadZone() {
    return GestureDetector(
      onTap: _checking ? null : _pickImage,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        height: 180,
        decoration: BoxDecoration(
          color: C.panelAlt,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: _imageBytes != null
                ? C.green.withValues(alpha: 0.5)
                : C.border,
            width: _imageBytes != null ? 1.5 : 1,
          ),
        ),
        child: _imageBytes != null
            ? Stack(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(11),
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
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Icon(Icons.close,
                            color: Colors.white, size: 16),
                      ),
                    ),
                  ),
                ],
              )
            : Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  Icon(Icons.camera_alt_outlined,
                      color: C.textMuted, size: 38),
                  SizedBox(height: 10),
                  Text('Tap to upload a photo of your plant',
                      style: TextStyle(color: C.textMuted, fontSize: 13)),
                  SizedBox(height: 4),
                  Text('JPG · PNG · WEBP',
                      style: TextStyle(color: C.textDim, fontSize: 11)),
                ],
              ),
      ),
    );
  }

  // ── Analyse button ────────────────────────────────────────────────────────────

  Widget _buildAnalyseButton() {
    return SizedBox(
      height: 48,
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
          style: const TextStyle(
              fontWeight: FontWeight.w600, fontSize: 15, color: Colors.white),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: C.green,
          disabledBackgroundColor: C.green.withValues(alpha: 0.3),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
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

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: isLatest ? C.green.withValues(alpha: 0.05) : C.panelAlt,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
            color: isLatest ? C.green.withValues(alpha: 0.25) : C.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Score circle + status + timestamp ─────────────────────────────────
          Row(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: scoreColor.withValues(alpha: 0.1),
                  border: Border.all(
                      color: scoreColor.withValues(alpha: 0.35), width: 2),
                ),
                child: Center(
                  child: Text('$score',
                      style: TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                          color: scoreColor)),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: scoreColor)),
                    Text(
                      isLatest ? 'Latest analysis · $timeLabel' : timeLabel,
                      style: const TextStyle(fontSize: 12, color: C.textMuted),
                    ),
                  ],
                ),
              ),
              if (check.phenologicalStage.isNotEmpty)
                _smallBadge(
                    Icons.eco_outlined, check.phenologicalStage, C.green),
            ],
          ),

          // ── Care indicators ───────────────────────────────────────────────────
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

          // ── AI insights ───────────────────────────────────────────────────────
          if (check.healthSummary.isNotEmpty) ...[
            const SizedBox(height: 18),
            _sectionLabel('AI INSIGHTS'),
            const SizedBox(height: 8),
            Text(check.healthSummary,
                style: const TextStyle(
                    fontSize: 14, height: 1.55, color: C.textPrimary)),
          ],

          // ── What to do ────────────────────────────────────────────────────────
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
                          style: const TextStyle(
                              fontSize: 13,
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
              style: const TextStyle(fontSize: 12, color: C.textMuted)),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value.clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: C.border,
              valueColor: AlwaysStoppedAnimation<Color>(catColor),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 48,
          child: Text(cat,
              textAlign: TextAlign.right,
              style: TextStyle(
                  fontSize: 11,
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
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 4),
          Text(text,
              style: TextStyle(
                  fontSize: 11,
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
      style: const TextStyle(
          fontSize: 10,
          color: C.textMuted,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.8),
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
            const Text('History',
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: C.textPrimary)),
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
          Container(
            padding: const EdgeInsets.symmetric(vertical: 28),
            alignment: Alignment.center,
            child: const Column(
              children: [
                Text('📊', style: TextStyle(fontSize: 32)),
                SizedBox(height: 10),
                Text('No previous checks yet',
                    style: TextStyle(
                        color: C.textMuted,
                        fontSize: 14,
                        fontWeight: FontWeight.w500)),
                SizedBox(height: 4),
                Text(
                  'Upload a photo and analyse your plant to get started',
                  style: TextStyle(color: C.textDim, fontSize: 12),
                ),
              ],
            ),
          )
        else
          ...historyToShow.map(
            (c) => Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: _buildResultCard(c),
            ),
          ),
      ],
    );
  }

  // ── Upgrade banner ────────────────────────────────────────────────────────────

  Widget _buildUpgradeBanner() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            C.green.withValues(alpha: 0.10),
            C.warn.withValues(alpha: 0.07),
          ],
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
        ),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: C.green.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          const Icon(Icons.workspace_premium, color: C.warn, size: 20),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Upgrade to Plant Pro',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: C.textPrimary)),
                SizedBox(height: 2),
                Text('Unlimited plants · Advanced AI analysis',
                    style: TextStyle(fontSize: 11, color: C.textMuted)),
              ],
            ),
          ),
          const SizedBox(width: 12),
          _upgradingToPro
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child:
                      CircularProgressIndicator(strokeWidth: 2, color: C.green))
              : TextButton(
                  onPressed: _upgradeToPro,
                  style: TextButton.styleFrom(
                    backgroundColor: C.green,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 8),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(6)),
                  ),
                  child: const Text('Upgrade',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w700)),
                ),
        ],
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
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: C.danger.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: C.danger.withValues(alpha: 0.4)),
      ),
      child: Text(msg, style: const TextStyle(color: C.danger, fontSize: 13)),
    );
  }
}
