import 'dart:math';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme.dart';
import '../services/api_client.dart';
import '../widgets/shared.dart';
import '../widgets/plant_visual.dart';
import '../widgets/phenology_bar.dart';
import '../widgets/sparkline.dart';
import '../models/plant_state.dart';
import 'diagnostics.dart';
import 'executor_log.dart';
import 'monitor_settings.dart';
import 'metrics_viewer.dart';
import 'mqtt_settings_screen.dart';
import '../services/auth_service.dart';
import 'auth_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiClient _api = ApiClient();

  // UI state — all data comes raw from Flask
  bool isLoading = false;
  bool simulationRunning = false;
  Map<String, dynamic>?
      simulationState; // raw state dict from /simulation/state
  Map<String, dynamic>? simulationSummary; // raw summary dict
  Map<String, dynamic>? simulationConfig; // raw config dict
  List<Map<String, dynamic>> history = [];
  Map<String, dynamic>? agentStats;
  List<PlantProfile> availablePlants = [];
  String? selectedPlant;
  String? error;

  // Simulation settings
  int _timeGapHours = 1;
  int _simulationDays = 30;
  String _simulationMode = 'speed';

  // User profile (loaded from backend after login)
  Map<String, dynamic>? _userProfile;
  bool _profileLoading = false;
  bool _profileSaving = false;
  double _potSizeL = 5.0;
  bool _dailyRegimeEnabled = true;

  // Notification bell — nutrient stress alerts
  final GlobalKey _notifBellKey = GlobalKey();
  bool _notifyNutrientStress = false;

  // ── helpers to read backend state fields safely ─────────────────────────────

  double _d(String key, [double fallback = 0.0]) =>
      (simulationState?[key] ?? fallback).toDouble();

  int _i(String key, [int fallback = 0]) =>
      (simulationState?[key] ?? fallback).toInt();

  bool _b(String key, [bool fallback = true]) =>
      simulationState?[key] as bool? ?? fallback;

  /// phenological_stage comes as a string from the backend state dict
  GrowthStage get _stage =>
      GrowthStage.fromString(simulationState?['phenological_stage'] as String?);

  // ── lifecycle ────────────────────────────────────────────────────────────────

  @override
  void initState() {
    super.initState();
    _loadAvailablePlants();
    _loadUserProfile();
    _startPolling();
  }

  @override
  void dispose() {
    super.dispose();
  }

  void _startPolling() {
    _periodicUpdate();
  }

  Future<void> _periodicUpdate() async {
    while (mounted) {
      try {
        final stateResp = await _api.getSimulationState();
        if (!mounted) return;

        final wasRunning = simulationRunning;
        final nowRunning = stateResp.running;
        final hasState = stateResp.success && stateResp.state.isNotEmpty;
        final isAlive = stateResp.state['is_alive'] as bool? ?? true;

        setState(() {
          simulationRunning = nowRunning;
          // Only update simulationState if:
          // 1. Simulation is currently running, OR
          // 2. Simulation was running but just ended (keep final state visible)
          // This prevents repopulating state after user intentionally resets
          if (hasState && (nowRunning || wasRunning)) {
            simulationState = stateResp.state;
            simulationSummary = stateResp.summary;
            simulationConfig = stateResp.config;
          }
          error = null;
        });

        // Notify user when simulation ends (plant died or finished)
        if (wasRunning && !nowRunning && mounted) {
          final deathReason = simulationState?['death_reason'] as String?;
          final msg = !isAlive
              ? '💀 Plant died: ${deathReason ?? "unknown"}'
              : '✅ Simulation complete';
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(msg),
            backgroundColor: isAlive ? C.green : C.danger,
            duration: const Duration(seconds: 6),
          ));
        }

        if (nowRunning) {
          final histResp = await _api.getSimulationHistory(limit: 100);
          final agentResp = await _api.getAgentStatus();

          if (!mounted) return;
          setState(() {
            history = histResp.history;
            agentStats = agentResp.statistics;
          });
        }
      } catch (e) {
        if (!mounted) return;
        setState(() {
          error = e.toString();
        });
      }

      await Future.delayed(const Duration(seconds: 2));
    }
  }

  Future<void> _loadUserProfile() async {
    if (mounted) setState(() => _profileLoading = true);
    try {
      final profile = await _api.getProfile();
      if (!mounted || profile == null) return;
      const validSteps = [1, 2, 3, 6, 12, 24];
      const validPots = [2.0, 5.0, 10.0, 20.0];
      final rawStep = (profile['step_size'] as num?)?.toInt() ?? 1;
      final rawPot = (profile['pot_size_L'] as num?)?.toDouble() ?? 5.0;
      setState(() {
        _userProfile = profile;
        _timeGapHours = validSteps.contains(rawStep) ? rawStep : 1;
        _potSizeL = validPots.contains(rawPot) ? rawPot : 5.0;
        _dailyRegimeEnabled = profile['daily_regime_enabled'] as bool? ?? true;
        _simulationDays = (profile['simulation_days'] as num?)?.toInt() ?? 30;
        // Set default plant from profile once plants are loaded
        final defPlant = profile['default_plant'] as String?;
        if (defPlant != null && availablePlants.any((p) => p.id == defPlant)) {
          selectedPlant = defPlant;
        }
      });
    } catch (_) {
      // Non-fatal — dashboard works without profile
    } finally {
      if (mounted) setState(() => _profileLoading = false);
    }
  }

  Future<void> _saveUserProfile() async {
    setState(() => _profileSaving = true);
    try {
      final updated = await _api.updateProfile({
        'step_size': _timeGapHours,
        'pot_size_L': _potSizeL,
        'daily_regime_enabled': _dailyRegimeEnabled,
        'default_plant': selectedPlant ?? 'tomato_standard',
      });
      if (!mounted) return;
      setState(() => _userProfile = updated);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Settings saved'),
            backgroundColor: C.green,
            duration: Duration(seconds: 2)),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('Failed to save: $e'), backgroundColor: C.danger),
      );
    } finally {
      if (mounted) setState(() => _profileSaving = false);
    }
  }

  Future<void> _loadAvailablePlants() async {
    try {
      final response = await _api.getAvailablePlants();
      if (!mounted) return;
      setState(() {
        availablePlants = response.plants;
        if (availablePlants.isNotEmpty && selectedPlant == null) {
          selectedPlant = availablePlants.first.id;
        }
        // Apply profile default_plant now that plants are loaded
        final defPlant = _userProfile?['default_plant'] as String?;
        if (defPlant != null && availablePlants.any((p) => p.id == defPlant)) {
          selectedPlant = defPlant;
        }
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('Failed to load plants: $e'),
            backgroundColor: C.danger),
      );
    }
  }

  Future<void> _startSimulation() async {
    if (selectedPlant == null) return;
    setState(() => isLoading = true);
    try {
      final response = await _api.startSimulation(
        plantName: selectedPlant!,
        mode: 'speed',
        hoursPerTick: _timeGapHours,
        days: _simulationDays,
        tickDelay: 0.1,
        dailyRegime: _dailyRegimeEnabled,
        monitorEnabled: true,
      );
      if (!mounted) return;
      if (response.success) {
        // Immediately fetch the simulation state to populate the running view
        final stateResp = await _api.getSimulationState();
        if (!mounted) return;
        
        setState(() {
          simulationRunning = true;
          if (stateResp.success && stateResp.state.isNotEmpty) {
            simulationState = stateResp.state;
            simulationSummary = stateResp.summary;
            simulationConfig = stateResp.config;
          }
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('✅ ${response.message}'), backgroundColor: C.green),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('Error: ${response.error}'),
              backgroundColor: C.danger),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed: $e'), backgroundColor: C.danger),
      );
    } finally {
      if (mounted) setState(() => isLoading = false);
    }
  }

  Future<void> _stopSimulation() async {
    setState(() => isLoading = true);
    try {
      final response = await _api.stopSimulation();
      if (!mounted) return;
      if (response.success) {
        setState(() {
          simulationRunning = false;
          simulationState = null;
          history = [];
          agentStats = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('⏹️ ${response.message}'),
              backgroundColor: C.green),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('Error stopping: $e'), backgroundColor: C.danger),
      );
    } finally {
      if (mounted) setState(() => isLoading = false);
    }
  }

  Future<void> _executeAction(
      ActionType type, Map<String, dynamic> params) async {
    try {
      final response = await _api.executeAction(type.backendName, params);
      if (!mounted) return;
      if (response.success) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('✅ ${response.message}'), backgroundColor: C.green),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ ${response.error ?? "Action failed"}'),
            backgroundColor: C.danger,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: C.danger),
      );
    }
  }

  /// Shows a dialog to collect parameters for [type], then calls [_executeAction].
  /// Each field is pre-filled with the current simulation state value.
  Future<void> _promptAndExecute(ActionType type) async {
    final Map<String, TextEditingController> controllers = {};

    switch (type) {
      case ActionType.light:
        controllers['target_PAR'] = TextEditingController(
            text: _d('light_PAR', 600).toStringAsFixed(0));
      case ActionType.water:
        controllers['volume_L'] =
            TextEditingController(text: '0.2');
      case ActionType.nutrient:
        controllers['N_dose_ppm'] = TextEditingController(text: '50');
        controllers['P_dose_ppm'] = TextEditingController(text: '15');
        controllers['K_dose_ppm'] = TextEditingController(text: '40');
      case ActionType.hvac:
        controllers['target_temp_C'] = TextEditingController(
            text: _d('air_temp', 25).toStringAsFixed(1));
      case ActionType.humidity:
        controllers['target_RH'] = TextEditingController(
            text: _d('relative_humidity', 65).toStringAsFixed(1));
      case ActionType.ventilation:
        controllers['fan_speed'] = TextEditingController(text: '50');
    }

    final labels = {
      'target_PAR': 'Target PAR (µmol/m²/s, 0–2000)',
      'volume_L': 'Volume (L, 0–10)',
      'N_dose_ppm': 'Nitrogen (ppm)',
      'P_dose_ppm': 'Phosphorus (ppm)',
      'K_dose_ppm': 'Potassium (ppm)',
      'target_temp_C': 'Target temperature (°C)',
      'target_RH': 'Target humidity (%)',
      'fan_speed': 'Fan speed (%, 0–100)',
    };

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: C.panel,
        title: Text('Configure ${type.name}',
            style: const TextStyle(color: C.textPrimary)),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: controllers.entries.map((e) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: TextField(
                  controller: e.value,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  style: const TextStyle(color: C.textPrimary),
                  decoration: InputDecoration(
                    labelText: labels[e.key] ?? e.key,
                    labelStyle: const TextStyle(color: C.textMuted),
                    enabledBorder: const OutlineInputBorder(
                        borderSide: BorderSide(color: C.border)),
                    focusedBorder: const OutlineInputBorder(
                        borderSide: BorderSide(color: C.green)),
                  ),
                ),
              );
            }).toList(),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child:
                  const Text('Cancel', style: TextStyle(color: C.textMuted))),
          ElevatedButton(
              onPressed: () => Navigator.pop(ctx, true),
              style: ElevatedButton.styleFrom(backgroundColor: C.green),
              child: const Text('Apply')),
        ],
      ),
    );

    if (confirmed != true) return;

    final params = controllers.map((k, c) {
      final raw = c.text.trim();
      return MapEntry(k, double.tryParse(raw) ?? 0.0);
    });

    await _executeAction(type, params);
  }

  // ── Daily regime dialog ───────────────────────────────────────────────────

  Future<void> _showRegimeDialog() async {
    // Pre-fill from current config if available
    final regime = (simulationConfig?['regime'] as Map?)?.cast<String, dynamic>() ?? {};
    bool enabled = regime['enabled'] as bool? ?? _dailyRegimeEnabled;
    bool co2On   = regime['co2_enrichment'] as bool? ?? true;
    bool notifyN = simulationConfig?['notify_nutrient_stress'] as bool? ?? _notifyNutrientStress;

    final cWaterHour  = TextEditingController(text: '${regime['watering_hour'] ?? 7}');
    final cVentHour   = TextEditingController(text: '${regime['ventilation_hour'] ?? 12}');
    final cWaterAmt   = TextEditingController(text: '${regime['water_amount'] ?? 0.3}');
    final cFanSpeed   = TextEditingController(text: '${regime['fan_speed'] ?? 20}');
    final cCo2Target  = TextEditingController(text: '${regime['co2_target'] ?? 1000}');
    final cTargetTemp = TextEditingController(
        text: regime['target_temp'] != null ? '${regime['target_temp']}' : '');
    final cTargetPar  = TextEditingController(
        text: regime['target_par'] != null ? '${regime['target_par']}' : '');

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          backgroundColor: C.surface,
          title: const Text('Daily Regime Settings',
              style: TextStyle(color: C.textPrimary)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Enable toggle
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('Enable regime',
                        style: TextStyle(color: C.textPrimary)),
                    Switch(
                      value: enabled,
                      onChanged: (v) => setS(() => enabled = v),
                      activeColor: C.green,
                    ),
                  ],
                ),
                const Divider(color: C.border, height: 20),
                _regimeField(cTargetTemp, 'Target air temp (°C, blank = plant profile)'),
                _regimeField(cTargetPar,  'Target PAR (µmol/m²/s, blank = plant profile)'),
                _regimeField(cWaterAmt,   'Water per event (L)'),
                _regimeField(cWaterHour,  'Watering hour (0–23)'),
                _regimeField(cFanSpeed,   'Fan speed (%, 0–100)'),
                _regimeField(cVentHour,   'Ventilation hour (0–23)'),
                _regimeField(cCo2Target,  'CO2 target (ppm)'),
                // CO2 enrichment toggle
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('CO2 enrichment',
                        style: TextStyle(color: C.textPrimary)),
                    Switch(
                      value: co2On,
                      onChanged: (v) => setS(() => co2On = v),
                      activeColor: C.green,
                    ),
                  ],
                ),
                const Divider(color: C.border, height: 20),
                // Nutrient stress notification checkbox
                Row(
                  children: [
                    Checkbox(
                      value: notifyN,
                      onChanged: (v) => setS(() => notifyN = v ?? false),
                      activeColor: C.green,
                    ),
                    const Expanded(
                      child: Text('Notify when nutrient stress > 30%',
                          style: TextStyle(color: C.textPrimary, fontSize: 14)),
                    ),
                  ],
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Cancel', style: TextStyle(color: C.textMuted))),
            ElevatedButton(
                onPressed: () => Navigator.pop(ctx, true),
                style: ElevatedButton.styleFrom(backgroundColor: C.green),
                child: const Text('Apply')),
          ],
        ),
      ),
    );

    if (confirmed != true || !mounted) return;

    double? parseOpt(TextEditingController c) {
      final t = c.text.trim();
      return t.isEmpty ? null : double.tryParse(t);
    }

    try {
      final res = await _api.setRegime(
        enabled: enabled,
        wateringHour: int.tryParse(cWaterHour.text.trim()) ?? 7,
        ventilationHour: int.tryParse(cVentHour.text.trim()) ?? 12,
        waterAmount: double.tryParse(cWaterAmt.text.trim()) ?? 0.3,
        fanSpeed: double.tryParse(cFanSpeed.text.trim()) ?? 20.0,
        co2Enrichment: co2On,
        co2Target: double.tryParse(cCo2Target.text.trim()) ?? 1000.0,
        targetTemp: parseOpt(cTargetTemp),
        targetPar: parseOpt(cTargetPar),
        notifyNutrientStress: notifyN,
      );

      if (!mounted) return;
      final success = res['success'] as bool? ?? false;
      if (success) {
        setState(() {
          _notifyNutrientStress = notifyN;
          simulationConfig = res['config'] as Map<String, dynamic>?;
        });
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Daily regime updated'),
          backgroundColor: C.green,
        ));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(res['error'] ?? 'Failed to update regime'),
          backgroundColor: C.danger,
        ));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Error: $e'),
        backgroundColor: C.danger,
      ));
    }
  }

  /// Compact text field reused in the regime dialog.
  Widget _regimeField(TextEditingController c, String label) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TextField(
          controller: c,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          style: const TextStyle(color: C.textPrimary),
          decoration: InputDecoration(
            labelText: label,
            labelStyle: const TextStyle(color: C.textMuted, fontSize: 13),
            isDense: true,
            enabledBorder:
                const OutlineInputBorder(borderSide: BorderSide(color: C.border)),
            focusedBorder:
                const OutlineInputBorder(borderSide: BorderSide(color: C.green)),
          ),
        ),
      );

  // ── Nutrient stress notification popup ───────────────────────────────────

  void _showNutrientNotification() {
    final RenderBox box =
        _notifBellKey.currentContext!.findRenderObject() as RenderBox;
    final Offset offset = box.localToGlobal(Offset.zero);
    final Size size = box.size;

    final nutrientStress = _d('nutrient_stress');
    final soilN = _d('soil_N');
    final soilP = _d('soil_P');
    final soilK = _d('soil_K');

    showMenu(
      context: context,
      color: C.panel,
      position: RelativeRect.fromLTRB(
        offset.dx,
        offset.dy + size.height + 4,
        offset.dx + size.width,
        0,
      ),
      items: [
        PopupMenuItem(
          enabled: false,
          child: SizedBox(
            width: 240,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Nutrient Status',
                    style: TextStyle(
                        color: C.textPrimary,
                        fontWeight: FontWeight.w700,
                        fontSize: 15)),
                const SizedBox(height: 8),
                _nutrientRow(
                    'Stress level',
                    '${(nutrientStress * 100).toStringAsFixed(0)}%',
                    nutrientStress > 0.3 ? C.danger : C.green),
                _nutrientRow('Nitrogen (N)', '${soilN.toStringAsFixed(0)} ppm', C.textPrimary),
                _nutrientRow('Phosphorus (P)', '${soilP.toStringAsFixed(0)} ppm', C.textPrimary),
                _nutrientRow('Potassium (K)', '${soilK.toStringAsFixed(0)} ppm', C.textPrimary),
                if (nutrientStress > 0.3) ...[
                  const SizedBox(height: 8),
                  const Text(
                    'Consider applying fertiliser (🧪 Feed)',
                    style: TextStyle(color: C.warn, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _nutrientRow(String label, String value, Color valueColor) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: C.textMuted, fontSize: 13)),
            Text(value,
                style: TextStyle(
                    color: valueColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
          ],
        ),
      );

  Future<void> _stepSimulation(int hours) async {
    setState(() => isLoading = true);
    try {
      final response = await _api.stepSimulation(hours);
      if (!mounted) return;
      if (response.success) {
        setState(() => simulationState = response.state);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('⏩ Stepped +${hours}h (Hour ${_i('hour')})'),
            backgroundColor: C.green,
            duration: const Duration(seconds: 1),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ ${response.error ?? "Step failed"}'),
            backgroundColor: C.danger,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: C.danger),
      );
    } finally {
      if (mounted) setState(() => isLoading = false);
    }
  }

  // ── display name helper ──────────────────────────────────────────────────────

  String get _selectedPlantDisplayName {
    if (selectedPlant == null) return 'Plant';
    final profile =
        availablePlants.where((p) => p.id == selectedPlant).firstOrNull;
    if (profile == null) return selectedPlant!;
    return profile.commonNames.isNotEmpty
        ? profile.commonNames.first
        : profile.name;
  }

  // ── build ────────────────────────────────────────────────────────────────────

  /// Reset to the settings view immediately, then stop the backend in background.
  Future<void> _resetToProfileView() async {
    // Show the settings page right away — no need to wait for the stop call.
    if (mounted) {
      setState(() {
        simulationState = null;
        simulationRunning = false;
        history = [];
        agentStats = null;
        error = null;
        isLoading = false;
      });
    }
    // Stop backend best-effort (fire-and-forget).
    try {
      await _api.stopSimulation();
    } catch (e) {
      debugPrint('Error stopping simulation during reset: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: C.bg,
      body: Stack(
        children: [
          const AnimatedCyberBackground(),
          Container(
            width: double.infinity,
            height: double.infinity,
            color: Colors.black.withValues(alpha: 0.42),
          ),
          Column(
            children: [
              _buildHeader(),
              Expanded(
                child: simulationState != null
                    ? _buildRunningView()
                    : _buildProfileView(),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    final alive = _b('is_alive');
    final damage = _d('cumulative_damage');
    final totalHour = _i('hour');
    final day = totalHour ~/ 24;
    final hourOfDay = totalHour % 24;
    final hasStatus = simulationRunning && simulationState != null;

    // ── Reusable chip widgets ────────────────────────────────────────────────
    final dayChip = Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Text(
        'Day $day · ${hourOfDay.toString().padLeft(2, '0')}:00',
        style: GoogleFonts.outfit(
            fontWeight: FontWeight.w600, fontSize: 13, color: C.textPrimary),
      ),
    );

    final aliveChip = Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: alive
            ? C.green.withValues(alpha: 0.15)
            : C.danger.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: alive
              ? C.green.withValues(alpha: 0.40)
              : C.danger.withValues(alpha: 0.40),
        ),
      ),
      child: Text(
        '${alive ? "ALIVE" : "DEAD"} · ${damage.toStringAsFixed(0)}%',
        style: GoogleFonts.outfit(
            fontWeight: FontWeight.w700,
            fontSize: 12,
            color: alive ? C.green : C.danger),
      ),
    );

    final bellIcon = Stack(
      clipBehavior: Clip.none,
      children: [
        IconButton(
          key: _notifBellKey,
          icon: Icon(
            Icons.notifications_outlined,
            color: (_notifyNutrientStress && _d('nutrient_stress') > 0.3)
                ? C.warn
                : C.textMuted,
            size: 22,
          ),
          tooltip: 'Nutrient status',
          onPressed: _showNutrientNotification,
        ),
        if (_notifyNutrientStress && _d('nutrient_stress') > 0.3)
          Positioned(
            top: 8,
            right: 8,
            child: Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                  color: C.danger, shape: BoxShape.circle),
            ),
          ),
      ],
    );

    final menuBtn = PopupMenuButton<String>(
      icon: const Icon(Icons.more_vert, color: C.textMuted, size: 20),
      color: C.panel,
      onSelected: (value) async {
        switch (value) {
          case 'metrics':
            Navigator.push(context,
                MaterialPageRoute(builder: (_) => const MetricsViewerScreen()));
            break;
          case 'diagnostics':
            Navigator.push(context,
                MaterialPageRoute(builder: (_) => const DiagnosticsScreen()));
            break;
          case 'executor':
            Navigator.push(context,
                MaterialPageRoute(builder: (_) => const ExecutorLogScreen()));
            break;
          case 'monitor':
            Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => const MonitorSettingsScreen()));
            break;
          case 'mqtt':
            Navigator.push(context,
                MaterialPageRoute(builder: (_) => const MqttSettingsScreen()));
            break;
          case 'signout':
            try {
              try {
                await _api.stopSimulation();
              } catch (_) {}
              await AuthService.instance.signOut();
              if (mounted) {
                Navigator.of(context).pushAndRemoveUntil(
                  MaterialPageRoute(builder: (_) => const AuthScreen()),
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
            break;
        }
      },
      itemBuilder: (context) => const [
        PopupMenuItem(
            value: 'metrics',
            child: Row(children: [
              Icon(Icons.show_chart, color: C.green, size: 18),
              SizedBox(width: 8),
              Text('Metrics')
            ])),
        PopupMenuItem(
            value: 'diagnostics',
            child: Row(children: [
              Icon(Icons.analytics, color: C.info, size: 18),
              SizedBox(width: 8),
              Text('Diagnostics')
            ])),
        PopupMenuItem(
            value: 'executor',
            child: Row(children: [
              Icon(Icons.history, color: C.textMuted, size: 18),
              SizedBox(width: 8),
              Text('Action Log')
            ])),
        PopupMenuItem(
            value: 'monitor',
            child: Row(children: [
              Icon(Icons.settings, color: C.textMuted, size: 18),
              SizedBox(width: 8),
              Text('Monitor Settings')
            ])),
        PopupMenuItem(
            value: 'mqtt',
            child: Row(children: [
              Icon(Icons.cell_tower, color: C.info, size: 18),
              SizedBox(width: 8),
              Text('MQTT Settings')
            ])),
        PopupMenuItem(
            value: 'signout',
            child: Row(children: [
              Icon(Icons.logout, color: C.danger, size: 18),
              SizedBox(width: 8),
              Text('Sign Out', style: TextStyle(color: C.danger))
            ])),
      ],
    );

    // ── Glass header container ───────────────────────────────────────────────
    return ClipRect(
      child: BackdropFilter(
        filter: ui.ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.55),
            border: Border(
                bottom: BorderSide(
                    color: Colors.white.withValues(alpha: 0.08))),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth >= 500;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Plant Lab Simulator',
                              style: GoogleFonts.outfit(
                                  color: C.green,
                                  fontSize: wide ? 20 : 16,
                                  fontWeight: FontWeight.w800),
                            ),
                            if (wide)
                              Text(
                                'Flask-Powered Growth Simulation',
                                style: GoogleFonts.outfit(
                                    color: C.textMuted,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w400),
                              ),
                          ],
                        ),
                      ),
                      if (wide && hasStatus) ...[
                        dayChip,
                        const SizedBox(width: 8),
                        aliveChip,
                        const SizedBox(width: 4),
                      ],
                      if (hasStatus) bellIcon,
                      menuBtn,
                    ],
                  ),
                  // On narrow screens, status chips move to their own row
                  if (!wide && hasStatus) ...[
                    const SizedBox(height: 8),
                    Row(children: [
                      dayChip,
                      const SizedBox(width: 8),
                      aliveChip,
                    ]),
                  ],
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildProfileView() {
    const tickOptions = [1, 2, 3, 6, 12, 24];
    const dayOptions = [7, 14, 30, 60, 90];

    return Center(
      child: SingleChildScrollView(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
              // ── Plant & simulation setup ─────────────────────────────────
              Panel(
                glass: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.grass, color: C.green, size: 24),
                        const SizedBox(width: 12),
                        Text(
                          'Start New Simulation',
                          style: GoogleFonts.outfit(
                              fontSize: 18, fontWeight: FontWeight.w700),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),

                    // Plant selector
                    const Text('Plant species',
                        style: TextStyle(color: C.textMuted, fontSize: 13)),
                    const SizedBox(height: 6),
                    _dropdownBox(
                      child: DropdownButton<String>(
                        isDense: true,
                        isExpanded: true,
                        underline: const SizedBox(),
                        value: selectedPlant,
                        items: availablePlants.map((plant) {
                          final name = plant.commonNames.isNotEmpty
                              ? plant.commonNames.first
                              : plant.id;
                          return DropdownMenuItem(
                              value: plant.id, child: Text(name));
                        }).toList(),
                        onChanged: (v) => setState(() => selectedPlant = v),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Hours per tick + simulation days (side by side)
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Hours / tick',
                                  style: TextStyle(
                                      color: C.textMuted, fontSize: 13)),
                              const SizedBox(height: 6),
                              _dropdownBox(
                                child: DropdownButton<int>(
                                  isDense: true,
                                  isExpanded: true,
                                  underline: const SizedBox(),
                                  value: _timeGapHours,
                                  items: tickOptions.map((h) {
                                    return DropdownMenuItem(
                                      value: h,
                                      child: Text(
                                        h == 1 ? '1 h (fine)' : '$h h',
                                      ),
                                    );
                                  }).toList(),
                                  onChanged: (v) =>
                                      setState(() => _timeGapHours = v ?? 1),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Duration',
                                  style: TextStyle(
                                      color: C.textMuted, fontSize: 13)),
                              const SizedBox(height: 6),
                              _dropdownBox(
                                child: DropdownButton<int>(
                                  isDense: true,
                                  isExpanded: true,
                                  underline: const SizedBox(),
                                  value: dayOptions.contains(_simulationDays)
                                      ? _simulationDays
                                      : 30,
                                  items: dayOptions.map((d) {
                                    return DropdownMenuItem(
                                        value: d, child: Text('$d days'));
                                  }).toList(),
                                  onChanged: (v) =>
                                      setState(() => _simulationDays = v ?? 30),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),

                    // Daily regime toggle
                    Row(
                      children: [
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Daily Regime',
                                  style: TextStyle(fontSize: 15)),
                              Text(
                                'Auto watering, HVAC, CO₂ enrichment',
                                style: TextStyle(
                                    color: C.textMuted, fontSize: 13),
                              ),
                            ],
                          ),
                        ),
                        Switch(
                          value: _dailyRegimeEnabled,
                          onChanged: (v) =>
                              setState(() => _dailyRegimeEnabled = v),
                          activeThumbColor: C.green,
                          inactiveThumbColor: C.textDim,
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),

                    // MQTT speed hint
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: C.info.withValues(alpha: 0.07),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                            color: C.info.withValues(alpha: 0.25)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.cell_tower,
                              color: C.info, size: 15),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'MQTT publisher will step $_timeGapHours sim-hour'
                              '${_timeGapHours > 1 ? 's' : ''} per publish cycle',
                              style: const TextStyle(
                                  color: C.info, fontSize: 12),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),

                    // Start button
                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: ElevatedButton(
                        onPressed: isLoading ? null : _startSimulation,
                        style: ElevatedButton.styleFrom(
                            backgroundColor: C.green,
                            foregroundColor: Colors.white),
                        child: isLoading
                            ? const SizedBox(
                                height: 20,
                                width: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation(
                                      Colors.white),
                                ),
                              )
                            : Text(
                                'Simulate  ($_simulationDays d · ${_timeGapHours}h/tick)',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                    fontSize: 16,
                                    color: Colors.white),
                              ),
                      ),
                    ),
                    if (error != null) ...[
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: C.danger.withValues(alpha: 0.1),
                          border: Border.all(color: C.danger),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(error!,
                            style: const TextStyle(
                                color: C.danger, fontSize: 14)),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  ),
    );
  }

  /// Styled container wrapping a DropdownButton
  Widget _dropdownBox({required Widget child}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: child,
    );
  }

  /// Label + control in a horizontal row
  Widget _settingsRow(String label, Widget control) {
    return Row(
      children: [
        Expanded(
          child: Text(label,
              style: const TextStyle(color: C.textMuted, fontSize: 12)),
        ),
        control,
      ],
    );
  }

  Widget _buildRunningView() {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth > 1100) {
          return _buildWideLayout();
        } else if (constraints.maxWidth > 700) {
          return _buildMediumLayout();
        } else {
          return _buildNarrowLayout();
        }
      },
    );
  }

  Widget _buildWideLayout() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 3,
          child: _scrollCol([
            _buildPlantPanel(),
            _buildCoreStatePanel(),
            _buildPhenologyPanel(),
          ]),
        ),
        Expanded(
          flex: 4,
          child: _scrollCol([
            _buildEnvironmentPanel(),
            _buildHistoryPanel(),
            _buildAgentStatsPanel(),
          ]),
        ),
        Expanded(
          flex: 3,
          child: _scrollCol([
            _buildStepPanel(),
            _buildActionsPanel(),
            _buildControlPanel(),
          ]),
        ),
      ],
    );
  }

  Widget _buildMediumLayout() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 3,
          child: _scrollCol([
            _buildPlantPanel(),
            _buildEnvironmentPanel(),
            _buildHistoryPanel(),
          ]),
        ),
        Expanded(
          flex: 2,
          child: _scrollCol([
            _buildCoreStatePanel(),
            _buildPhenologyPanel(),
            _buildAgentStatsPanel(),
            _buildStepPanel(),
            _buildActionsPanel(),
            _buildControlPanel(),
          ]),
        ),
      ],
    );
  }

  Widget _buildNarrowLayout() {
    return _scrollCol([
      _buildPlantPanel(),
      _buildCoreStatePanel(),
      _buildPhenologyPanel(),
      _buildEnvironmentPanel(),
      _buildHistoryPanel(),
      _buildAgentStatsPanel(),
      _buildStepPanel(),
      _buildActionsPanel(),
      _buildControlPanel(),
      const SizedBox(height: 60),
    ]);
  }

  Widget _scrollCol(List<Widget> children) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: children
            .map((w) =>
                Padding(padding: const EdgeInsets.only(bottom: 12), child: w))
            .toList(),
      ),
    );
  }

  // ── panels — all read directly from simulationState map ─────────────────────

  Widget _buildPlantPanel() {
    final stageLabel = _stage.label;
    final day = _i('hour') ~/ 24;
    return Panel(
      glass: true,
      child: Column(
        children: [
          const PanelTitle('Plant Visual'),
          Center(child: PlantVisual(state: simulationState ?? {})),
          const SizedBox(height: 6),
          Text(
            '$_selectedPlantDisplayName · $stageLabel · Day $day',
            style: const TextStyle(color: C.textMuted, fontSize: 17),
          ),
        ],
      ),
    );
  }

  Widget _buildCoreStatePanel() {
    final biomass = _d('biomass');
    final leafArea = _d('leaf_area');
    final thermalTime = _d('thermal_time');
    final damage = _d('cumulative_damage');
    final waterStress = _d('water_stress');
    final tempStress = _d('temp_stress');
    final nutrientStress = _d('nutrient_stress');

    return Panel(
      glass: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Core State'),
          MetricTile(
              label: 'Biomass', value: biomass.toStringAsFixed(1), unit: 'g'),
          const SizedBox(height: 6),
          MetricTile(
              label: 'Leaf Area',
              value: leafArea.toStringAsFixed(3),
              unit: 'm²'),
          const SizedBox(height: 6),
          MetricTile(
              label: 'Thermal Time',
              value: thermalTime.toStringAsFixed(0),
              unit: '°C·h'),
          const SizedBox(height: 6),
          MetricTile(
            label: 'Damage',
            value: damage.toStringAsFixed(1),
            unit: '%',
            warn: damage > 20,
          ),
          const SizedBox(height: 8),
          BarGauge(value: damage),
          const SizedBox(height: 3),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('0%',
                  style: TextStyle(fontSize: 13, color: C.textMuted)),
              Text(
                '${damage.toStringAsFixed(0)}%',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: damage < 30
                      ? C.green
                      : damage < 60
                          ? C.warn
                          : C.danger,
                ),
              ),
              const Text('95% ☠',
                  style: TextStyle(fontSize: 13, color: C.textMuted)),
            ],
          ),
          const SizedBox(height: 10),
          _stressRow('Water', waterStress),
          _stressRow('Temperature', tempStress),
          _stressRow('Nutrient', nutrientStress),
        ],
      ),
    );
  }

  /// Returns green/amber/red based on stress level — informative, not type-coded.
  Color _stressColor(double stress) {
    if (stress < 0.25) return C.green;
    if (stress < 0.55) return C.warn;
    return C.danger;
  }

  Widget _stressRow(String label, double value) {
    final color = _stressColor(value);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          SizedBox(
            width: 100,
            child: Text(label,
                style: const TextStyle(fontSize: 13, color: C.textMuted)),
          ),
          Expanded(child: BarGauge(value: value * 100, color: color, height: 6)),
          const SizedBox(width: 8),
          SizedBox(
            width: 40,
            child: Text(
              '${(value * 100).toStringAsFixed(0)}%',
              textAlign: TextAlign.right,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: color),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPhenologyPanel() {
    final stage = _stage;
    return Panel(
      glass: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Growth Stage'),
          PhenologyBar(stage: stage.label),
          const SizedBox(height: 4),
          Text(
            stage.label,
            style: const TextStyle(fontSize: 16, color: C.textMuted),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildEnvironmentPanel() {
    // NOTE: backend sends VPD as uppercase key "VPD"
    final soilWater = _d('soil_water');
    final airTemp = _d('air_temp');
    final soilTemp = _d('soil_temp');
    final rh = _d('relative_humidity');
    final par = _d('light_PAR');
    final vpd = (simulationState?['VPD'] ?? 0.0).toDouble();
    final soilN = _d('soil_N');
    final soilEC = _d('soil_EC');

    // 3-level semantic alerts: danger → warn → null (ok)
    Color? soilWaterAlert = soilWater < 10
        ? C.danger
        : soilWater < 20
            ? C.warn
            : null;
    Color? airTempAlert = (airTemp > 36 || airTemp < 8)
        ? C.danger
        : (airTemp > 32 || airTemp < 12)
            ? C.warn
            : null;
    Color? rhAlert = (rh < 30 || rh > 90)
        ? C.danger
        : (rh < 40 || rh > 80)
            ? C.warn
            : null;
    Color? parAlert = par < 50
        ? C.warn
        : par > 1800
            ? C.warn
            : null;
    Color? vpdAlert = vpd > 2.5
        ? C.danger
        : vpd > 1.8
            ? C.warn
            : null;
    Color? soilTempAlert =
        (soilTemp > 32 || soilTemp < 8) ? C.warn : null;
    Color? soilNAlert = soilN < 30
        ? C.danger
        : soilN < 70
            ? C.warn
            : null;
    Color? soilECAlert = soilEC > 4.0
        ? C.danger
        : soilEC > 3.0
            ? C.warn
            : null;

    return Panel(
      glass: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Environment'),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 6,
            crossAxisSpacing: 6,
            childAspectRatio: 2.2,
            children: [
              _envTile('Soil Moisture', '${soilWater.toStringAsFixed(1)}%', soilWaterAlert),
              _envTile('Air Temp', '${airTemp.toStringAsFixed(1)}°C', airTempAlert),
              _envTile('Humidity', '${rh.toStringAsFixed(0)}%', rhAlert),
              _envTile('PAR', '${par.toStringAsFixed(0)} µ', parAlert),
              _envTile('VPD', '${vpd.toStringAsFixed(2)} kPa', vpdAlert),
              _envTile('Soil Temp', '${soilTemp.toStringAsFixed(1)}°C', soilTempAlert),
              _envTile('Soil N', '${soilN.toStringAsFixed(0)} ppm', soilNAlert),
              _envTile('Soil EC', '${soilEC.toStringAsFixed(2)} mS', soilECAlert),
            ],
          ),
        ],
      ),
    );
  }

  Widget _envTile(String label, String value, Color? alert) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: alert != null
            ? alert.withValues(alpha: 0.08)
            : Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: alert != null
              ? alert.withValues(alpha: 0.30)
              : Colors.white.withValues(alpha: 0.07),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Text(label,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.outfit(
                        color: C.textMuted,
                        fontSize: 11,
                        fontWeight: FontWeight.w400)),
              ),
              if (alert != null)
                Container(
                  width: 6,
                  height: 6,
                  decoration:
                      BoxDecoration(color: alert, shape: BoxShape.circle),
                ),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: GoogleFonts.outfit(
              fontWeight: FontWeight.w700,
              fontSize: 17,
              color: alert ?? C.textPrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHistoryPanel() {
    if (history.isEmpty) {
      return Panel(
        glass: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            PanelTitle('History'),
            Text('No history data yet',
                style: TextStyle(color: C.textMuted, fontSize: 14)),
          ],
        ),
      );
    }

    final n = min(100, history.length);
    final slice = history.sublist(max(0, history.length - n));

    return Panel(
      glass: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          PanelTitle('History (${history.length} hours)'),
          _chartRow(
              'Biomass',
              slice
                  .map<double>((h) => (h['biomass'] ?? 0.0).toDouble())
                  .toList(),
              0,
              300,
              C.green),
          const SizedBox(height: 8),
          _chartRow(
              'Damage',
              slice
                  .map<double>(
                      (h) => (h['cumulative_damage'] ?? 0.0).toDouble())
                  .toList(),
              0,
              100,
              C.danger),
          const SizedBox(height: 8),
          _chartRow(
              'Soil Moisture',
              slice
                  .map<double>((h) => (h['soil_water'] ?? 0.0).toDouble())
                  .toList(),
              0,
              50,
              C.water),
          const SizedBox(height: 8),
          _chartRow(
              'Air Temp',
              slice
                  .map<double>((h) => (h['air_temp'] ?? 0.0).toDouble())
                  .toList(),
              5,
              45,
              C.warn),
        ],
      ),
    );
  }

  Widget _chartRow(
      String label, List<double> data, double minY, double maxY, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(fontSize: 15, color: C.textMuted)),
            if (data.isNotEmpty)
              Text(
                data.last.toStringAsFixed(1),
                style: TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w700, color: color),
              ),
          ],
        ),
        const SizedBox(height: 2),
        Sparkline(data: data, minY: minY, maxY: maxY, color: color, height: 40),
      ],
    );
  }

  Widget _buildAgentStatsPanel() {
    final reasoning = agentStats != null
        ? (agentStats!['reasoning'] as Map<String, dynamic>? ?? {})
        : <String, dynamic>{};

    final rows = <MapEntry<String, String>>[];
    if (agentStats != null) {
      rows.add(MapEntry('Monitor',
          agentStats!['monitor_enabled'] == true ? 'Enabled' : 'Disabled'));
      rows.add(MapEntry('Total Alerts', '${reasoning['total_alerts'] ?? 0}'));
      rows.add(MapEntry('Warnings', '${reasoning['warnings'] ?? 0}'));
      rows.add(MapEntry('Criticals', '${reasoning['criticals'] ?? 0}'));
      rows.add(MapEntry(
          'Executor Actions', '${agentStats!['executor_actions'] ?? 0}'));
    }

    return Panel(
      glass: true,
      accentLeft: C.info,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Agent Statistics'),
          if (agentStats == null)
            const Text('No agent data',
                style: TextStyle(color: C.textMuted, fontSize: 16))
          else
            ...rows.map((e) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(e.key,
                          style: const TextStyle(
                              fontSize: 16, color: C.textMuted)),
                      Text(e.value,
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w600)),
                    ],
                  ),
                )),
        ],
      ),
    );
  }

  Widget _buildActionsPanel() {
    return Panel(
      glass: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: PanelTitle('Manual Actions')),
              TextButton.icon(
                onPressed: simulationRunning ? _showRegimeDialog : null,
                icon: const Icon(Icons.tune, size: 16),
                label: const Text('Daily Regime'),
                style: TextButton.styleFrom(foregroundColor: C.green),
              ),
            ],
          ),
          const Text(
            'Execute actions directly on the backend:',
            style: TextStyle(color: C.textMuted, fontSize: 15),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              AnimButton(
                label: '💧 Water',
                color: C.water.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _promptAndExecute(ActionType.water),
              ),
              AnimButton(
                label: '💡 Light',
                color: C.light.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _promptAndExecute(ActionType.light),
              ),
              AnimButton(
                label: '🧪 Feed',
                color: C.nutrient.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _promptAndExecute(ActionType.nutrient),
              ),
              AnimButton(
                label: '🌡️ HVAC',
                color: C.hvac.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _promptAndExecute(ActionType.hvac),
              ),
              AnimButton(
                label: '💨 Humidity',
                color: C.humidity.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _promptAndExecute(ActionType.humidity),
              ),
              AnimButton(
                label: '🌬️ Vent',
                color: C.vent.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _promptAndExecute(ActionType.ventilation),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStepPanel() {
    // Only use step sizes allowed by the backend [1,2,3,6,12,24]
    const presets = [(1, '1h'), (2, '2h'), (3, '3h'), (6, '6h'), (12, '12h'), (24, '1d')];
    return Panel(
      glass: true,
      accentLeft: C.info,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Manual Step'),
          const Text(
            'Advance simulation by:',
            style: TextStyle(color: C.textMuted, fontSize: 15),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: presets.map((s) {
              final hours = s.$1;
              final label = s.$2;
              final isDefault = hours == _timeGapHours;
              return AnimButton(
                label: isDefault ? '$label *' : label,
                color: isDefault
                    ? C.green.withValues(alpha: 0.4)
                    : C.info.withValues(alpha: 0.25),
                compact: true,
                onTap: isLoading ? () {} : () => _stepSimulation(hours),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildControlPanel() {
    final isAlive = _b('is_alive');
    final deathReason = simulationState?['death_reason'] as String?;
    // Simulation ended when we have state AND it is no longer actively running
    final ended = simulationState != null && !simulationRunning;

    return Panel(
      glass: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Simulation Control'),

          // ── Dead-plant banner (only when plant is dead) ────────────────
          if (ended && !isAlive) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: C.danger.withValues(alpha: 0.08),
                border: Border.all(color: C.danger.withValues(alpha: 0.4)),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const Text(
                    '💀 Plant has died',
                    style: TextStyle(
                        color: C.danger,
                        fontWeight: FontWeight.w700,
                        fontSize: 15),
                  ),
                  if (deathReason != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      deathReason,
                      style:
                          const TextStyle(color: C.textMuted, fontSize: 13),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],

          // ── Completed-normally banner ──────────────────────────────────
          if (ended && isAlive) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: C.green.withValues(alpha: 0.08),
                border: Border.all(color: C.green.withValues(alpha: 0.4)),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Text(
                '✅ Simulation complete',
                style: TextStyle(
                    color: C.green,
                    fontWeight: FontWeight.w600,
                    fontSize: 14),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 12),
          ],

          // ── Primary action button ──────────────────────────────────────
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ended
                // Simulation over: let user start fresh without navigating away
                ? ElevatedButton.icon(
                    onPressed: isLoading ? null : () async => await _resetToProfileView(),
                    icon: const Icon(Icons.refresh),
                    label: const Text(
                      'Start New Simulation',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
                    ),
                    style: ElevatedButton.styleFrom(
                        backgroundColor: C.green,
                        foregroundColor: Colors.white),
                  )
                // Simulation running: allow manual stop
                : ElevatedButton.icon(
                    onPressed: isLoading ? null : _stopSimulation,
                    icon: const Icon(Icons.stop),
                    label: const Text('Stop Simulation'),
                    style:
                        ElevatedButton.styleFrom(backgroundColor: C.danger),
                  ),
          ),
        ],
      ),
    );
  }
}
