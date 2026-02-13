import 'package:flutter/material.dart';
import '../theme.dart';
import '../widgets/shared.dart';
import '../services/api_client.dart';

class ExecutorLogScreen extends StatefulWidget {
  const ExecutorLogScreen({super.key});

  @override
  State<ExecutorLogScreen> createState() => _ExecutorLogScreenState();
}

class _ExecutorLogScreenState extends State<ExecutorLogScreen> {
  List<ExecutorLogItem> actions = [];
  bool isLoading = false;
  String? error;
  int limit = 50;
  final ApiClient _api = ApiClient();

  @override
  void initState() {
    super.initState();
    _fetchExecutorLog();
  }

  Future<void> _fetchExecutorLog() async {
    setState(() {
      isLoading = true;
      error = null;
    });

    try {
      final response = await _api.getExecutorLog(limit: limit);
      if (response.success) {
        setState(() {
          actions = response.log;
        });
      } else {
        setState(() {
          error = response.error ?? 'Failed to fetch executor log';
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Executor Action Log'),
        backgroundColor: C.panel,
        elevation: 0,
      ),
      backgroundColor: C.bg,
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.error_outline,
                          color: C.danger, size: 48),
                      const SizedBox(height: 16),
                      Text(error!, style: const TextStyle(color: C.textMuted)),
                      const SizedBox(height: 24),
                      ElevatedButton(
                        onPressed: _fetchExecutorLog,
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Panel(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const PanelTitle('Tool Execution History'),
                            const SizedBox(height: 12),
                            if (actions.isEmpty)
                              const Text(
                                'No actions recorded',
                                style: TextStyle(color: C.textMuted),
                              )
                            else
                              ...actions.map((a) => _ActionLogTile(action: a)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }
}

class _ActionLogTile extends StatefulWidget {
  final ExecutorLogItem action;

  const _ActionLogTile({required this.action});

  @override
  State<_ActionLogTile> createState() => _ActionLogTileState();
}

class _ActionLogTileState extends State<_ActionLogTile> {
  bool expanded = false;

  Color _statusColor() {
    return widget.action.success ? C.green : C.danger;
  }

  IconData _toolIcon() {
    switch (widget.action.toolType) {
      case 'watering':
        return Icons.water_drop;
      case 'lighting':
        return Icons.lightbulb;
      case 'nutrients':
        return Icons.science;
      case 'hvac':
        return Icons.air;
      case 'ventilation':
        return Icons.wind_power;
      case 'humidity':
        return Icons.cloud;
      case 'co2_control':
        return Icons.cloud_queue;
      default:
        return Icons.build;
    }
  }

  Color _toolColor() {
    switch (widget.action.toolType) {
      case 'watering':
        return C.water;
      case 'lighting':
        return C.light;
      case 'nutrients':
        return C.nutrient;
      case 'hvac':
        return C.hvac;
      case 'ventilation':
        return C.vent;
      case 'humidity':
        return C.humidity;
      case 'co2_control':
        return C.info;
      default:
        return C.textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: C.panelAlt,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          InkWell(
            onTap: () => setState(() => expanded = !expanded),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Icon(_toolIcon(), color: _toolColor(), size: 20),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.action.toolType.toUpperCase(),
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          widget.action.message.isNotEmpty
                              ? widget.action.message
                              : 'No message',
                          style: const TextStyle(
                            color: C.textMuted,
                            fontSize: 11,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: _statusColor().withOpacity(0.2),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      widget.action.success ? 'OK' : 'FAIL',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: _statusColor(),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'H${widget.action.hour}',
                    style: const TextStyle(color: C.textDim, fontSize: 10),
                  ),
                  const SizedBox(width: 8),
                  Icon(
                    expanded ? Icons.expand_less : Icons.expand_more,
                    color: C.textMuted,
                    size: 18,
                  ),
                ],
              ),
            ),
          ),
          if (expanded) ...[
            const Divider(color: C.border, height: 1),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Parameters',
                    style: TextStyle(
                      color: C.textMuted,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 6),
                  ...widget.action.parameters.entries.map((e) {
                    final value = e.value;
                    final displayValue = value is double
                        ? value.toStringAsFixed(2)
                        : value.toString();
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        children: [
                          Text(
                            '${e.key}:',
                            style: const TextStyle(
                              color: C.textDim,
                              fontSize: 11,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            displayValue,
                            style: const TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    );
                  }),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class ExecutorAction {
  final String timestamp;
  final String toolType;
  final String status; // 'success', 'warning', 'error'
  final Map<String, dynamic> parameters;
  final String result;

  ExecutorAction({
    required this.timestamp,
    required this.toolType,
    required this.status,
    required this.parameters,
    required this.result,
  });
}
// Note: ExecutorLogItem is defined in services/api_client.dart
