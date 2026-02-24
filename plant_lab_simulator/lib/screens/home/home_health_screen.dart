// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../theme.dart';
import '../../services/auth_service.dart';
import '../auth_screen.dart';
import '../../services/firestore_service.dart';
import '../../services/gemini_service.dart';
import '../../models/plant_record.dart';
import '../../models/health_check.dart';
import 'plant_onboarding_screen.dart';

/// Main Home Plant screen.
///
/// Shows:
///  - Top-right avatar with plant switcher pop-up menu
///  - Optional last-watering selector
///  - Image upload zone + "Check Health" button
///  - Latest health result (stress bars + visual scores + summary + action chips)
///  - Scrollable history of previous checks
class HomeHealthScreen extends StatefulWidget {
  /// Pre-selected plant, or null to auto-load the first plant.
  final PlantRecord? initialPlant;

  const HomeHealthScreen({super.key, this.initialPlant});

  @override
  State<HomeHealthScreen> createState() => _HomeHealthScreenState();
}

class _HomeHealthScreenState extends State<HomeHealthScreen> {
  // ── Plant list & selection ───────────────────────────────────────────────────
  List<PlantRecord> _plants = [];
  PlantRecord? _current;
  bool _loadingPlants = true;

  // ── Image upload ─────────────────────────────────────────────────────────────
  Uint8List? _imageBytes;
  String? _imageB64;

  // ── Optional env hints ────────────────────────────────────────────────────────
  // null = not provided; 0 = today, 1 = yesterday, etc.
  int? _lastWateringDays;

  // ── Health check state ────────────────────────────────────────────────────────
  bool _checking = false;
  String? _checkError;
  HealthCheck? _latestResult;

  // ── History ──────────────────────────────────────────────────────────────────
  List<HealthCheck> _history = [];
  bool _loadingHistory = false;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
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

  // ── Image pick ───────────────────────────────────────────────────────────────

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

  // ── Health check ─────────────────────────────────────────────────────────────

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
      // Backend pipeline: Gemini visual analysis → XGBoost → recommendations
      // → Firestore persistence (server-side).  Returns enriched HealthCheck.
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

  // ── Plant switch ─────────────────────────────────────────────────────────────

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
    final result = await Navigator.push<PlantRecord>(
      context,
      MaterialPageRoute(
        builder: (_) => const PlantOnboardingScreen(isFirstPlant: false),
      ),
    );
    if (result != null && mounted) {
      setState(() => _plants = [..._plants, result]);
      _switchPlant(result);
    }
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
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 600),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildPlantHeader(),
                const SizedBox(height: 24),
                _buildLastWateringSelector(),
                const SizedBox(height: 16),
                _buildUploadZone(),
                if (_checkError != null) ...[
                  const SizedBox(height: 12),
                  _errorBox(_checkError!),
                ],
                const SizedBox(height: 16),
                _buildCheckButton(),
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
      ),
    );
  }

  // ── AppBar ────────────────────────────────────────────────────────────────────

  AppBar _buildAppBar() {
    final plant = _current!;
    return AppBar(
      backgroundColor: C.bg,
      elevation: 0,
      title: const Text(
        'Home Plant',
        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
      actions: [
        Padding(
          padding: const EdgeInsets.only(right: 12),
          child: PopupMenuButton<String>(
            offset: const Offset(0, 48),
            color: C.panel,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            tooltip: 'Switch plant',
            child: CircleAvatar(
              radius: 18,
              backgroundColor: C.green.withValues(alpha: 0.15),
              child: Text(
                plant.emoji,
                style: const TextStyle(fontSize: 17),
              ),
            ),
            itemBuilder: (_) => [
              PopupMenuItem<String>(
                enabled: false,
                height: 36,
                child: Text(
                  'Your plants',
                  style: TextStyle(
                      fontSize: 11,
                      color: C.textMuted,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.8),
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
                          child: Text(p.name,
                              style: TextStyle(
                                  color: p.id == _current!.id
                                      ? C.green
                                      : C.textPrimary,
                                  fontWeight: p.id == _current!.id
                                      ? FontWeight.w600
                                      : FontWeight.normal))),
                      if (p.id == _current!.id)
                        const Icon(Icons.check, size: 14, color: C.green),
                    ],
                  ),
                ),
              ),
              const PopupMenuDivider(),
              PopupMenuItem<String>(
                value: 'add_plant',
                child: Row(children: const [
                  Icon(Icons.add, size: 16, color: C.green),
                  SizedBox(width: 10),
                  Text('Add new plant',
                      style: TextStyle(color: C.green, fontSize: 13)),
                ]),
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
                      MaterialPageRoute(
                          builder: (_) => const AuthScreen()),
                      (_) => false,
                    );
                  }
                } catch (e) {
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('Error signing out: $e'),
                        backgroundColor: C.danger,
                      ),
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
        Column(
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
      ],
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
        const Text(
          'Last watered',
          style: TextStyle(
              fontSize: 12, color: C.textMuted, fontWeight: FontWeight.w600),
        ),
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
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
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
                  Icon(Icons.add_photo_alternate_outlined,
                      color: C.textMuted, size: 40),
                  SizedBox(height: 10),
                  Text('Tap to upload a photo of your plant',
                      style: TextStyle(color: C.textMuted, fontSize: 13)),
                  SizedBox(height: 4),
                  Text('JPG, PNG, WEBP',
                      style: TextStyle(color: C.textDim, fontSize: 11)),
                ],
              ),
      ),
    );
  }

  // ── Check health button ───────────────────────────────────────────────────────

  Widget _buildCheckButton() {
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
            : const Icon(Icons.health_and_safety_outlined,
                color: Colors.white, size: 18),
        label: Text(
          _checking ? 'Analysing…' : 'Check Health',
          style: const TextStyle(
              fontWeight: FontWeight.w600,
              fontSize: 15,
              color: Colors.white),
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
    final timeLabel = _formatTime(check.timestamp);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isLatest ? C.green.withValues(alpha: 0.06) : C.panelAlt,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color:
              isLatest ? C.green.withValues(alpha: 0.3) : C.border,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header row ──────────────────────────────────────────────────────
          Row(
            children: [
              Icon(
                Icons.health_and_safety,
                color: isLatest ? C.green : C.textMuted,
                size: 15,
              ),
              const SizedBox(width: 6),
              Text(
                isLatest ? 'Latest result' : timeLabel,
                style: TextStyle(
                  fontSize: 11,
                  color: isLatest ? C.green : C.textMuted,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.6,
                ),
              ),
              if (isLatest) ...[
                const Spacer(),
                Text(timeLabel,
                    style:
                        const TextStyle(color: C.textDim, fontSize: 11)),
              ],
            ],
          ),

          // ── Phenological stage + model badge ────────────────────────────────
          if (check.phenologicalStage.isNotEmpty &&
              check.phenologicalStage != 'vegetative' ||
              check.modelUsed.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              children: [
                if (check.phenologicalStage.isNotEmpty)
                  _smallBadge(
                    Icons.eco_outlined,
                    check.phenologicalStage,
                    C.green,
                  ),
                if (check.modelUsed.isNotEmpty)
                  _smallBadge(
                    Icons.memory_outlined,
                    check.modelUsed,
                    C.textDim,
                  ),
              ],
            ),
          ],

          // ── Stress prediction bars ────────────────────────────────────────────
          if (check.waterStress > 0 ||
              check.nutrientStress > 0 ||
              check.temperatureStress > 0) ...[
            const SizedBox(height: 14),
            _sectionLabel('Stress Levels'),
            const SizedBox(height: 8),
            _stressBar('Water', check.waterStress, check.waterStressCat,
                C.water),
            const SizedBox(height: 6),
            _stressBar('Nutrient', check.nutrientStress,
                check.nutrientStressCat, C.nutrient),
            const SizedBox(height: 6),
            _stressBar('Temperature', check.temperatureStress,
                check.temperatureStressCat, C.hvac),
          ],

          // ── Visual scores ─────────────────────────────────────────────────────
          if (check.leafYellowingScore > 0 ||
              check.leafDroopScore > 0 ||
              check.necrosisScore > 0) ...[
            const SizedBox(height: 14),
            _sectionLabel('Visual Scores'),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                    child: _visualScore(
                        'Yellowing', check.leafYellowingScore)),
                const SizedBox(width: 8),
                Expanded(
                    child:
                        _visualScore('Droop', check.leafDroopScore)),
                const SizedBox(width: 8),
                Expanded(
                    child:
                        _visualScore('Necrosis', check.necrosisScore)),
              ],
            ),
          ],

          // ── Health summary ─────────────────────────────────────────────────────
          const SizedBox(height: 12),
          Text(
            check.healthSummary,
            style: const TextStyle(fontSize: 14, height: 1.5),
          ),

          // ── Recommended actions ────────────────────────────────────────────────
          if (check.recommendedActions.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: check.recommendedActions.map((action) {
                return Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: C.green.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                        color: C.green.withValues(alpha: 0.25)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.task_alt,
                          color: C.green, size: 12),
                      const SizedBox(width: 5),
                      Text(action,
                          style: const TextStyle(
                              color: C.green,
                              fontSize: 12,
                              fontWeight: FontWeight.w500)),
                    ],
                  ),
                );
              }).toList(),
            ),
          ],
        ],
      ),
    );
  }

  // ── Stress bar ────────────────────────────────────────────────────────────────

  Widget _stressBar(
      String label, double value, String cat, Color baseColor) {
    final catColor = switch (cat) {
      'high' => C.danger,
      'medium' => C.warn,
      _ => C.green,
    };

    return Row(
      children: [
        SizedBox(
          width: 88,
          child: Text(label,
              style:
                  const TextStyle(fontSize: 12, color: C.textMuted)),
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
        Container(
          width: 52,
          alignment: Alignment.centerRight,
          child: Text(
            cat,
            style: TextStyle(
                fontSize: 11,
                color: catColor,
                fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }

  // ── Visual score mini-widget ──────────────────────────────────────────────────

  Widget _visualScore(String label, double value) {
    final pct = (value * 100).round();
    final color = value < 0.3
        ? C.green
        : value < 0.6
            ? C.warn
            : C.danger;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        children: [
          Text('$pct%',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: color)),
          const SizedBox(height: 2),
          Text(label,
              style:
                  const TextStyle(fontSize: 10, color: C.textDim)),
        ],
      ),
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
          fontSize: 11,
          color: C.textMuted,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.5),
    );
  }

  // ── History section ───────────────────────────────────────────────────────────

  Widget _buildHistorySection() {
    final historyToShow = _latestResult != null
        ? _history.skip(1).toList()
        : _history;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'Previous checks',
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: C.textMuted),
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
        const SizedBox(height: 12),
        if (!_loadingHistory && historyToShow.isEmpty)
          const Text(
            'No previous checks yet.',
            style: TextStyle(color: C.textDim, fontSize: 13),
          )
        else
          ...historyToShow
              .map((c) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _buildResultCard(c),
                  ))
              .toList(),
      ],
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
      child: Text(msg,
          style: const TextStyle(color: C.danger, fontSize: 13)),
    );
  }
}
