import 'package:flutter/material.dart';
import '../theme.dart';
import '../widgets/shared.dart';
import '../services/api_client.dart';

class DiagnosticsScreen extends StatefulWidget {
  const DiagnosticsScreen({super.key});

  @override
  State<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends State<DiagnosticsScreen> {
  List<DiagnosticItem> diagnostics = [];
  bool isLoading = false;
  String? error;
  final ApiClient _api = ApiClient();

  @override
  void initState() {
    super.initState();
    _fetchDiagnostics();
  }

  Future<void> _fetchDiagnostics() async {
    setState(() {
      isLoading = true;
      error = null;
    });

    try {
      final response = await _api.getDiagnostics(limit: 10);
      if (response.success) {
        setState(() {
          diagnostics = response.diagnostics;
        });
      } else {
        setState(() {
          error = response.error ?? 'Failed to fetch diagnostics';
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
        title: const Text('Agent Diagnostics'),
        backgroundColor: C.panel,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: isLoading ? null : _fetchDiagnostics,
            tooltip: 'Refresh',
          ),
        ],
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
                        onPressed: _fetchDiagnostics,
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
                            const PanelTitle('Agent Diagnostics'),
                            const SizedBox(height: 12),
                            if (diagnostics.isEmpty)
                              const Text(
                                'No diagnostics available',
                                style: TextStyle(color: C.textMuted),
                              )
                            else
                              ...diagnostics.map(
                                (d) => _DiagnosticCard(diagnostic: d),
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

class _DiagnosticCard extends StatelessWidget {
  final DiagnosticItem diagnostic;

  const _DiagnosticCard({required this.diagnostic});

  // Backend sends alertSeverity: 'WARNING', 'CRITICAL', 'INFO', etc.
  Color _severityColor() {
    switch (diagnostic.alertSeverity.toUpperCase()) {
      case 'CRITICAL':
        return C.danger;
      case 'WARNING':
        return C.warn;
      default:
        return C.info;
    }
  }

  IconData _severityIcon() {
    switch (diagnostic.alertSeverity.toUpperCase()) {
      case 'CRITICAL':
        return Icons.error;
      case 'WARNING':
        return Icons.warning_amber;
      default:
        return Icons.info;
    }
  }

  // status is 'analyzed' (RAG) or 'fallback' (rule-based)
  Color _statusColor() {
    return diagnostic.status == 'analyzed' ? C.green : C.textMuted;
  }

  @override
  Widget build(BuildContext context) {
    final color = _severityColor();
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: C.panelAlt,
        borderRadius: BorderRadius.circular(8),
        border: Border(left: BorderSide(color: color, width: 3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(_severityIcon(), color: color, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Hour ${diagnostic.hour} · ${diagnostic.alertSeverity}',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: color,
                    fontSize: 15,
                  ),
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: _statusColor().withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  diagnostic.status.toUpperCase(),
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: _statusColor(),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            diagnostic.diagnostic,
            style: const TextStyle(
                color: C.textMuted, fontSize: 14, height: 1.4),
          ),
        ],
      ),
    );
  }
}
