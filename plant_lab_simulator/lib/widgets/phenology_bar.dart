import 'package:flutter/material.dart';
import '../theme.dart';

class PhenologyBar extends StatelessWidget {
  final String stage;

  const PhenologyBar({super.key, required this.stage});

  static const stages = ['seed', 'seedling', 'vegetative', 'mature', 'dead'];

  @override
  Widget build(BuildContext context) {
    final currentIndex = stages.indexOf(stage);

    return Row(
      children: stages.map((s) {
        final i = stages.indexOf(s);
        final active = i <= currentIndex;

        return Expanded(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 2),
            height: 8,
            decoration: BoxDecoration(
              color: active ? C.green : C.border,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
        );
      }).toList(),
    );
  }
}
