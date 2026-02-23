/// A plant registered in the Home Plant mode.
/// Stored server-side in Firestore: users/{uid}/plants/{plantId}
class PlantRecord {
  final String id;
  final String name;         // user-given nickname
  final String identifiedAs; // "tomato" | "lettuce" | "basil"
  final int ageDays;         // days since planting at time of registration
  final DateTime createdAt;

  const PlantRecord({
    required this.id,
    required this.name,
    required this.identifiedAs,
    required this.ageDays,
    required this.createdAt,
  });

  factory PlantRecord.fromJson(Map<String, dynamic> d) {
    return PlantRecord(
      id: d['id'] as String? ?? '',
      name: d['name'] as String? ?? 'My Plant',
      identifiedAs: d['identified_as'] as String? ?? 'plant',
      ageDays: (d['age_days'] as num?)?.toInt() ?? 1,
      createdAt: DateTime.tryParse(d['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'name': name,
        'identified_as': identifiedAs,
        'age_days': ageDays,
      };

  String get emoji {
    switch (identifiedAs) {
      case 'tomato':
        return '🍅';
      case 'lettuce':
        return '🥬';
      case 'basil':
        return '🌿';
      default:
        return '🪴';
    }
  }
}
