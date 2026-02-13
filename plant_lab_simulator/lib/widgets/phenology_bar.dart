import 'package:flutter/material.dart';
import '../theme.dart';
import '../models/plant_state.dart';

class PhenologyBar extends StatelessWidget {
  final GrowthStage current;
  const PhenologyBar({super.key, required this.current});

  @override
  Widget build(BuildContext context) {
    // Show key milestone stages in the bar (skip fruiting to save space)
    final stages = [
      GrowthStage.seed,
      GrowthStage.seedling,
      GrowthStage.vegetative,
      GrowthStage.flowering,
      GrowthStage.mature,
    ];

    return Row(
      children: [
        for (int i = 0; i < stages.length; i++) ...[
          if (i > 0) _connector(stages[i].index <= current.index),
          _stageChip(stages[i], current),
        ],
      ],
    );
  }

  Widget _connector(bool filled) {
    return Expanded(
      child: Container(
        height: 2,
        color: filled ? C.green : C.border,
      ),
    );
  }

  Widget _stageChip(GrowthStage stage, GrowthStage current) {
    final isDead = current == GrowthStage.dead;
    final isDone = stage.index < current.index;
    final isActive = stage == current ||
        (isDead && stage == GrowthStage.mature);

    Color bg = C.bg;
    Color fg = C.textMuted;
    if (isDead && stage == GrowthStage.mature) {
      bg = C.dangerDim;
      fg = C.dangerSoft;
    } else if (isActive) {
      bg = C.green;
      fg = C.greenDeep;
    } else if (isDone) {
      bg = C.greenDark;
      fg = const Color(0xFF6EE7B7);
    }

    String label;
    switch (stage) {
      case GrowthStage.seed:
        label = 'Seed';
        break;
      case GrowthStage.seedling:
        label = 'Sdlg';
        break;
      case GrowthStage.vegetative:
        label = 'Veg';
        break;
      case GrowthStage.flowering:
        label = 'Flwr';
        break;
      case GrowthStage.fruiting:
        label = 'Fruit';
        break;
      case GrowthStage.mature:
        label = isDead ? '☠ Dead' : 'Mature';
        break;
      case GrowthStage.dead:
        label = 'Dead';
        break;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label,
          style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: fg)),
    );
  }
}
