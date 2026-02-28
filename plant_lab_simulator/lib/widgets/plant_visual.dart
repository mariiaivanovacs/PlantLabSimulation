import 'package:flutter/material.dart';
import '../theme.dart';

class PlantVisual extends StatelessWidget {
  final Map<String, dynamic> state;

  const PlantVisual({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final biomass = (state['biomass'] ?? 0).toDouble();
    final damage = (state['cumulative_damage'] ?? 0).toDouble();
    final alive = state['is_alive'] ?? false;

    final scale = (biomass / 150).clamp(0.3, 1.0);
    final color = Color.lerp(C.greenSoft, Colors.brown, damage / 100)!;

    return SizedBox(
      height: 120,
      child: CustomPaint(
        painter: _PlantPainter(scale, color, alive),
      ),
    );
  }
}

class _PlantPainter extends CustomPainter {
  final double scale;
  final Color color;
  final bool alive;

  _PlantPainter(this.scale, this.color, this.alive);

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final bottom = size.height;

    final stemHeight = 80 * scale;

    final stemPaint = Paint()
      ..color = color
      ..strokeWidth = 4;

    canvas.drawLine(
      Offset(cx, bottom),
      Offset(cx, bottom - stemHeight),
      stemPaint,
    );

    if (alive) {
      canvas.drawCircle(
        Offset(cx, bottom - stemHeight),
        6 * scale,
        Paint()..color = color,
      );
    } else {
      final tp = TextPainter(
        text: const TextSpan(text: '☠', style: TextStyle(fontSize: 20)),
        textDirection: TextDirection.ltr,
      )..layout();

      tp.paint(canvas, Offset(cx - 10, bottom - stemHeight - 20));
    }
  }

  @override
  bool shouldRepaint(covariant _PlantPainter old) =>
      scale != old.scale || color != old.color || alive != old.alive;
}