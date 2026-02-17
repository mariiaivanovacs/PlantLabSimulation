import 'package:flutter/material.dart';
import '../theme.dart';

class Panel extends StatelessWidget {
  final Widget child;
  final Color? accentLeft;

  const Panel({super.key, required this.child, this.accentLeft});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: C.panel,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: C.border, width: 1),
      ),
      child: accentLeft != null
          ? Row(
              children: [
                Container(
                  width: 4,
                  decoration: BoxDecoration(
                    color: accentLeft,
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(14),
                      bottomLeft: Radius.circular(14),
                    ),
                  ),
                ),
                Expanded(child: Padding(padding: const EdgeInsets.all(14), child: child)),
              ],
            )
          : Padding(padding: const EdgeInsets.all(14), child: child),
    );
  }
}

class PanelTitle extends StatelessWidget {
  final String text;
  final String? badge;
  final Color? badgeColor;

  const PanelTitle(this.text, {super.key, this.badge, this.badgeColor});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Text(text,
              style: const TextStyle(
                  color: C.green, fontSize: 19, fontWeight: FontWeight.w700)),
          if (badge != null) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: (badgeColor ?? C.warn).withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(badge!,
                  style: TextStyle(
                      color: badgeColor ?? C.warn,
                      fontSize: 10,
                      fontWeight: FontWeight.w700)),
            ),
          ],
        ],
      ),
    );
  }
}

class MetricTile extends StatelessWidget {
  final String label;
  final String value;
  final String? unit;
  final bool warn;

  const MetricTile(
      {super.key, required this.label, required this.value, this.unit, this.warn = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: C.bg,
        borderRadius: BorderRadius.circular(8),
        border: warn ? const Border(left: BorderSide(color: C.warn, width: 3)) : null,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Flexible(
            child: Text(label,
                style: const TextStyle(color: C.textMuted, fontSize: 15),
                overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: 8),
          Text.rich(
            TextSpan(children: [
              TextSpan(
                  text: value,
                  style: TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 18,
                      color: warn ? C.warn : C.textPrimary)),
              if (unit != null)
                TextSpan(
                    text: ' $unit',
                    style: const TextStyle(color: C.textMuted, fontSize: 14)),
            ]),
          ),
        ],
      ),
    );
  }
}

class BarGauge extends StatelessWidget {
  final double value; // 0-100
  final Color? color;
  final double height;

  const BarGauge(
      {super.key, required this.value, this.color, this.height = 6});

  @override
  Widget build(BuildContext context) {
    final c = color ??
        (value < 30
            ? C.green
            : value < 60
                ? C.warn
                : C.danger);

    return Stack(
      children: [
        Container(
          height: height,
          decoration: BoxDecoration(
            color: C.bg,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        TweenAnimationBuilder<double>(
          tween: Tween(end: (value / 100).clamp(0, 1)),
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeInOut,
          builder: (context, v, child) => FractionallySizedBox(
            widthFactor: v,
            alignment: Alignment.centerLeft,
            child: Container(
              height: height,
              decoration: BoxDecoration(
                color: c,
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class AnimButton extends StatefulWidget {
  final String label;
  final Color color;
  final VoidCallback onTap;
  final IconData? icon;
  final bool compact;

  const AnimButton({
    super.key,
    required this.label,
    required this.color,
    required this.onTap,
    this.icon,
    this.compact = false,
  });

  @override
  State<AnimButton> createState() => _AnimButtonState();
}

class _AnimButtonState extends State<AnimButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: _pressed ? 0.93 : 1.0,
        duration: const Duration(milliseconds: 100),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: EdgeInsets.symmetric(
            horizontal: widget.compact ? 10 : 14,
            vertical: widget.compact ? 6 : 10,
          ),
          decoration: BoxDecoration(
            color: _pressed ? widget.color.withValues(alpha: 0.6) : widget.color,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.icon != null) ...[
                Icon(widget.icon, size: 14, color: Colors.white),
                const SizedBox(width: 6),
              ],
              Text(widget.label,
                  style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: widget.compact ? 12 : 13,
                      color: Colors.white)),
            ],
          ),
        ),
      ),
    );
  }
}
