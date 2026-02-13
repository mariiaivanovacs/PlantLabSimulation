// Plant state model for backend-powered dashboard

enum GrowthStage {
  seed,
  seedling,
  vegetative,
  flowering,
  fruiting,
  mature,
  dead;

  static GrowthStage fromIndex(int index) {
    return GrowthStage.values[index.clamp(0, GrowthStage.values.length - 1)];
  }
}

enum ActionType {
  water,
  light,
  nutrient,
  hvac,
  humidity,
  ventilation;

  /// Maps to the backend ToolType string value
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

class PlantState {
  final int day;
  final int hour;
  final double biomass;
  final double leafArea;
  final double thermalTime;
  final double cumulativeDamage;
  final bool isAlive;

  // Environmental state
  final double soilWater;
  final double airTemp;
  final double soilTemp;
  final double relativeHumidity;
  final double lightPAR;
  final double vpd;
  final double soilN;
  final double soilEC;

  // Stress factors
  final double waterStress;
  final double tempStress;
  final double nutrientStress;

  // Growth stage
  final int stage;

  const PlantState({
    this.day = 0,
    this.hour = 0,
    this.biomass = 0.5,
    this.leafArea = 0.001,
    this.thermalTime = 0,
    this.cumulativeDamage = 0,
    this.isAlive = true,
    this.soilWater = 35,
    this.airTemp = 25,
    this.soilTemp = 22,
    this.relativeHumidity = 60,
    this.lightPAR = 0,
    this.vpd = 1.0,
    this.soilN = 150,
    this.soilEC = 1.5,
    this.waterStress = 0,
    this.tempStress = 0,
    this.nutrientStress = 0,
    this.stage = 0,
  });

  String get stageLabel {
    const labels = [
      'Seed',
      'Seedling',
      'Vegetative',
      'Flowering',
      'Fruiting',
      'Mature',
      'Dead',
    ];
    return labels[stage.clamp(0, labels.length - 1)];
  }
}


