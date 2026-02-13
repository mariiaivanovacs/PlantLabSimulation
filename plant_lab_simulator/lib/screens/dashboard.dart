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

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiClient _api = ApiClient();

  // UI state
  bool isLoading = false;
  bool simulationRunning = false;
  Map<String, dynamic>? simulationState;
  Map<String, dynamic>? simulationSummary;
  Map<String, dynamic>? simulationConfig;
  List<Map<String, dynamic>> history = [];
  Map<String, dynamic>? agentStats;
  List<PlantProfile> availablePlants = [];
  String? selectedPlant;
  String? error;

  // Polling timer
  bool _mounted = true;

  @override
  void initState() {
    super.initState();
    _loadAvailablePlants();
    _startPolling();
  }

  @override
  void dispose() {
    _mounted = false;
    super.dispose();
  }

  void _startPolling() {
    _periodicUpdate();
  }

  Future<void> _periodicUpdate() async {
    while (_mounted) {
      try {
        // Poll simulation state
        final stateResp = await _api.getSimulationState();
        if (!_mounted) return;

        setState(() {
          simulationRunning = stateResp.running;
          simulationState = stateResp.state;
          simulationSummary = stateResp.summary;
          simulationConfig = stateResp.config;
          error = null;
        });

        // If running, also fetch history and agent stats
        if (simulationRunning) {
          final histResp = await _api.getSimulationHistory(limit: 100);
          final agentResp = await _api.getAgentStatus();

          if (!_mounted) return;
          setState(() {
            history = histResp.history;
            agentStats = agentResp.statistics;
          });
        }
      } catch (e) {
        if (!_mounted) return;
        setState(() {
          error = e.toString();
          simulationRunning = false;
        });
      }

      await Future.delayed(const Duration(seconds: 2));
    }
  }

  Future<void> _loadAvailablePlants() async {
    try {
      final response = await _api.getAvailablePlants();
      if (!_mounted) return;
      setState(() {
        availablePlants = response.plants;
        if (availablePlants.isNotEmpty && selectedPlant == null) {
          selectedPlant = availablePlants.first.id;
        }
      });
    } catch (e) {
      if (!_mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to load plants: $e'),
          backgroundColor: C.danger,
        ),
      );
    }
  }

  Future<void> _startSimulation() async {
    if (selectedPlant == null) return;

    setState(() => isLoading = true);
    try {
      final response = await _api.startSimulation(
        plantName: selectedPlant!,
        days: 30,
        mode: 'speed',
        hoursPerTick: 1,
        tickDelay: 0.1,
        dailyRegime: true,
        monitorEnabled: true,
      );

      if (!_mounted) return;
      if (response.success) {
        setState(() => simulationRunning = true);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✅ ${response.message}'),
            backgroundColor: C.green,
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: ${response.error}'),
            backgroundColor: C.danger,
          ),
        );
      }
    } catch (e) {
      if (!_mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed: $e'),
          backgroundColor: C.danger,
        ),
      );
    } finally {
      if (_mounted) setState(() => isLoading = false);
    }
  }

  Future<void> _stopSimulation() async {
    setState(() => isLoading = true);
    try {
      final response = await _api.stopSimulation();
      if (!_mounted) return;
      if (response.success) {
        setState(() {
          simulationRunning = false;
          history = [];
          agentStats = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('⏹️ ${response.message}'),
            backgroundColor: C.green,
          ),
        );
      }
    } catch (e) {
      if (!_mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error stopping: $e'),
          backgroundColor: C.danger,
        ),
      );
    } finally {
      if (_mounted) setState(() => isLoading = false);
    }
  }

  Future<void> _executeAction(ActionType type, Map<String, dynamic> params) async {
    try {
      final response = await _api.executeAction(type.backendName, params);
      if (!_mounted) return;

      if (response.success) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✅ ${response.message}'),
            backgroundColor: C.green,
          ),
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
      if (!_mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error: $e'),
          backgroundColor: C.danger,
        ),
      );
    }
  }

  PlantState _buildPlantState() {
    if (simulationState == null) {
      return const PlantState();
    }

    final state = simulationState!;
    final summary = simulationSummary ?? {};

    return PlantState(
      day: state['day'] ?? 0,
      hour: state['hour'] ?? 0,
      biomass: (state['biomass'] ?? 0.0).toDouble(),
      leafArea: (state['leaf_area'] ?? 0.0).toDouble(),
      thermalTime: (state['thermal_time'] ?? 0.0).toDouble(),
      cumulativeDamage: (state['cumulative_damage'] ?? 0.0).toDouble(),
      isAlive: state['is_alive'] ?? false,
      soilWater: (state['soil_water'] ?? 35.0).toDouble(),
      airTemp: (state['air_temp'] ?? 25.0).toDouble(),
      soilTemp: (state['soil_temp'] ?? 22.0).toDouble(),
      relativeHumidity: (state['relative_humidity'] ?? 60.0).toDouble(),
      lightPAR: (state['light_PAR'] ?? 0.0).toDouble(),
      vpd: (state['vpd'] ?? 1.0).toDouble(),
      soilN: (state['soil_N'] ?? 150.0).toDouble(),
      soilEC: (state['soil_EC'] ?? 1.5).toDouble(),
      waterStress: (state['water_stress'] ?? 0.0).toDouble(),
      tempStress: (state['temp_stress'] ?? 0.0).toDouble(),
      nutrientStress: (state['nutrient_stress'] ?? 0.0).toDouble(),
      stage: _stageFromString(summary['phenological_stage']),
    );
  }

  int _stageFromString(String? stageStr) {
    if (stageStr == null) return 0;
    // Backend PhenologicalStage enum values: SEED, SEEDLING, VEGETATIVE, FLOWERING, FRUITING, MATURE, DEAD
    switch (stageStr.toUpperCase()) {
      case 'SEED':
        return 0;
      case 'SEEDLING':
        return 1;
      case 'VEGETATIVE':
        return 2;
      case 'FLOWERING':
        return 3;
      case 'FRUITING':
        return 4;
      case 'MATURE':
        return 5;
      case 'DEAD':
        return 6;
      default:
        return 0;
    }
  }

  String _growthStageStringFromState(PlantState state) {
    if (!state.isAlive) return 'dead';
    // Map integer stage index to PhenologyBar stage strings
    const stages = ['seed', 'seedling', 'vegetative', 'flowering', 'fruiting', 'mature', 'dead'];
    return stages[state.stage.clamp(0, stages.length - 1)];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: simulationRunning && simulationState != null
                ? _buildRunningView()
                : _buildStartView(),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader() {
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
                    fontWeight: FontWeight.w800,
                  ),
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
                'Day ${simulationState!['day']} · H${simulationState!['hour']}',
                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
              ),
            ),
            const SizedBox(width: 10),
            _buildHealthChip(),
            const SizedBox(width: 8),
          ],
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert, color: C.textMuted, size: 20),
            color: C.panel,
            onSelected: (value) {
              switch (value) {
                case 'diagnostics':
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const DiagnosticsScreen()),
                  );
                  break;
                case 'executor':
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const ExecutorLogScreen()),
                  );
                  break;
                case 'monitor':
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const MonitorSettingsScreen()),
                  );
                  break;
              }
            },
            itemBuilder: (context) => const [
              PopupMenuItem(
                value: 'diagnostics',
                child: Row(
                  children: [
                    Icon(Icons.analytics, color: C.info, size: 18),
                    SizedBox(width: 8),
                    Text('Diagnostics'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'executor',
                child: Row(
                  children: [
                    Icon(Icons.history, color: C.textMuted, size: 18),
                    SizedBox(width: 8),
                    Text('Action Log'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'monitor',
                child: Row(
                  children: [
                    Icon(Icons.settings, color: C.textMuted, size: 18),
                    SizedBox(width: 8),
                    Text('Monitor Settings'),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildHealthChip() {
    final state = _buildPlantState();
    final alive = state.isAlive;
    final damage = state.cumulativeDamage;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: alive ? C.greenSoft.withOpacity(0.85) : C.danger.withOpacity(0.8),
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
    );
  }

  Widget _buildStartView() {
    return Center(
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Panel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.grass, color: C.green, size: 24),
                        SizedBox(width: 12),
                        Text(
                          'Start New Simulation',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    const Text(
                      'Select a plant to begin:',
                      style: TextStyle(color: C.textMuted),
                    ),
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      decoration: BoxDecoration(
                        color: C.panelAlt,
                        border: Border.all(color: C.border),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: DropdownButton<String>(
                        isDense: true,
                        isExpanded: true,
                        underline: const SizedBox(),
                        value: selectedPlant,
                        items: availablePlants.map((plant) {
                          final displayName = plant.commonNames.isNotEmpty
                              ? plant.commonNames.first
                              : plant.id;
                          return DropdownMenuItem(
                            value: plant.id,
                            child: Text(displayName),
                          );
                        }).toList(),
                        onChanged: (value) {
                          setState(() => selectedPlant = value);
                        },
                      ),
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: ElevatedButton(
                        onPressed: isLoading ? null : _startSimulation,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: C.green,
                        ),
                        child: isLoading
                            ? const SizedBox(
                                height: 20,
                                width: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation(C.bg),
                                ),
                              )
                            : const Text(
                                'Start Simulation',
                                style: TextStyle(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 14,
                                ),
                              ),
                      ),
                    ),
                    if (error != null) ...[
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: C.danger.withOpacity(0.1),
                          border: Border.all(color: C.danger),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          error!,
                          style: const TextStyle(
                            color: C.danger,
                            fontSize: 12,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildRunningView() {
    final plantState = _buildPlantState();

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth > 1100) {
          return _buildWideLayout(plantState);
        } else if (constraints.maxWidth > 700) {
          return _buildMediumLayout(plantState);
        } else {
          return _buildNarrowLayout(plantState);
        }
      },
    );
  }

  Widget _buildWideLayout(PlantState state) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 300,
          child: _scrollCol([
            _buildPlantPanel(state),
            _buildCoreStatePanel(state),
            _buildPhenologyPanel(state),
          ]),
        ),
        Expanded(
          child: _scrollCol([
            _buildEnvironmentPanel(state),
            _buildHistoryPanel(),
            _buildAgentStatsPanel(),
          ]),
        ),
        SizedBox(
          width: 340,
          child: _scrollCol([
            _buildActionsPanel(),
            _buildControlPanel(),
          ]),
        ),
      ],
    );
  }

  Widget _buildMediumLayout(PlantState state) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 3,
          child: _scrollCol([
            _buildPlantPanel(state),
            _buildEnvironmentPanel(state),
            _buildHistoryPanel(),
          ]),
        ),
        Expanded(
          flex: 2,
          child: _scrollCol([
            _buildCoreStatePanel(state),
            _buildPhenologyPanel(state),
            _buildAgentStatsPanel(),
            _buildActionsPanel(),
            _buildControlPanel(),
          ]),
        ),
      ],
    );
  }

  Widget _buildNarrowLayout(PlantState state) {
    return _scrollCol([
      _buildPlantPanel(state),
      _buildCoreStatePanel(state),
      _buildPhenologyPanel(state),
      _buildEnvironmentPanel(state),
      _buildHistoryPanel(),
      _buildAgentStatsPanel(),
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
            .map((w) => Padding(padding: const EdgeInsets.only(bottom: 12), child: w))
            .toList(),
      ),
    );
  }

  // === PANEL WIDGETS ===

  Widget _buildPlantPanel(PlantState state) {
    return Panel(
      child: Column(
        children: [
          const PanelTitle('Plant Visual'),
          Center(child: PlantVisual(state: state)),
          const SizedBox(height: 6),
          Text(
            '${selectedPlant ?? "Plant"} · ${state.stageLabel} · Day ${state.day}',
            style: const TextStyle(color: C.textMuted, fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget _buildCoreStatePanel(PlantState state) {
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Core State'),
          MetricTile(
            label: 'Biomass',
            value: state.biomass.toStringAsFixed(1),
            unit: 'g',
          ),
          const SizedBox(height: 6),
          MetricTile(
            label: 'Leaf Area',
            value: state.leafArea.toStringAsFixed(3),
            unit: 'm²',
          ),
          const SizedBox(height: 6),
          MetricTile(
            label: 'Thermal Time',
            value: state.thermalTime.toStringAsFixed(0),
            unit: '°C·h',
          ),
          const SizedBox(height: 6),
          MetricTile(
            label: 'Damage',
            value: state.cumulativeDamage.toStringAsFixed(1),
            unit: '%',
            warn: state.cumulativeDamage > 20,
          ),
          const SizedBox(height: 8),
          BarGauge(value: state.cumulativeDamage),
          const SizedBox(height: 3),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('0%', style: TextStyle(fontSize: 9, color: C.textMuted)),
              Text(
                '${state.cumulativeDamage.toStringAsFixed(0)}%',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: state.cumulativeDamage < 30
                      ? C.green
                      : state.cumulativeDamage < 60
                          ? C.warn
                          : C.danger,
                ),
              ),
              const Text('95% ☠', style: TextStyle(fontSize: 9, color: C.textMuted)),
            ],
          ),
          const SizedBox(height: 10),
          _stressRow('Water', state.waterStress, C.water),
          _stressRow('Temperature', state.tempStress, C.hvac),
          _stressRow('Nutrient', state.nutrientStress, C.nutrient),
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
            child: Text(
              label,
              style: const TextStyle(fontSize: 11, color: C.textMuted),
            ),
          ),
          Expanded(
            child: BarGauge(value: value * 100, color: color, height: 4),
          ),
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

  Widget _buildPhenologyPanel(PlantState state) {
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Growth Stage'),
          PhenologyBar(current: GrowthStage.fromIndex(state.stage)),
          const SizedBox(height: 4),
          Text(
            state.stageLabel,
            style: const TextStyle(fontSize: 11, color: C.textMuted),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildEnvironmentPanel(PlantState state) {
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
              _envTile(
                'Soil Moisture',
                '${state.soilWater.toStringAsFixed(1)}%',
                state.soilWater < 15 ? C.danger : null,
              ),
              _envTile(
                'Air Temp',
                '${state.airTemp.toStringAsFixed(1)}°C',
                (state.airTemp > 33 || state.airTemp < 12) ? C.danger : null,
              ),
              _envTile('Humidity', '${state.relativeHumidity.toStringAsFixed(0)}%', null),
              _envTile('PAR', state.lightPAR.toStringAsFixed(0), null),
              _envTile('VPD', '${state.vpd.toStringAsFixed(2)} kPa', null),
              _envTile('Soil Temp', '${state.soilTemp.toStringAsFixed(1)}°C', null),
              _envTile(
                'Soil N',
                '${state.soilN.toStringAsFixed(0)} ppm',
                state.soilN < 60 ? C.warn : null,
              ),
              _envTile(
                'Soil EC',
                '${state.soilEC.toStringAsFixed(2)} mS/cm',
                state.soilEC > 3.5 ? C.danger : null,
              ),
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
        border: alert != null ? Border.all(color: alert.withOpacity(0.4)) : null,
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
            Text('No history data yet', style: TextStyle(color: C.textMuted, fontSize: 12)),
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
            slice.map((h) => (h['biomass'] ?? 0.0).toDouble()).toList(),
            0,
            300,
            C.green,
          ),
          const SizedBox(height: 8),
          _chartRow(
            'Damage',
            slice.map((h) => (h['cumulative_damage'] ?? 0.0).toDouble()).toList(),
            0,
            100,
            C.danger,
          ),
          const SizedBox(height: 8),
          _chartRow(
            'Soil Moisture',
            slice.map((h) => (h['soil_water'] ?? 0.0).toDouble()).toList(),
            0,
            50,
            C.water,
          ),
          const SizedBox(height: 8),
          _chartRow(
            'Air Temp',
            slice.map((h) => (h['air_temp'] ?? 0.0).toDouble()).toList(),
            5,
            45,
            C.warn,
          ),
        ],
      ),
    );
  }

  Widget _chartRow(String label, List<double> data, double minY, double maxY, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(fontSize: 10, color: C.textMuted)),
            if (data.isNotEmpty)
              Text(
                data.last.toStringAsFixed(1),
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: color,
                ),
              ),
          ],
        ),
        const SizedBox(height: 2),
        Sparkline(data: data, minY: minY, maxY: maxY, color: color, height: 40),
      ],
    );
  }

  Widget _buildAgentStatsPanel() {
    return Panel(
      accentLeft: C.info,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PanelTitle('Agent Statistics'),
          if (agentStats == null)
            const Text('No agent data', style: TextStyle(color: C.textMuted, fontSize: 12))
          else
            ...agentStats!.entries.map((e) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(e.key, style: const TextStyle(fontSize: 12, color: C.textMuted)),
                      Text('${e.value}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
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
                color: C.water.withOpacity(0.3),
                compact: true,
                onTap: () => _executeAction(ActionType.water, {'volume_L': 0.2}),
              ),
              AnimButton(
                label: '💡 Light',
                color: C.light.withOpacity(0.3),
                compact: true,
                onTap: () => _executeAction(ActionType.light, {
                  'target_PAR': 600,
                  'power_W': 100,
                }),
              ),
              AnimButton(
                label: '🧪 Feed',
                color: C.nutrient.withOpacity(0.3),
                compact: true,
                onTap: () => _executeAction(ActionType.nutrient, {
                  'N_ppm': 50,
                  'P_ppm': 15,
                  'K_ppm': 40,
                }),
              ),
              AnimButton(
                label: '🌡️ Cool',
                color: C.hvac.withOpacity(0.3),
                compact: true,
                onTap: () => _executeAction(ActionType.hvac, {'target_temp_C': 25}),
              ),
              AnimButton(
                label: '💨 Humidity',
                color: C.humidity.withOpacity(0.3),
                compact: true,
                onTap: () => _executeAction(ActionType.humidity, {'target_RH': 65}),
              ),
              AnimButton(
                label: '🌬️ Vent',
                color: C.vent.withOpacity(0.3),
                compact: true,
                onTap: () => _executeAction(ActionType.ventilation, {'rate': 0.5}),
              ),
            ],
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
              style: ElevatedButton.styleFrom(
                backgroundColor: C.danger,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
