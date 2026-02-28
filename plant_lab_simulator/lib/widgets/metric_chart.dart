import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme.dart';

/// A line chart widget that draws multiple named series with axis labels and legend.
class MetricChart extends StatelessWidget {
  final String title;
  final List<ChartSeries> series;
  final double height;
  final String? yUnit;

  const MetricChart({
    super.key,
    required this.title,
    required this.series,
    this.height = 180,
    this.yUnit,
  });

  @override
  Widget build(BuildContext context) {
    final nonEmpty = series.where((s) => s.data.length >= 2).toList();
    if (nonEmpty.isEmpty) {
      return SizedBox(
        height: height,
        child: Center(
          child: Text('No data for $title',
              style: GoogleFonts.outfit(color: C.textMuted, fontSize: 12)),
        ),
      );
    }

    // Compute global Y range across all series
    double globalMin = double.infinity;
    double globalMax = double.negativeInfinity;
    for (final s in nonEmpty) {
      for (final v in s.data) {
        if (v < globalMin) globalMin = v;
        if (v > globalMax) globalMax = v;
      }
    }
    // Add padding
    final range = globalMax - globalMin;
    if (range < 1e-9) {
      globalMin -= 1;
      globalMax += 1;
    } else {
      globalMin -= range * 0.05;
      globalMax += range * 0.05;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Title
        Text(title,
            style: GoogleFonts.outfit(
                color: C.green,
                fontSize: 14,
                fontWeight: FontWeight.w700,
                shadows: [
                  Shadow(
                    color: C.green.withValues(alpha: 0.5),
                    blurRadius: 10,
                  ),
                ])),
        const SizedBox(height: 8),
        // Legend
        Wrap(
          spacing: 12,
          runSpacing: 4,
          children: nonEmpty
              .map((s) => Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                          width: 10,
                          height: 3,
                          decoration: BoxDecoration(
                              color: s.color,
                              borderRadius: BorderRadius.circular(1))),
                      const SizedBox(width: 4),
                      Text(s.label,
                          style: GoogleFonts.outfit(
                              color: C.textMuted, fontSize: 10)),
                    ],
                  ))
              .toList(),
        ),
        const SizedBox(height: 8),
        // Chart area with Y-axis labels
        SizedBox(
          height: height,
          child: Row(
            children: [
              // Y-axis labels
              SizedBox(
                width: 44,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(_fmt(globalMax),
                        style:
                            const TextStyle(color: C.textDim, fontSize: 9)),
                    if (yUnit != null)
                      Text(yUnit!,
                          style:
                              const TextStyle(color: C.textDim, fontSize: 8)),
                    Text(_fmt(globalMin),
                        style:
                            const TextStyle(color: C.textDim, fontSize: 9)),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              // Chart
              Expanded(
                child: CustomPaint(
                  painter: _MultiSeriesPainter(
                    series: nonEmpty,
                    minY: globalMin,
                    maxY: globalMax,
                  ),
                  size: Size.infinite,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  String _fmt(double v) {
    if (v.abs() >= 1000) return v.toStringAsFixed(0);
    if (v.abs() >= 10) return v.toStringAsFixed(1);
    if (v.abs() >= 1) return v.toStringAsFixed(2);
    return v.toStringAsFixed(4);
  }
}

class ChartSeries {
  final String label;
  final List<double> data;
  final Color color;

  const ChartSeries({
    required this.label,
    required this.data,
    required this.color,
  });
}

class _MultiSeriesPainter extends CustomPainter {
  final List<ChartSeries> series;
  final double minY, maxY;

  _MultiSeriesPainter({
    required this.series,
    required this.minY,
    required this.maxY,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final range = maxY - minY;
    if (range == 0) return;

    // Draw grid lines
    final gridPaint = Paint()
      ..color = const Color(0xFF243428).withValues(alpha: 0.5)
      ..strokeWidth = 0.5;
    for (int i = 0; i <= 4; i++) {
      final y = size.height * i / 4;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    // Draw each series
    for (final s in series) {
      if (s.data.length < 2) continue;

      final maxPts = min(s.data.length, 500);
      final step = s.data.length > 500 ? s.data.length / 500 : 1.0;

      double yOf(double v) =>
          size.height - ((v - minY) / range * size.height).clamp(0, size.height);
      double xOf(int i) => i / (maxPts - 1) * size.width;

      // Build path
      final path = Path();
      path.moveTo(xOf(0), yOf(s.data[0]));
      for (int i = 1; i < maxPts; i++) {
        final idx = (i * step).round().clamp(0, s.data.length - 1);
        path.lineTo(xOf(i), yOf(s.data[idx]));
      }

      // Fill gradient
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
            colors: [
              s.color.withValues(alpha: 0.15),
              s.color.withValues(alpha: 0.0)
            ],
          ).createShader(Rect.fromLTWH(0, 0, size.width, size.height)),
      );

      // Line
      canvas.drawPath(
        path,
        Paint()
          ..color = s.color
          ..strokeWidth = 1.5
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round,
      );

      // Current value dot
      final lastIdx = (((maxPts - 1) * step).round()).clamp(0, s.data.length - 1);
      canvas.drawCircle(
        Offset(xOf(maxPts - 1), yOf(s.data[lastIdx])),
        3,
        Paint()..color = s.color,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _MultiSeriesPainter old) => true;
}
