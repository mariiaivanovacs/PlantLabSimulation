import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http; // ignore: depend_on_referenced_packages

/// API client for Flask backend.
/// Override the base URL at build time:
///   flutter run --dart-define=API_BASE_URL=http://192.168.1.22:5010/api
class ApiClient {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:5010/api',
  );

  // Singleton instance
  static final ApiClient _instance = ApiClient._internal();

  factory ApiClient() {
    return _instance;
  }

  ApiClient._internal();

  // Auth token — set by _AuthGate after Firebase login
  String? _authToken;

  void setToken(String? token) {
    _authToken = token;
  }

  Map<String, String> _buildHeaders({bool json = false}) {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (_authToken != null) headers['Authorization'] = 'Bearer $_authToken';
    return headers;
  }

  // Helper: make GET request.
  // Backend returns 400 (not 404/503) when no simulation is running,
  // so we decode those bodies too (they contain {success:false, error:...}).
  Future<dynamic> getRequest(String endpoint) async {
    try {
      final url = Uri.parse('$baseUrl$endpoint');
      final response = await http.get(url, headers: _buildHeaders()).timeout(
            const Duration(seconds: 10),
            onTimeout: () => throw TimeoutException('Request timeout'),
          );

      if (response.statusCode == 200 || response.statusCode == 400) {
        return jsonDecode(response.body);
      } else {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      throw Exception('GET $endpoint failed: $e');
    }
  }

  // Helper: make POST request.
  // Backend returns 400 (not 404/503) when no simulation is running,
  // so we decode those bodies too (they contain {success:false, error:...}).
  Future<dynamic> postRequest(
      String endpoint, Map<String, dynamic> body) async {
    try {
      final url = Uri.parse('$baseUrl$endpoint');
      final response = await http
          .post(
            url,
            headers: _buildHeaders(json: true),
            body: jsonEncode(body),
          )
          .timeout(
            const Duration(seconds: 10),
            onTimeout: () => throw TimeoutException('Request timeout'),
          );

      if (response.statusCode == 200 || response.statusCode == 400) {
        return jsonDecode(response.body);
      } else {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      throw Exception('POST $endpoint failed: $e');
    }
  }

  Future<dynamic> putRequest(
      String endpoint, Map<String, dynamic> body) async {
    try {
      final url = Uri.parse('$baseUrl$endpoint');
      final response = await http
          .put(
            url,
            headers: _buildHeaders(json: true),
            body: jsonEncode(body),
          )
          .timeout(
            const Duration(seconds: 10),
            onTimeout: () => throw TimeoutException('Request timeout'),
          );

      if (response.statusCode == 200 || response.statusCode == 400) {
        return jsonDecode(response.body);
      } else {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      throw Exception('PUT $endpoint failed: $e');
    }
  }

  // --- Agent endpoints ---

  /// GET /agents/status
  Future<AgentStatusResponse> getAgentStatus() async {
    final response = await getRequest('/agents/status');
    return AgentStatusResponse.fromJson(response);
  }

  /// GET /agents/diagnostics?limit=5
  Future<DiagnosticsResponse> getDiagnostics({int limit = 5}) async {
    final response = await getRequest('/agents/diagnostics?limit=$limit');
    return DiagnosticsResponse.fromJson(response);
  }

  /// GET /agents/executor/log?limit=20
  Future<ExecutorLogResponse> getExecutorLog({int limit = 20}) async {
    final response = await getRequest('/agents/executor/log?limit=$limit');
    return ExecutorLogResponse.fromJson(response);
  }

  /// POST /agents/monitor/enable
  Future<MonitorResponse> setMonitorEnabled(bool enabled) async {
    final response = await postRequest('/agents/monitor/enable', {
      'enabled': enabled,
    });
    return MonitorResponse.fromJson(response);
  }

  /// POST /agents/execute
  Future<ExecuteResponse> executeAction(
      String toolType, Map<String, dynamic> parameters) async {
    final response = await postRequest('/agents/execute', {
      'tool_type': toolType,
      'parameters': parameters,
    });
    return ExecuteResponse.fromJson(response);
  }

  // --- Simulation endpoints ---

  /// POST /simulation/start
  Future<SimulationStartResponse> startSimulation({
    required String plantName,
    required int days,
    String mode = 'speed',
    int hoursPerTick = 1,
    double tickDelay = 0.1,
    bool dailyRegime = false,
    bool monitorEnabled = true,
  }) async {
    final response = await postRequest('/simulation/start', {
      'plant_name': plantName,
      'days': days,
      'mode': mode,
      'hours_per_tick': hoursPerTick,
      'tick_delay': tickDelay,
      'daily_regime': dailyRegime,
      'monitor_enabled': monitorEnabled,
    });
    return SimulationStartResponse.fromJson(response);
  }

  /// GET /simulation/state
  Future<SimulationStateResponse> getSimulationState() async {
    final response = await getRequest('/simulation/state');
    return SimulationStateResponse.fromJson(response);
  }

  /// GET /simulation/history?limit=24
  Future<SimulationHistoryResponse> getSimulationHistory(
      {int limit = 24}) async {
    final response = await getRequest('/simulation/history?limit=$limit');
    return SimulationHistoryResponse.fromJson(response);
  }

  /// GET /simulation/plants
  Future<PlantsResponse> getAvailablePlants() async {
    final response = await getRequest('/simulation/plants');
    return PlantsResponse.fromJson(response);
  }

  /// POST /simulation/stop
  Future<SimulationStopResponse> stopSimulation() async {
    final response = await postRequest('/simulation/stop', {});
    return SimulationStopResponse.fromJson(response);
  }

  /// POST /simulation/step
  Future<SimulationStepResponse> stepSimulation(int hours) async {
    final response = await postRequest('/simulation/step', {'hours': hours});
    return SimulationStepResponse.fromJson(response);
  }

  /// GET /simulation/metrics
  Future<Map<String, List<Map<String, dynamic>>>> getMetrics() async {
    final response = await getRequest('/simulation/metrics');
    final files = response['files'] as Map<String, dynamic>? ?? {};
    final result = <String, List<Map<String, dynamic>>>{};
    for (final entry in files.entries) {
      final list = entry.value as List<dynamic>? ?? [];
      result[entry.key] = list
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
    }
    return result;
  }

  // --- User profile endpoints ---

  /// POST /auth/profile — create or return existing profile
  Future<Map<String, dynamic>> createProfile(String displayName) async {
    final response =
        await postRequest('/auth/profile', {'display_name': displayName});
    return Map<String, dynamic>.from(response['profile'] ?? response);
  }

  /// GET /auth/profile — fetch current user's profile
  Future<Map<String, dynamic>?> getProfile() async {
    try {
      final response = await getRequest('/auth/profile');
      if (response['success'] == true) {
        return Map<String, dynamic>.from(response['profile'] ?? {});
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// PUT /auth/profile — partial update of allowed fields
  Future<Map<String, dynamic>> updateProfile(
      Map<String, dynamic> patch) async {
    final response = await putRequest('/auth/profile', patch);
    return Map<String, dynamic>.from(response['profile'] ?? response);
  }

}

// --- Response Models ---

class AgentStatusResponse {
  final bool success;
  final Map<String, dynamic> statistics;
  final String? error;

  AgentStatusResponse({
    required this.success,
    required this.statistics,
    this.error,
  });

  factory AgentStatusResponse.fromJson(Map<String, dynamic> json) {
    return AgentStatusResponse(
      success: json['success'] ?? false,
      statistics: Map<String, dynamic>.from(json['statistics'] ?? {}),
      error: json['error'],
    );
  }
}

class DiagnosticsResponse {
  final bool success;
  final List<DiagnosticItem> diagnostics;
  final String? error;

  DiagnosticsResponse({
    required this.success,
    required this.diagnostics,
    this.error,
  });

  factory DiagnosticsResponse.fromJson(Map<String, dynamic> json) {
    final diagList = (json['diagnostics'] as List<dynamic>?)?.map((d) {
          return DiagnosticItem.fromJson(d as Map<String, dynamic>);
        }).toList() ??
        [];

    return DiagnosticsResponse(
      success: json['success'] ?? false,
      diagnostics: diagList,
      error: json['error'],
    );
  }
}

// Backend returns: { status, diagnostic, alert_severity, hour }
class DiagnosticItem {
  final String status; // 'analyzed' or 'fallback'
  final String diagnostic;
  final String alertSeverity; // 'WARNING', 'CRITICAL', etc.
  final int hour;

  DiagnosticItem({
    required this.status,
    required this.diagnostic,
    required this.alertSeverity,
    required this.hour,
  });

  factory DiagnosticItem.fromJson(Map<String, dynamic> json) {
    return DiagnosticItem(
      status: json['status'] ?? 'fallback',
      diagnostic: json['diagnostic'] ?? '',
      alertSeverity: json['alert_severity'] ?? 'UNKNOWN',
      hour: json['hour'] ?? 0,
    );
  }
}

class ExecutorLogResponse {
  final bool success;
  final int total;
  final List<ExecutorLogItem> log;
  final String? error;

  ExecutorLogResponse({
    required this.success,
    required this.total,
    required this.log,
    this.error,
  });

  factory ExecutorLogResponse.fromJson(Map<String, dynamic> json) {
    final logList = (json['log'] as List<dynamic>?)?.map((item) {
          return ExecutorLogItem.fromJson(item as Map<String, dynamic>);
        }).toList() ??
        [];

    return ExecutorLogResponse(
      success: json['success'] ?? false,
      total: json['total'] ?? 0,
      log: logList,
      error: json['error'],
    );
  }
}

// Backend returns: { hour, tool_type, parameters, success, message }
class ExecutorLogItem {
  final int hour;
  final String toolType;
  final bool success;
  final Map<String, dynamic> parameters;
  final String message;

  ExecutorLogItem({
    required this.hour,
    required this.toolType,
    required this.success,
    required this.parameters,
    required this.message,
  });

  factory ExecutorLogItem.fromJson(Map<String, dynamic> json) {
    return ExecutorLogItem(
      hour: json['hour'] ?? 0,
      toolType: json['tool_type'] ?? '',
      success: json['success'] ?? false,
      parameters: Map<String, dynamic>.from(json['parameters'] ?? {}),
      message: json['message'] ?? '',
    );
  }
}

class MonitorResponse {
  final bool success;
  final bool monitorEnabled;
  final String? error;

  MonitorResponse({
    required this.success,
    required this.monitorEnabled,
    this.error,
  });

  factory MonitorResponse.fromJson(Map<String, dynamic> json) {
    return MonitorResponse(
      success: json['success'] ?? false,
      monitorEnabled: json['monitor_enabled'] ?? false,
      error: json['error'],
    );
  }
}

class ExecuteResponse {
  final bool success;
  final String message;
  final Map<String, dynamic> changes;
  final String? error;

  ExecuteResponse({
    required this.success,
    required this.message,
    required this.changes,
    this.error,
  });

  factory ExecuteResponse.fromJson(Map<String, dynamic> json) {
    return ExecuteResponse(
      success: json['success'] ?? false,
      message: json['message'] ?? '',
      changes: Map<String, dynamic>.from(json['changes'] ?? {}),
      error: json['error'],
    );
  }
}

// --- Simulation Response Models ---

class SimulationStartResponse {
  final bool success;
  final String message;
  final String simulationId;
  final String plantId;
  final String profileId;
  final Map<String, dynamic> config;
  final String? error;

  SimulationStartResponse({
    required this.success,
    required this.message,
    required this.simulationId,
    required this.plantId,
    required this.profileId,
    required this.config,
    this.error,
  });

  factory SimulationStartResponse.fromJson(Map<String, dynamic> json) {
    return SimulationStartResponse(
      success: json['success'] ?? false,
      message: json['message'] ?? '',
      simulationId: json['simulation_id'] ?? '',
      plantId: json['plant_id'] ?? '',
      profileId: json['profile_id'] ?? '',
      config: Map<String, dynamic>.from(json['config'] ?? {}),
      error: json['error'],
    );
  }
}

class SimulationStateResponse {
  final bool success;
  final bool running;
  final Map<String, dynamic> state;
  final Map<String, dynamic> summary;
  final Map<String, dynamic> config;
  final String? error;

  SimulationStateResponse({
    required this.success,
    required this.running,
    required this.state,
    required this.summary,
    required this.config,
    this.error,
  });

  factory SimulationStateResponse.fromJson(Map<String, dynamic> json) {
    return SimulationStateResponse(
      success: json['success'] ?? false,
      running: json['running'] ?? false,
      state: Map<String, dynamic>.from(json['state'] ?? {}),
      summary: Map<String, dynamic>.from(json['summary'] ?? {}),
      config: Map<String, dynamic>.from(json['config'] ?? {}),
      error: json['error'],
    );
  }
}

class SimulationHistoryResponse {
  final bool success;
  final int totalHours;
  final int returned;
  final List<Map<String, dynamic>> history;
  final String? error;

  SimulationHistoryResponse({
    required this.success,
    required this.totalHours,
    required this.returned,
    required this.history,
    this.error,
  });

  factory SimulationHistoryResponse.fromJson(Map<String, dynamic> json) {
    final histList = (json['history'] as List<dynamic>?)
            ?.map((h) => Map<String, dynamic>.from(h as Map))
            .toList() ??
        [];
    return SimulationHistoryResponse(
      success: json['success'] ?? false,
      totalHours: json['total_hours'] ?? 0,
      returned: json['returned'] ?? 0,
      history: histList,
      error: json['error'],
    );
  }
}

class PlantsResponse {
  final bool success;
  final List<PlantProfile> plants;
  final String? error;

  PlantsResponse({
    required this.success,
    required this.plants,
    this.error,
  });

  factory PlantsResponse.fromJson(Map<String, dynamic> json) {
    final plantsList = (json['plants'] as List<dynamic>?)
            ?.map((p) => PlantProfile.fromJson(p as Map<String, dynamic>))
            .toList() ??
        [];
    return PlantsResponse(
      success: json['success'] ?? false,
      plants: plantsList,
      error: json['error'],
    );
  }
}

class PlantProfile {
  final String id;
  final String name;
  final List<String> commonNames;

  PlantProfile({
    required this.id,
    required this.name,
    required this.commonNames,
  });

  factory PlantProfile.fromJson(Map<String, dynamic> json) {
    return PlantProfile(
      id: json['id'] ?? '',
      name: json['name'] ?? '',
      commonNames: json['common_names'] != null
          ? List<String>.from(json['common_names'])
          : [],
    );
  }
}

class SimulationStopResponse {
  final bool success;
  final String message;
  final Map<String, dynamic> summary;
  final String? reasoningLog;
  final String? error;

  SimulationStopResponse({
    required this.success,
    required this.message,
    required this.summary,
    this.reasoningLog,
    this.error,
  });

  factory SimulationStopResponse.fromJson(Map<String, dynamic> json) {
    return SimulationStopResponse(
      success: json['success'] ?? false,
      message: json['message'] ?? '',
      summary: Map<String, dynamic>.from(json['summary'] ?? {}),
      reasoningLog: json['reasoning_log'],
      error: json['error'],
    );
  }
}

class SimulationStepResponse {
  final bool success;
  final int hoursStipped;
  final Map<String, dynamic> state;
  final Map<String, dynamic> summary;
  final String? error;

  SimulationStepResponse({
    required this.success,
    required this.hoursStipped,
    required this.state,
    required this.summary,
    this.error,
  });

  factory SimulationStepResponse.fromJson(Map<String, dynamic> json) {
    return SimulationStepResponse(
      success: json['success'] ?? false,
      hoursStipped: json['hours_stepped'] ?? 0,
      state: Map<String, dynamic>.from(json['state'] ?? {}),
      summary: Map<String, dynamic>.from(json['summary'] ?? {}),
      error: json['error'],
    );
  }
}

