// Enums used by the dashboard — backed by Flask backend values.

/// Growth stage — maps to the backend PhenologicalStage enum.
enum GrowthStage {
  seed,
  seedling,
  vegetative,
  flowering,
  fruiting,
  mature,
  dead;

  /// Parse from the backend string value (e.g. "SEEDLING" → GrowthStage.seedling).
  static GrowthStage fromString(String? s) {
    switch ((s ?? '').toUpperCase()) {
      case 'SEED':
        return GrowthStage.seed;
      case 'SEEDLING':
        return GrowthStage.seedling;
      case 'VEGETATIVE':
        return GrowthStage.vegetative;
      case 'FLOWERING':
        return GrowthStage.flowering;
      case 'FRUITING':
        return GrowthStage.fruiting;
      case 'MATURE':
        return GrowthStage.mature;
      case 'DEAD':
        return GrowthStage.dead;
      default:
        return GrowthStage.seed;
    }
  }

  String get label {
    switch (this) {
      case GrowthStage.seed:
        return 'Seed';
      case GrowthStage.seedling:
        return 'Seedling';
      case GrowthStage.vegetative:
        return 'Vegetative';
      case GrowthStage.flowering:
        return 'Flowering';
      case GrowthStage.fruiting:
        return 'Fruiting';
      case GrowthStage.mature:
        return 'Mature';
      case GrowthStage.dead:
        return 'Dead';
    }
  }
}

/// Action types — maps to backend ToolType strings.
enum ActionType {
  water,
  light,
  nutrient,
  hvac,
  humidity,
  ventilation;

  String get backendName {
    switch (this) {
      case ActionType.water:
        return 'watering';
      case ActionType.light:
        return 'lighting';
      case ActionType.nutrient:
        return 'nutrients';
      case ActionType.hvac:
        return 'hvac';
      case ActionType.humidity:
        return 'humidity';
      case ActionType.ventilation:
        return 'ventilation';
    }
  }
}
