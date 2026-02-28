import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme.dart';

// ── Animated cyber gradient background ───────────────────────────────────────

class AnimatedCyberBackground extends StatefulWidget {
  const AnimatedCyberBackground({super.key});

  @override
  State<AnimatedCyberBackground> createState() =>
      _AnimatedCyberBackgroundState();
}

class _AnimatedCyberBackgroundState extends State<AnimatedCyberBackground>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (context, _) {
        final t = _ctrl.value;
        final sweepX = -1.0 + (2.0 * t);
        return Container(
          width: double.infinity,
          height: double.infinity,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                const Color(0xFF0B0F14),
                Color.lerp(
                  const Color(0xFF0F2027),
                  const Color(0xFF0D3018),
                  t,
                )!,
                const Color(0xFF0F1115),
              ],
            ),
          ),
          child: Stack(
            children: [
              // Primary teal orb – sweeps left-right
              Align(
                alignment: Alignment(sweepX, -0.3),
                child: Container(
                  width: 500,
                  height: 500,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        Colors.tealAccent.withValues(alpha: 0.12),
                        Colors.transparent,
                      ],
                    ),
                  ),
                ),
              ),
              // Secondary green orb – drifts in the opposite direction
              Align(
                alignment: Alignment(-sweepX * 0.6, 0.55),
                child: Container(
                  width: 320,
                  height: 320,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        C.green.withValues(alpha: 0.08),
                        Colors.transparent,
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ── App logo — loads assets/logo.png (transparent PNG) with icon fallback ───

class AppLogoImage extends StatelessWidget {
  final double size;
  const AppLogoImage({super.key, this.size = 72});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Image.asset(
        'assets/logo.png',
        width: size,
        height: size,
        fit: BoxFit.contain,
        // Falls back to the icon until the user drops their PNG into assets/
        errorBuilder: (_, __, ___) => Icon(
          Icons.eco,
          color: C.green,
          size: size * 0.65,
        ),
      ),
    );
  }
}

class Panel extends StatelessWidget {
  final Widget child;
  final Color? accentLeft;
  /// When true, renders with BackdropFilter blur + translucent glass surface.
  final bool glass;

  const Panel({super.key, required this.child, this.accentLeft, this.glass = true});

  @override
  Widget build(BuildContext context) {
    const br = BorderRadius.all(Radius.circular(14));

    final innerContent = accentLeft != null
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
        : Padding(padding: const EdgeInsets.all(14), child: child);

    if (glass) {
      return ClipRRect(
        borderRadius: br,
        child: BackdropFilter(
          filter: ui.ImageFilter.blur(sigmaX: 12, sigmaY: 12),
          child: Container(
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.05),
              borderRadius: br,
              border: Border.all(
                color: accentLeft != null
                    ? accentLeft!.withValues(alpha: 0.28)
                    : C.green.withValues(alpha: 0.12),
              ),
              boxShadow: [
                BoxShadow(
                  color: (accentLeft ?? C.green).withValues(alpha: 0.10),
                  blurRadius: 24,
                  spreadRadius: -4,
                ),
              ],
            ),
            child: innerContent,
          ),
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: C.panel,
        borderRadius: br,
        border: Border.all(color: C.border, width: 1),
      ),
      child: innerContent,
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
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: [
          Flexible(
            child: Text(
              text,
              style: GoogleFonts.outfit(
                color: C.green,
                fontSize: 22,
                fontWeight: FontWeight.w700,
                shadows: [
                  Shadow(
                    color: C.green.withValues(alpha: 0.55),
                    blurRadius: 14,
                  ),
                ],
              ),
            ),
          ),
          if (badge != null) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: (badgeColor ?? C.warn).withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(4),
                boxShadow: [
                  BoxShadow(
                    color: (badgeColor ?? C.warn).withValues(alpha: 0.25),
                    blurRadius: 8,
                  ),
                ],
              ),
              child: Text(badge!,
                  style: GoogleFonts.outfit(
                      color: badgeColor ?? C.warn,
                      fontSize: 12,
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
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: warn ? C.warn.withValues(alpha: 0.07) : C.bg,
        borderRadius: BorderRadius.circular(8),
        border: Border(
          left: BorderSide(
            color: warn ? C.warn : Colors.transparent,
            width: 3,
          ),
        ),
        boxShadow: warn
            ? [
                BoxShadow(
                  color: C.warn.withValues(alpha: 0.18),
                  blurRadius: 12,
                  spreadRadius: -2,
                ),
              ]
            : null,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Flexible(
            child: Text(label,
                style: GoogleFonts.outfit(
                    color: warn ? C.warn.withValues(alpha: 0.85) : C.textMuted,
                    fontSize: 15),
                overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: 8),
          Text.rich(
            TextSpan(children: [
              TextSpan(
                  text: value,
                  style: GoogleFonts.outfit(
                      fontWeight: FontWeight.w700,
                      fontSize: 21,
                      color: warn ? C.warn : C.textPrimary,
                      shadows: warn
                          ? [
                              Shadow(
                                color: C.warn.withValues(alpha: 0.45),
                                blurRadius: 8,
                              ),
                            ]
                          : null)),
              if (unit != null)
                TextSpan(
                    text: ' $unit',
                    style: GoogleFonts.outfit(
                        color: C.textMuted, fontSize: 14)),
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
                Icon(widget.icon, size: 16, color: Colors.white),
                const SizedBox(width: 6),
              ],
              Text(widget.label,
                  style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: widget.compact ? 14 : 16,
                      color: Colors.white)),
            ],
          ),
        ),
      ),
    );
  }
}
