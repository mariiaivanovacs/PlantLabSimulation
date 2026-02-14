import 'package:flutter/material.dart';

/// A simple sparkline chart that draws the last N values.
class Sparkline extends StatelessWidget {
  final List<double> data;
  final double minY;
  final double maxY;
  final Color color;
  final double height;

  const Sparkline({
    super.key,
    required this.data,
    required this.minY,
    required this.maxY,
    required this.color,
    this.height = 50,
  });

  @override
  Widget build(BuildContext context) {
    if (data.length < 2) return SizedBox(height: height);

    return SizedBox(
      height: height,
      child: CustomPaint(
        painter: _SparkPainter(
          data: data,
          minY: minY,
          maxY: maxY,
          color: color,
        ),
        size: Size.infinite,
      ),
    );
  }
}

class _SparkPainter extends CustomPainter {
  final List<double> data;
  final double minY, maxY;
  final Color color;

  _SparkPainter({
    required this.data, required this.minY, required this.maxY,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (data.length < 2) return;

    final range = maxY - minY;
    if (range == 0) return;

    double yOf(double v) => size.height - ((v - minY) / range * size.height).clamp(0, size.height);
    double xOf(int i) => i / (data.length - 1) * size.width;

    // Fill gradient
    final path = Path()..moveTo(xOf(0), yOf(data[0]));
    for (int i = 1; i < data.length; i++) {
      path.lineTo(xOf(i), yOf(data[i]));
    }
    final fillPath = Path.from(path)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();

    canvas.drawPath(
      fillPath,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [color.withValues(alpha: 0.25), color.withValues(alpha: 0)],
        ).createShader(Rect.fromLTWH(0, 0, size.width, size.height)),
    );

    // Line
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..strokeWidth = 1.5
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round,
    );

    // Current value dot
    canvas.drawCircle(
      Offset(xOf(data.length - 1), yOf(data.last)),
      3,
      Paint()..color = color,
    );
  }

  @override
  bool shouldRepaint(covariant _SparkPainter old) =>
      data.length != old.data.length || (data.isNotEmpty && data.last != old.data.last);
}
