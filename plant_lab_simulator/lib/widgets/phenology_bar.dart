import 'package:flutter/material.dart';
import '../theme.dart';

class PhenologyBar extends StatelessWidget {
  final String stage;

  const PhenologyBar({super.key, required this.stage});

  static const stages = ['seed', 'seedling', 'vegetative', 'mature', 'dead'];

  @override
  Widget build(BuildContext context) {
    final currentIndex = stages.indexOf(stage);
    final isDead = stage == 'dead';

    return Row(
      children: stages.map((s) {
        final i = stages.indexOf(s);
        final active = i <= currentIndex;
        final segmentColor = active
            ? (isDead ? C.danger : C.green)
            : C.border;

        return Expanded(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 2),
            height: 10,
            decoration: BoxDecoration(
              color: segmentColor,
              borderRadius: BorderRadius.circular(5),
              boxShadow: active
                  ? [
                      BoxShadow(
                        color: segmentColor.withValues(alpha: 0.65),
                        blurRadius: 8,
                        spreadRadius: 1,
                      ),
                    ]
                  : null,
            ),
          ),
        );
      }).toList(),
    );
  }
}
