import 'package:flutter/material.dart';
import '../theme.dart';
import '../widgets/shared.dart';
import '../services/api_client.dart';

class MonitorSettingsScreen extends StatefulWidget {
  const MonitorSettingsScreen({super.key});

  @override
  State<MonitorSettingsScreen> createState() => _MonitorSettingsScreenState();
}

class _MonitorSettingsScreenState extends State<MonitorSettingsScreen> {
  bool monitorEnabled = true;
  bool isLoading = false;
  String? error;
  Map<String, dynamic>? stats;
  final ApiClient _api = ApiClient();

  @override
  void initState() {
    super.initState();
    _loadMonitorStatus();
  }

  Future<void> _loadMonitorStatus() async {
    setState(() {
      isLoading = true;
      error = null;
    });

    try {
      final response = await _api.getAgentStatus();
      if (response.success) {
        // orchestrator.get_statistics() returns:
        //   { monitor_enabled, reasoning: { total_alerts, warnings, criticals, ... }, executor_actions }
        final reasoning = response.statistics['reasoning'] as Map<String, dynamic>? ?? {};
        setState(() {
          monitorEnabled = response.statistics['monitor_enabled'] ?? true;
          stats = {
            'total_alerts': reasoning['total_alerts'] ?? 0,
            'warnings': reasoning['warnings'] ?? 0,
            'criticals': reasoning['criticals'] ?? 0,
            'executor_actions': response.statistics['executor_actions'] ?? 0,
            'gemini_calls': reasoning['gemini_queries'] ?? 0,
          };
        });
      } else {
        setState(() {
          error = response.error ?? 'Failed to load monitor status';
        });
      }
    } catch (e) {
      setState(() {
        error = e.toString();
      });
    } finally {
      setState(() {
        isLoading = false;
      });
    }
  }

  Future<void> _toggleMonitor(bool value) async {
    final previousState = monitorEnabled;
    setState(() {
      monitorEnabled = value;
    });

    try {
      final response = await _api.setMonitorEnabled(value);
      if (response.success) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Monitor ${value ? 'enabled' : 'disabled'}'),
            backgroundColor: C.green,
            duration: const Duration(seconds: 2),
          ),
        );
        _loadMonitorStatus();
      } else {
        if (!mounted) return;
        setState(() {
          monitorEnabled = previousState;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed: ${response.error ?? 'Unknown error'}'),
            backgroundColor: C.danger,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        monitorEnabled = previousState;
        error = e.toString();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Failed to update monitor'),
          backgroundColor: C.danger,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  Future<void> _clearAlertHistory() async {
    try {
      final response = await _api.postRequest('/agents/alerts/clear', {});
      final success = response['success'] ?? false;
      if (!mounted) return;
      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Alert history cleared'),
            backgroundColor: C.green,
            duration: Duration(seconds: 2),
          ),
        );
        _loadMonitorStatus();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed: ${response['error'] ?? 'Unknown error'}'),
            backgroundColor: C.danger,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error: $e'),
          backgroundColor: C.danger,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Monitor Settings'),
        backgroundColor: C.panel,
        elevation: 0,
      ),
      backgroundColor: C.bg,
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Status Card
                  Panel(
                    accentLeft: monitorEnabled ? C.green : C.textDim,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              monitorEnabled
                                  ? Icons.check_circle
                                  : Icons.cancel,
                              color: monitorEnabled ? C.green : C.danger,
                              size: 24,
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const PanelTitle('Monitor Agent Status'),
                                  Text(
                                    monitorEnabled
                                        ? 'Active & Monitoring'
                                        : 'Disabled',
                                    style: TextStyle(
                                      color:
                                          monitorEnabled ? C.green : C.danger,
                                      fontSize: 18,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Switch(
                              value: monitorEnabled,
                              onChanged: _toggleMonitor,
                              activeThumbColor: C.green,
                              inactiveThumbColor: C.textDim,
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Statistics
                  if (stats != null) ...[
                    const Text(
                      'Alert Statistics',
                      style: TextStyle(
                        color: C.green,
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Panel(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: _StatCard(
                                  label: 'Total Alerts',
                                  value: '${stats!['total_alerts']}',
                                  color: C.info,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _StatCard(
                                  label: 'Warnings',
                                  value: '${stats!['warnings']}',
                                  color: C.warn,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _StatCard(
                                  label: 'Critical',
                                  value: '${stats!['criticals']}',
                                  color: C.danger,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: Panel(
                            accentLeft: C.info,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Executor Actions',
                                  style: TextStyle(
                                    color: C.textMuted,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  '${stats!['executor_actions']} applied',
                                  style: const TextStyle(
                                    fontSize: 17,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Panel(
                            accentLeft: C.green,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: const [
                                    Icon(Icons.auto_awesome,
                                        size: 14, color: C.green),
                                    SizedBox(width: 4),
                                    Text(
                                      'LLM API Calls',
                                      style: TextStyle(
                                        color: C.textMuted,
                                        fontSize: 15,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  '${stats!['gemini_calls']} calls',
                                  style: const TextStyle(
                                    fontSize: 17,
                                    fontWeight: FontWeight.w500,
                                    color: C.green,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],

                  // Information
                  const Text(
                    'About Monitor Agent',
                    style: TextStyle(
                      color: C.green,
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Panel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        Text(
                          'The Monitor Agent continuously evaluates plant conditions and generates alerts when critical thresholds are exceeded.',
                          style: TextStyle(
                            color: C.textMuted,
                            fontSize: 16,
                            height: 1.5,
                          ),
                        ),
                        SizedBox(height: 12),
                        Text(
                          'Monitored Parameters:',
                          style: TextStyle(
                            color: C.textPrimary,
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        SizedBox(height: 8),
                        _MonitoredParam(
                          name: 'Soil Moisture',
                          threshold: '< 15%',
                        ),
                        _MonitoredParam(
                          name: 'Air Temperature',
                          threshold: '< 12°C or > 33°C',
                        ),
                        _MonitoredParam(name: 'VPD', threshold: '> 1.5 kPa'),
                        _MonitoredParam(
                          name: 'Cumulative Damage',
                          threshold: '> 50% or > 10%',
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Actions
                  Panel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const PanelTitle('Actions'),
                        const SizedBox(height: 8),
                        SizedBox(
                          width: double.infinity,
                          child: ElevatedButton.icon(
                            onPressed: _clearAlertHistory,
                            icon: const Icon(Icons.delete_outline),
                            label: const Text('Clear Alert History'),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: C.danger.withValues(alpha: 0.2),
                              foregroundColor: C.danger,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _StatCard({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: C.bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            value,
            style: TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(
              color: C.textMuted,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _MonitoredParam extends StatelessWidget {
  final String name;
  final String threshold;

  const _MonitoredParam({required this.name, required this.threshold});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          const Icon(Icons.check_circle, color: C.green, size: 16),
          const SizedBox(width: 6),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: const TextStyle(
                    color: C.textPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  'Threshold: $threshold',
                  style: const TextStyle(color: C.textDim, fontSize: 15),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
