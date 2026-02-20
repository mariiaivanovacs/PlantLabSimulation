import 'dart:math';
import 'package:flutter/material.dart';
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
import '../services/auth_service.dart';

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

        setState(() {
          simulationRunning = stateResp.running;
          simulationState = stateResp.state;
          simulationSummary = stateResp.summary;
          simulationConfig = stateResp.config;
          error = null;
        });

        if (simulationRunning) {
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
          simulationRunning = false;
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
        days: _simulationDays,
        mode: _simulationMode,
        hoursPerTick: _timeGapHours,
        tickDelay: 0.1,
        dailyRegime: _dailyRegimeEnabled,
        monitorEnabled: true,
      );
      if (!mounted) return;
      if (response.success) {
        setState(() => simulationRunning = true);
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: simulationRunning && simulationState != null
                ? _buildRunningView()
                : _buildProfileView(),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    final alive = _b('is_alive');
    final damage = _d('cumulative_damage');
    final hour = _i('hour');
    final day = hour ~/ 24;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [C.bg, Color(0xFF122018)]),
        border: Border(bottom: BorderSide(color: C.border, width: 2)),
      ),
      child: Row(
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Plant Lab Simulator',
                  style: TextStyle(
                      color: C.green,
                      fontSize: 18,
                      fontWeight: FontWeight.w800),
                ),
                Text(
                  'Flask-Powered Growth Simulation',
                  style: TextStyle(color: C.textMuted, fontSize: 11),
                ),
              ],
            ),
          ),
          if (simulationRunning && simulationState != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: C.panelAlt,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                'Day $day · H$hour',
                style:
                    const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
              ),
            ),
            const SizedBox(width: 10),
            // Health chip — reads directly from simulationState
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: alive
                    ? C.greenSoft.withValues(alpha: 0.85)
                    : C.danger.withValues(alpha: 0.8),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(
                '${alive ? "🌿" : "💀"} ${alive ? "ALIVE" : "DEAD"} · ${damage.toStringAsFixed(0)}%',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                  color: alive ? C.greenDark : Colors.white,
                ),
              ),
            ),
            const SizedBox(width: 8),
          ],
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert, color: C.textMuted, size: 20),
            color: C.panel,
            onSelected: (value) {
              switch (value) {
                case 'metrics':
                  Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const MetricsViewerScreen()));
                  break;
                case 'diagnostics':
                  Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const DiagnosticsScreen()));
                  break;
                case 'executor':
                  Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const ExecutorLogScreen()));
                  break;
                case 'monitor':
                  Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const MonitorSettingsScreen()));
                  break;
                case 'signout':
                  AuthService.instance.signOut();
                  break;
              }
            },
            itemBuilder: (context) => const [
              PopupMenuItem(
                value: 'metrics',
                child: Row(children: [
                  Icon(Icons.show_chart, color: C.green, size: 18),
                  SizedBox(width: 8),
                  Text('Metrics'),
                ]),
              ),
              PopupMenuItem(
                value: 'diagnostics',
                child: Row(children: [
                  Icon(Icons.analytics, color: C.info, size: 18),
                  SizedBox(width: 8),
                  Text('Diagnostics'),
                ]),
              ),
              PopupMenuItem(
                value: 'executor',
                child: Row(children: [
                  Icon(Icons.history, color: C.textMuted, size: 18),
                  SizedBox(width: 8),
                  Text('Action Log'),
                ]),
              ),
              PopupMenuItem(
                value: 'monitor',
                child: Row(children: [
                  Icon(Icons.settings, color: C.textMuted, size: 18),
                  SizedBox(width: 8),
                  Text('Monitor Settings'),
                ]),
              ),
              PopupMenuItem(
                value: 'signout',
                child: Row(children: [
                  Icon(Icons.logout, color: C.danger, size: 18),
                  SizedBox(width: 8),
                  Text('Sign Out',
                      style: TextStyle(color: C.danger)),
                ]),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildProfileView() {
    final displayName =
        _userProfile?['display_name'] as String? ?? '';
    final totalSims =
        (_userProfile?['total_simulations_run'] as num?)?.toInt() ?? 0;
    final lastSimRaw = _userProfile?['last_simulation_date'] as String?;

    String lastSimStr = 'Never';
    if (lastSimRaw != null) {
      try {
        final dt = DateTime.parse(lastSimRaw).toLocal();
        lastSimStr =
            '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year}';
      } catch (_) {}
    }

    return Center(
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Panel(
              accentLeft: C.green,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Welcome header ─────────────────────────────────────
                  Row(
                    children: [
                      const Icon(Icons.eco, color: C.green, size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              displayName.isNotEmpty
                                  ? 'Welcome, $displayName'
                                  : 'Plant Lab Simulator',
                              style: const TextStyle(
                                  fontSize: 15, fontWeight: FontWeight.w700),
                            ),
                            if (_profileLoading)
                              const Text('Loading profile…',
                                  style: TextStyle(
                                      color: C.textMuted, fontSize: 11)),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Divider(color: C.border, height: 1),
                  const SizedBox(height: 16),

                  // ── Plant ──────────────────────────────────────────────
                  const Text('Plant',
                      style: TextStyle(color: C.textMuted, fontSize: 12)),
                  const SizedBox(height: 6),
                  _dropdownBox(
                    child: DropdownButton<String>(
                      isDense: true,
                      isExpanded: true,
                      underline: const SizedBox(),
                      value: selectedPlant,
                      items: availablePlants.map((plant) {
                        final label = plant.commonNames.isNotEmpty
                            ? plant.commonNames.first
                            : plant.id;
                        return DropdownMenuItem(
                            value: plant.id, child: Text(label));
                      }).toList(),
                      onChanged: (v) => setState(() => selectedPlant = v),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ── Settings rows ──────────────────────────────────────
                  _settingsRow(
                    'Step size',
                    _dropdownBox(
                      child: DropdownButton<int>(
                        isDense: true,
                        underline: const SizedBox(),
                        value: _timeGapHours,
                        items: const [1, 2, 3, 6, 12, 24]
                            .map((h) => DropdownMenuItem(
                                value: h, child: Text('${h}h')))
                            .toList(),
                        onChanged: (v) =>
                            setState(() => _timeGapHours = v ?? 1),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  _settingsRow(
                    'Pot size',
                    _dropdownBox(
                      child: DropdownButton<double>(
                        isDense: true,
                        underline: const SizedBox(),
                        value: _potSizeL,
                        items: const [2.0, 5.0, 10.0, 20.0]
                            .map((l) => DropdownMenuItem(
                                value: l, child: Text('${l.toInt()} L')))
                            .toList(),
                        onChanged: (v) =>
                            setState(() => _potSizeL = v ?? 5.0),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  _settingsRow(
                    'Daily regime',
                    Switch(
                      value: _dailyRegimeEnabled,
                      onChanged: (v) =>
                          setState(() => _dailyRegimeEnabled = v),
                      activeColor: C.green,
                    ),
                  ),
                  const SizedBox(height: 10),
                  _settingsRow(
                    'Duration (days)',
                    _dropdownBox(
                      child: DropdownButton<int>(
                        isDense: true,
                        underline: const SizedBox(),
                        value: _simulationDays,
                        items: const [7, 14, 30, 60, 90, 180]
                            .map((d) => DropdownMenuItem(
                                value: d, child: Text('$d')))
                            .toList(),
                        onChanged: (v) =>
                            setState(() => _simulationDays = v ?? 30),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  _settingsRow(
                    'Mode',
                    SegmentedButton<String>(
                      segments: const [
                        ButtonSegment(value: 'speed', label: Text('Speed')),
                        ButtonSegment(
                            value: 'realtime', label: Text('Realtime')),
                      ],
                      selected: {_simulationMode},
                      onSelectionChanged: (v) =>
                          setState(() => _simulationMode = v.first),
                      style: const ButtonStyle(
                        textStyle:
                            WidgetStatePropertyAll(TextStyle(fontSize: 12)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // ── Buttons ────────────────────────────────────────────
                  Row(
                    children: [
                      Expanded(
                        child: SizedBox(
                          height: 44,
                          child: OutlinedButton(
                            onPressed: (_profileSaving || _userProfile == null)
                                ? null
                                : _saveUserProfile,
                            style: OutlinedButton.styleFrom(
                              side: const BorderSide(color: C.border),
                              foregroundColor: C.textPrimary,
                            ),
                            child: _profileSaving
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2, color: C.green))
                                : const Text('Save Settings',
                                    style: TextStyle(fontSize: 13)),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        flex: 2,
                        child: SizedBox(
                          height: 44,
                          child: ElevatedButton(
                            onPressed: isLoading ? null : _startSimulation,
                            style: ElevatedButton.styleFrom(
                                backgroundColor: C.green),
                            child: isLoading
                                ? const SizedBox(
                                    height: 18,
                                    width: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor:
                                          AlwaysStoppedAnimation(C.bg),
                                    ),
                                  )
                                : const Text('Start Simulation',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w600,
                                        fontSize: 14)),
                          ),
                        ),
                      ),
                    ],
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
                          style:
                              const TextStyle(color: C.danger, fontSize: 12)),
                    ),
                  ],

                  // ── Stats footer ───────────────────────────────────────
                  if (_userProfile != null) ...[
                    const SizedBox(height: 16),
                    const Divider(color: C.border, height: 1),
                    const SizedBox(height: 10),
                    Text(
                      '$totalSims simulation${totalSims == 1 ? '' : 's'} run'
                      ' · Last: $lastSimStr',
                      style:
                          const TextStyle(color: C.textMuted, fontSize: 11),
                    ),
                  ],
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
        color: C.panelAlt,
        border: Border.all(color: C.border),
        borderRadius: BorderRadius.circular(6),
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
        SizedBox(
          width: 300,
          child: _scrollCol([
            _buildPlantPanel(),
            _buildCoreStatePanel(),
            _buildPhenologyPanel(),
          ]),
        ),
        Expanded(
          child: _scrollCol([
            _buildEnvironmentPanel(),
            _buildHistoryPanel(),
            _buildAgentStatsPanel(),
          ]),
        ),
        SizedBox(
          width: 340,
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
      child: Column(
        children: [
          const PanelTitle('Plant Visual'),
          Center(child: PlantVisual(state: simulationState ?? {})),
          const SizedBox(height: 6),
          Text(
            '$_selectedPlantDisplayName · $stageLabel · Day $day',
            style: const TextStyle(color: C.textMuted, fontSize: 12),
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
                  style: TextStyle(fontSize: 9, color: C.textMuted)),
              Text(
                '${damage.toStringAsFixed(0)}%',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: damage < 30
                      ? C.green
                      : damage < 60
                          ? C.warn
                          : C.danger,
                ),
              ),
              const Text('95% ☠',
                  style: TextStyle(fontSize: 9, color: C.textMuted)),
            ],
          ),
          const SizedBox(height: 10),
          _stressRow('Water', waterStress, C.water),
          _stressRow('Temperature', tempStress, C.hvac),
          _stressRow('Nutrient', nutrientStress, C.nutrient),
        ],
      ),
    );
  }

  Widget _stressRow(String label, double value, Color color) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(label,
                style: const TextStyle(fontSize: 11, color: C.textMuted)),
          ),
          Expanded(
              child: BarGauge(value: value * 100, color: color, height: 4)),
          const SizedBox(width: 6),
          SizedBox(
            width: 30,
            child: Text(
              '${(value * 100).toStringAsFixed(0)}%',
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 10, color: C.textMuted),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPhenologyPanel() {
    final stage = _stage;
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Growth Stage'),
          PhenologyBar(stage: stage.label),
          const SizedBox(height: 4),
          Text(
            stage.label,
            style: const TextStyle(fontSize: 11, color: C.textMuted),
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

    return Panel(
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
            childAspectRatio: 2.6,
            children: [
              _envTile('Soil Moisture', '${soilWater.toStringAsFixed(1)}%',
                  soilWater < 15 ? C.danger : null),
              _envTile('Air Temp', '${airTemp.toStringAsFixed(1)}°C',
                  (airTemp > 33 || airTemp < 12) ? C.danger : null),
              _envTile('Humidity', '${rh.toStringAsFixed(0)}%', null),
              _envTile('PAR', par.toStringAsFixed(0), null),
              _envTile('VPD', '${vpd.toStringAsFixed(2)} kPa', null),
              _envTile('Soil Temp', '${soilTemp.toStringAsFixed(1)}°C', null),
              _envTile('Soil N', '${soilN.toStringAsFixed(0)} ppm',
                  soilN < 60 ? C.warn : null),
              _envTile('Soil EC', '${soilEC.toStringAsFixed(2)} mS/cm',
                  soilEC > 3.5 ? C.danger : null),
            ],
          ),
        ],
      ),
    );
  }

  Widget _envTile(String label, String value, Color? alert) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: C.bg,
        borderRadius: BorderRadius.circular(6),
        border: alert != null
            ? Border.all(color: alert.withValues(alpha: 0.4))
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(label, style: const TextStyle(color: C.textMuted, fontSize: 10)),
          Text(
            value,
            style: TextStyle(
              fontWeight: FontWeight.w700,
              fontSize: 13,
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
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            PanelTitle('History'),
            Text('No history data yet',
                style: TextStyle(color: C.textMuted, fontSize: 12)),
          ],
        ),
      );
    }

    final n = min(100, history.length);
    final slice = history.sublist(max(0, history.length - n));

    return Panel(
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
                style: const TextStyle(fontSize: 10, color: C.textMuted)),
            if (data.isNotEmpty)
              Text(
                data.last.toStringAsFixed(1),
                style: TextStyle(
                    fontSize: 10, fontWeight: FontWeight.w700, color: color),
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
      accentLeft: C.info,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Agent Statistics'),
          if (agentStats == null)
            const Text('No agent data',
                style: TextStyle(color: C.textMuted, fontSize: 12))
          else
            ...rows.map((e) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(e.key,
                          style: const TextStyle(
                              fontSize: 12, color: C.textMuted)),
                      Text(e.value,
                          style: const TextStyle(
                              fontSize: 12, fontWeight: FontWeight.w600)),
                    ],
                  ),
                )),
        ],
      ),
    );
  }

  Widget _buildActionsPanel() {
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Manual Actions'),
          const Text(
            'Execute actions directly on the backend:',
            style: TextStyle(color: C.textMuted, fontSize: 11),
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
                onTap: () =>
                    _executeAction(ActionType.water, {'volume_L': 0.2}),
              ),
              AnimButton(
                label: '💡 Light',
                color: C.light.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _executeAction(
                    ActionType.light, {'target_PAR': 600, 'power_W': 100}),
              ),
              AnimButton(
                label: '🧪 Feed',
                color: C.nutrient.withValues(alpha: 0.3),
                compact: true,
                onTap: () => _executeAction(ActionType.nutrient,
                    {'N_dose_ppm': 50, 'P_dose_ppm': 15, 'K_dose_ppm': 40}),
              ),
              AnimButton(
                label: '🌡️ Cool',
                color: C.hvac.withValues(alpha: 0.3),
                compact: true,
                onTap: () =>
                    _executeAction(ActionType.hvac, {'target_temp_C': 25}),
              ),
              AnimButton(
                label: '💨 Humidity',
                color: C.humidity.withValues(alpha: 0.3),
                compact: true,
                onTap: () =>
                    _executeAction(ActionType.humidity, {'target_RH': 65}),
              ),
              AnimButton(
                label: '🌬️ Vent',
                color: C.vent.withValues(alpha: 0.3),
                compact: true,
                onTap: () =>
                    _executeAction(ActionType.ventilation, {'fan_speed': 50.0}),
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
      accentLeft: C.info,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Manual Step'),
          const Text(
            'Advance simulation by:',
            style: TextStyle(color: C.textMuted, fontSize: 11),
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
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Simulation Control'),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              onPressed: isLoading ? null : _stopSimulation,
              icon: const Icon(Icons.stop),
              label: const Text('Stop Simulation'),
              style: ElevatedButton.styleFrom(backgroundColor: C.danger),
            ),
          ),
        ],
      ),
    );
  }
}
