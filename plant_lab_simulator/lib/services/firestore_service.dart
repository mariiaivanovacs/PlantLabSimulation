import 'dart:async';
import 'dart:convert';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'api_client.dart';
import '../models/plant_record.dart';
import '../models/health_check.dart';

/// Reads and writes Home Plant data via the Flask backend.
/// No direct Firestore SDK — all Firestore access is server-side.
///
/// Schema (managed on server):
///   users/{uid}/plants/{plantId}
///   users/{uid}/plants/{plantId}/health_checks/{checkId}
class FirestoreService {
  static final FirestoreService instance = FirestoreService._();
  FirestoreService._();

  static const _timeout = Duration(seconds: 15);

  Future<Map<String, String>> _headers() async {
    final token =
        await FirebaseAuth.instance.currentUser?.getIdToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Future<Map<String, dynamic>> _get(String path) async {
    final url = Uri.parse('${ApiClient.baseUrl}$path');
    final resp = await http
        .get(url, headers: await _headers())
        .timeout(_timeout);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    if (resp.statusCode >= 400) {
      throw Exception(body['error'] ?? 'Server error ${resp.statusCode}');
    }
    return body;
  }

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> payload) async {
    final url = Uri.parse('${ApiClient.baseUrl}$path');
    final resp = await http
        .post(url, headers: await _headers(), body: jsonEncode(payload))
        .timeout(_timeout);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    if (resp.statusCode >= 400) {
      throw Exception(body['error'] ?? 'Server error ${resp.statusCode}');
    }
    return body;
  }

  // ── Plants ──────────────────────────────────────────────────────────────────

  Future<List<PlantRecord>> getPlants() async {
    final resp = await _get('/plants');
    final list = resp['plants'] as List? ?? [];
    return list
        .map((d) => PlantRecord.fromJson(d as Map<String, dynamic>))
        .toList();
  }

  Future<PlantRecord> addPlant({
    required String name,
    required String identifiedAs,
    required int ageDays,
  }) async {
    final resp = await _post('/plants', {
      'name': name,
      'identified_as': identifiedAs,
      'age_days': ageDays,
    });
    return PlantRecord.fromJson(resp['plant'] as Map<String, dynamic>);
  }

  // ── Health checks ────────────────────────────────────────────────────────────

  Future<List<HealthCheck>> getHealthChecks(String plantId) async {
    final resp = await _get('/plants/$plantId/health-checks');
    final list = resp['health_checks'] as List? ?? [];
    return list
        .map((d) => HealthCheck.fromJson(d as Map<String, dynamic>))
        .toList();
  }

  // addHealthCheck is intentionally removed — the backend writes to Firestore
  // automatically at the end of POST /api/gemini/health.
}
