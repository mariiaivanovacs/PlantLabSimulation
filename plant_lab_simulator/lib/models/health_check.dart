/// One AI health check result.
/// Written to Firestore server-side: users/{uid}/plants/{plantId}/health_checks/{id}
class HealthCheck {
  final String id;
  final DateTime timestamp;
  final String plantType;
  final int ageDays;
  final String healthSummary;
  final List<String> recommendedActions;

  // Gemini visual assessment
  final String phenologicalStage;
  final double estimatedBiomassG;
  final double estimatedLeafAreaM2;
  final double leafYellowingScore;   // 0-1
  final double leafDroopScore;       // 0-1
  final double necrosisScore;        // 0-1

  // XGBoost predictions (0-1)
  final double waterStress;
  final double nutrientStress;
  final double temperatureStress;

  // Categorical: "low" | "medium" | "high"
  final String waterStressCat;
  final String nutrientStressCat;
  final String temperatureStressCat;

  final String modelUsed;      // "xgboost" | "rule_based"
  final String? firestoreId;   // server-assigned doc id

  const HealthCheck({
    required this.id,
    required this.timestamp,
    required this.plantType,
    required this.ageDays,
    required this.healthSummary,
    required this.recommendedActions,
    this.phenologicalStage = 'vegetative',
    this.estimatedBiomassG = 0,
    this.estimatedLeafAreaM2 = 0,
    this.leafYellowingScore = 0,
    this.leafDroopScore = 0,
    this.necrosisScore = 0,
    this.waterStress = 0,
    this.nutrientStress = 0,
    this.temperatureStress = 0,
    this.waterStressCat = 'low',
    this.nutrientStressCat = 'low',
    this.temperatureStressCat = 'low',
    this.modelUsed = 'unknown',
    this.firestoreId,
  });

  /// Parse a health check returned from the Flask backend (plain JSON map).
  factory HealthCheck.fromJson(Map<String, dynamic> d) {
    return HealthCheck(
      id:                   d['id']                    as String? ?? '',
      timestamp:            DateTime.tryParse(d['timestamp'] as String? ?? '') ?? DateTime.now(),
      plantType:            d['plant_type']             as String? ?? '',
      ageDays:              (d['age_days'] as num?)?.toInt() ?? 0,
      healthSummary:        d['health_summary']          as String? ?? '',
      recommendedActions:   List<String>.from(d['recommended_actions'] as List? ?? []),
      phenologicalStage:    d['phenological_stage']      as String? ?? 'vegetative',
      estimatedBiomassG:    (d['estimated_biomass_g']    as num?)?.toDouble() ?? 0,
      estimatedLeafAreaM2:  (d['estimated_leaf_area_m2'] as num?)?.toDouble() ?? 0,
      leafYellowingScore:   (d['leaf_yellowing_score']   as num?)?.toDouble() ?? 0,
      leafDroopScore:       (d['leaf_droop_score']       as num?)?.toDouble() ?? 0,
      necrosisScore:        (d['necrosis_score']         as num?)?.toDouble() ?? 0,
      waterStress:          (d['water_stress']           as num?)?.toDouble() ?? 0,
      nutrientStress:       (d['nutrient_stress']        as num?)?.toDouble() ?? 0,
      temperatureStress:    (d['temperature_stress']     as num?)?.toDouble() ?? 0,
      waterStressCat:       d['water_stress_cat']        as String? ?? 'low',
      nutrientStressCat:    d['nutrient_stress_cat']     as String? ?? 'low',
      temperatureStressCat: d['temperature_stress_cat']  as String? ?? 'low',
      modelUsed:            d['model_used']              as String? ?? 'unknown',
    );
  }

  /// Parse the Flask /api/gemini/health response (has success wrapper + extra fields).
  factory HealthCheck.fromApiResponse(Map<String, dynamic> r) {
    return HealthCheck(
      id:                   r['firestore_id']           as String? ?? '',
      timestamp:            DateTime.now(),
      plantType:            r['plant_type']             as String? ?? '',
      ageDays:              (r['age_days'] as num?)?.toInt() ?? 0,
      healthSummary:        r['health_summary']          as String? ?? '',
      recommendedActions:   List<String>.from(r['recommended_actions'] as List? ?? []),
      phenologicalStage:    r['phenological_stage']      as String? ?? 'vegetative',
      estimatedBiomassG:    (r['estimated_biomass_g']    as num?)?.toDouble() ?? 0,
      estimatedLeafAreaM2:  (r['estimated_leaf_area_m2'] as num?)?.toDouble() ?? 0,
      leafYellowingScore:   (r['leaf_yellowing_score']   as num?)?.toDouble() ?? 0,
      leafDroopScore:       (r['leaf_droop_score']       as num?)?.toDouble() ?? 0,
      necrosisScore:        (r['necrosis_score']         as num?)?.toDouble() ?? 0,
      waterStress:          (r['water_stress']           as num?)?.toDouble() ?? 0,
      nutrientStress:       (r['nutrient_stress']        as num?)?.toDouble() ?? 0,
      temperatureStress:    (r['temperature_stress']     as num?)?.toDouble() ?? 0,
      waterStressCat:       r['water_stress_cat']        as String? ?? 'low',
      nutrientStressCat:    r['nutrient_stress_cat']     as String? ?? 'low',
      temperatureStressCat: r['temperature_stress_cat']  as String? ?? 'low',
      modelUsed:            r['model_used']              as String? ?? 'unknown',
      firestoreId:          r['firestore_id']            as String?,
    );
  }

  /// Overall health score 0-1 derived from stress predictions.
  double get overallHealth =>
      (1.0 - (waterStress + nutrientStress + temperatureStress) / 3.0).clamp(0.0, 1.0);

  /// Highest stress category across the three targets.
  String get worstStressCat {
    const order = {'low': 0, 'medium': 1, 'high': 2};
    final cats = [waterStressCat, nutrientStressCat, temperatureStressCat];
    return cats.reduce((a, b) => (order[a] ?? 0) >= (order[b] ?? 0) ? a : b);
  }
}
