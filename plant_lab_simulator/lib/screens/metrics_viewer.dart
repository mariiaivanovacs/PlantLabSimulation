import 'dart:async';
import 'package:flutter/material.dart';
import '../theme.dart';
import '../services/api_client.dart';
import '../widgets/shared.dart';
import '../widgets/metric_chart.dart';

class MetricsViewerScreen extends StatefulWidget {
  const MetricsViewerScreen({super.key});

  @override
  State<MetricsViewerScreen> createState() => _MetricsViewerScreenState();
}

class _MetricsViewerScreenState extends State<MetricsViewerScreen>
    with SingleTickerProviderStateMixin {
  final ApiClient _api = ApiClient();
  late TabController _tabController;
  Timer? _refreshTimer;
  Map<String, List<Map<String, dynamic>>>? _metricsData;
  bool _loading = true;
  String? _error;

  static const _tabs = ['Growth', 'Environment', 'Water', 'Stress'];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: _tabs.length, vsync: this);
    _fetchMetrics();
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted) _fetchMetrics();
    });
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _fetchMetrics() async {
    try {
      final response = await _api.getMetrics();
      if (!mounted) return;
      setState(() {
        _metricsData = response;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  List<double> _extractColumn(String fileKey, String column) {
    final rows = _metricsData?[fileKey];
    if (rows == null) return [];
    return rows
        .map((r) => (r[column] as num?)?.toDouble())
        .where((v) => v != null)
        .cast<double>()
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: C.bg,
      appBar: AppBar(
        backgroundColor: C.panel,
        title: const Text('Metrics',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        bottom: TabBar(
          controller: _tabController,
          labelColor: C.green,
          unselectedLabelColor: C.textMuted,
          indicatorColor: C.green,
          labelStyle:
              const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          tabs: _tabs.map((t) => Tab(text: t)).toList(),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, size: 20),
            onPressed: _fetchMetrics,
            color: C.textMuted,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: C.green))
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text('Error: $_error',
                        style: const TextStyle(color: C.danger)),
                  ),
                )
              : TabBarView(
                  controller: _tabController,
                  children: [
                    _buildGrowthTab(),
                    _buildEnvironmentTab(),
                    _buildWaterTab(),
                    _buildStressTab(),
                  ],
                ),
    );
  }

  Widget _chartPanel(List<Widget> charts) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: charts
            .map((c) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Panel(child: c),
                ))
            .toList(),
      ),
    );
  }

  Widget _buildGrowthTab() {
    final biomass = _extractColumn('session_log', 'biomass');
    final rgr = _extractColumn('session_log', 'rgr');
    final pGross = _extractColumn('photosynthesis', 'p_gross');
    final rMaint = _extractColumn('respiration', 'r_maint');
    final leafArea = _extractColumn('leaf', 'leaf_area');

    return _chartPanel([
      MetricChart(
        title: 'Biomass',
        yUnit: 'g',
        series: [ChartSeries(label: 'Biomass', data: biomass, color: C.green)],
      ),
      MetricChart(
        title: 'Leaf Area',
        yUnit: 'm\u00B2',
        series: [
          ChartSeries(label: 'Leaf Area', data: leafArea, color: C.greenSoft)
        ],
      ),
      MetricChart(
        title: 'RGR (Relative Growth Rate)',
        yUnit: '/h',
        series: [ChartSeries(label: 'RGR', data: rgr, color: C.olive)],
      ),
      MetricChart(
        title: 'Carbon Fluxes',
        yUnit: 'g/h',
        series: [
          ChartSeries(label: 'Photosynthesis', data: pGross, color: C.green),
          ChartSeries(label: 'Respiration', data: rMaint, color: C.warn),
        ],
      ),
    ]);
  }

  Widget _buildEnvironmentTab() {
    final airTemp = _extractColumn('session_log', 'air_temp');
    final humidity = _extractColumn('session_log', 'humidity');
    final co2 = _extractColumn('session_log', 'co2');
    final co2Consumed = _extractColumn('co2_consumption', 'co2_consumed');

    return _chartPanel([
      MetricChart(
        title: 'Air Temperature',
        yUnit: '\u00B0C',
        series: [
          ChartSeries(label: 'Air Temp', data: airTemp, color: C.hvac)
        ],
      ),
      MetricChart(
        title: 'Relative Humidity',
        yUnit: '%',
        series: [
          ChartSeries(label: 'Humidity', data: humidity, color: C.humidity)
        ],
      ),
      MetricChart(
        title: 'CO\u2082 Level',
        yUnit: 'ppm',
        series: [ChartSeries(label: 'CO\u2082', data: co2, color: C.vent)],
      ),
      MetricChart(
        title: 'CO\u2082 Consumption',
        yUnit: 'g/h',
        series: [
          ChartSeries(
              label: 'Consumed', data: co2Consumed, color: C.greenSoft)
        ],
      ),
    ]);
  }

  Widget _buildWaterTab() {
    final soilOld = _extractColumn('soil_water', 'old_water');
    final soilNew = _extractColumn('soil_water', 'new_water');
    final etPct = _extractColumn('soil_water', 'et_pct');
    final et = _extractColumn('session_log', 'et');

    return _chartPanel([
      MetricChart(
        title: 'Soil Water',
        yUnit: '%',
        series: [
          ChartSeries(label: 'Before', data: soilOld, color: C.water),
          ChartSeries(
              label: 'After',
              data: soilNew,
              color: C.info),
        ],
      ),
      MetricChart(
        title: 'Evapotranspiration',
        yUnit: 'L/h',
        series: [ChartSeries(label: 'ET', data: et, color: C.humidity)],
      ),
      MetricChart(
        title: 'ET as % of Pot Volume',
        yUnit: '%',
        series: [
          ChartSeries(label: 'ET %', data: etPct, color: C.water)
        ],
      ),
    ]);
  }

  Widget _buildStressTab() {
    final waterStress = _extractColumn('session_log', 'water_stress');
    final instantStress = _extractColumn('water_stress', 'instant_stress');
    final accumStress = _extractColumn('water_stress', 'new_stress');

    return _chartPanel([
      MetricChart(
        title: 'Water Stress (Session Log)',
        yUnit: '0-1',
        series: [
          ChartSeries(
              label: 'Water Stress', data: waterStress, color: C.warn)
        ],
      ),
      MetricChart(
        title: 'Water Stress Detail',
        yUnit: '0-1',
        series: [
          ChartSeries(
              label: 'Instantaneous',
              data: instantStress,
              color: C.dangerSoft),
          ChartSeries(
              label: 'Accumulated', data: accumStress, color: C.danger),
        ],
      ),
    ]);
  }
}
