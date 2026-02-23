import 'dart:async';
import 'dart:convert';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'api_client.dart';
import '../models/health_check.dart';

/// Calls the Flask /api/gemini/* endpoints (Gemini API key stays on the server).
class GeminiService {
  static final GeminiService instance = GeminiService._();
  GeminiService._();

  // Gemini image analysis can take ~30 s — use a generous timeout.
  static const _timeout = Duration(seconds: 90);

  /// Fetch a fresh Firebase ID token to authenticate with Flask.
  Future<String?> _idToken() =>
      FirebaseAuth.instance.currentUser?.getIdToken() ??
      Future.value(null);

  Future<Map<String, String>> _headers() async {
    final token = await _idToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Future<Map<String, dynamic>> _post(
      String endpoint, Map<String, dynamic> body) async {
    final url = Uri.parse('${ApiClient.baseUrl}$endpoint');
    final resp = await http
        .post(url, headers: await _headers(), body: jsonEncode(body))
        .timeout(_timeout, onTimeout: () {
      throw TimeoutException('Gemini request timed out after 90 s');
    });

    final decoded = jsonDecode(resp.body) as Map<String, dynamic>;
    if (resp.statusCode >= 400) {
      throw Exception(decoded['error'] ?? 'Server error ${resp.statusCode}');
    }
    return decoded;
  }

  /// Identify a plant from base64 image bytes or a typed text name.
  /// Returns one of: "tomato" | "lettuce" | "basil" | "none"
  Future<String> identifyPlant({String? imageB64, String? plantName}) async {
    assert(imageB64 != null || plantName != null,
        'Provide imageB64 or plantName');
    final body = <String, dynamic>{};
    if (imageB64 != null) body['image_b64'] = imageB64;
    if (plantName != null) body['plant_name'] = plantName;

    final resp = await _post('/gemini/identify', body);
    if (resp['success'] != true) {
      throw Exception(resp['error'] ?? 'Identification failed');
    }
    return resp['identified'] as String;
  }

  /// Full AI health check pipeline:
  ///   Gemini visual analysis → XGBoost stress prediction → merged recommendations.
  ///
  /// [plantId]          Firestore plant doc ID — backend saves history automatically.
  /// [lastWateringDays] Optional: days since last watering (improves water stress prediction).
  /// [roomTempC]        Optional: current room temperature °C.
  /// [soilWaterPct]     Optional: soil moisture estimate 0-100.
  ///
  /// Returns a [HealthCheck] with all prediction fields populated.
  Future<HealthCheck> checkHealth({
    required String imageB64,
    required String plantType,
    required int ageDays,
    required String plantId,
    double? lastWateringDays,
    double? roomTempC,
    double? soilWaterPct,
  }) async {
    final body = <String, dynamic>{
      'image_b64':  imageB64,
      'plant_type': plantType,
      'age_days':   ageDays,
      'plant_id':   plantId,
      if (lastWateringDays != null) 'last_watering_days': lastWateringDays,
      if (roomTempC != null)        'room_temp_c':        roomTempC,
      if (soilWaterPct != null)     'soil_water_pct':     soilWaterPct,
    };

    final resp = await _post('/gemini/health', body);
    if (resp['success'] != true) {
      throw Exception(resp['error'] ?? 'Health check failed');
    }

    // Attach plant_type and age_days so fromApiResponse has them
    resp['plant_type'] = plantType;
    resp['age_days']   = ageDays;

    return HealthCheck.fromApiResponse(resp);
  }
}
