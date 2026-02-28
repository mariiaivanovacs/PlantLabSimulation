import 'dart:ui' as ui;
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme.dart';
import '../services/auth_service.dart';
import '../widgets/shared.dart';
import 'dashboard.dart';
import 'home/home_health_screen.dart';

/// First screen after login — user picks Enterprise or Home Plant mode.
class ModeSelectionScreen extends StatelessWidget {
  const ModeSelectionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: C.bg,
      body: Stack(
        children: [
          // Animated gradient background
          const AnimatedCyberBackground(),

          // Dark overlay
          Container(
            width: double.infinity,
            height: double.infinity,
            color: Colors.black.withValues(alpha: 0.35),
          ),

          // Content
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(32),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // Logo
                    const AppLogoImage(size: 80),
                    const SizedBox(height: 16),
                    Text(
                      'Plant Lab',
                      style: GoogleFonts.outfit(
                        color: C.green,
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.2,
                        shadows: [
                          Shadow(
                            color: C.green.withValues(alpha: 0.7),
                            blurRadius: 18,
                          ),
                          Shadow(
                            color: C.green.withValues(alpha: 0.3),
                            blurRadius: 36,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'How are you using Plant Lab today?',
                      style: GoogleFonts.outfit(
                        color: C.textMuted,
                        fontSize: 15,
                      ),
                    ),
                    const SizedBox(height: 40),

                    // ── Mode cards ─────────────────────────────────────────
                    LayoutBuilder(
                      builder: (ctx, constraints) {
                        final wide = constraints.maxWidth > 440;
                        final cards = [
                          _ModeCard(
                            icon: Icons.science,
                            iconColor: C.green,
                            title: 'Enterprise',
                            subtitle:
                                'Full physics simulation,\nday/night cycles, agent control',
                            onTap: () => Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(
                                  builder: (_) => const DashboardScreen()),
                            ),
                          ),
                          _ModeCard(
                            icon: Icons.home_outlined,
                            iconColor: C.info,
                            title: 'Home Plant',
                            subtitle:
                                'AI health checks for your\nreal plants at home',
                            onTap: () => Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(
                                  builder: (_) => const HomeHealthScreen()),
                            ),
                          ),
                        ];

                        return wide
                            ? Row(
                                children: cards
                                    .map((c) => Expanded(
                                        child: Padding(
                                            padding: const EdgeInsets.symmetric(
                                                horizontal: 8),
                                            child: c)))
                                    .toList(),
                              )
                            : Column(
                                children: cards
                                    .map((c) => Padding(
                                        padding:
                                            const EdgeInsets.only(bottom: 16),
                                        child: c))
                                    .toList(),
                              );
                      },
                    ),

                    const SizedBox(height: 40),
                    TextButton.icon(
                      onPressed: () => AuthService.instance.signOut(),
                      icon: const Icon(Icons.logout,
                          color: C.textMuted, size: 16),
                      label: Text(
                        'Sign out',
                        style: GoogleFonts.outfit(
                          color: C.textMuted,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ModeCard extends StatefulWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _ModeCard({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  State<_ModeCard> createState() => _ModeCardState();
}

class _ModeCardState extends State<_ModeCard> {
  bool _hovered = false;

  static const Duration _hoverAnimDuration = Duration(milliseconds: 220);

  @override
  Widget build(BuildContext context) {
    // Responsive: auto-detect "compact" (phone) layout and scale sizes
    final width = MediaQuery.of(context).size.width;
    final isCompact = width < 420; // tweak threshold as needed

    final padding = isCompact ? 16.0 : 24.0;
    final iconSize = isCompact ? 48.0 : 52.0; // glyph size (foreground)
    final titleSize = isCompact ? 20.0 : 18.0; // text a bit bigger on mobile
    final subtitleSize = isCompact ? 14.0 : 13.0;

    // Hover-driven transforms
    final double cardScale = _hovered ? 1.025 : 1.0;
    final double bgIconScale = _hovered ? 1.12 : 1.0;
    final double bgIconOpacity = _hovered ? 0.22 : 0.16;
    final double bgDarken = _hovered ? 0.45 : 0.36;

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedScale(
          scale: cardScale,
          duration: _hoverAnimDuration,
          curve: Curves.easeOutCubic,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: Stack(
              children: [
                // Background blurry / darkened icon (behind content)
                Positioned.fill(
                  child: AnimatedOpacity(
                    duration: _hoverAnimDuration,
                    opacity: bgIconOpacity,
                    child: Align(
                      alignment: Alignment.topRight,
                      child: Padding(
                        padding: EdgeInsets.only(
                            right: isCompact ? 8 : 16, top: isCompact ? 4 : 8),
                        child: TweenAnimationBuilder<double>(
                          tween: Tween(begin: 1.0, end: bgIconScale),
                          duration: _hoverAnimDuration,
                          curve: Curves.easeOut,
                          builder: (context, scaleFactor, child) {
                            return Transform.scale(
                              scale: scaleFactor,
                              origin: Offset(20, 0),
                              child: Icon(
                                widget.icon,
                                size: (isCompact ? 120 : 160) * scaleFactor,
                                color: widget.iconColor.withOpacity(0.18),
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                  ),
                ),

                // Frosted glass + content
                BackdropFilter(
                  filter: ui.ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                  child: AnimatedContainer(
                    duration: _hoverAnimDuration,
                    padding: EdgeInsets.all(padding),
                    constraints:
                        BoxConstraints(minHeight: isCompact ? 110 : 160),
                    decoration: BoxDecoration(
                      color: _hovered
                          ? Colors.white.withValues(alpha: 0.10)
                          : Colors.white.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: _hovered
                            ? widget.iconColor.withValues(alpha: 0.5)
                            : Colors.white.withValues(alpha: 0.10),
                        width: 1,
                      ),
                      boxShadow: _hovered
                          ? [
                              BoxShadow(
                                color: widget.iconColor.withValues(alpha: 0.22),
                                blurRadius: 28,
                                spreadRadius: 0,
                              ),
                            ]
                          : [],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Foreground small glyph (keeps original look)
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Small circular icon background to contrast text
                            Container(
                              width: iconSize,
                              height: iconSize,
                              decoration: BoxDecoration(
                                color: widget.iconColor.withValues(alpha: 0.12),
                                shape: BoxShape.circle,
                                boxShadow: [
                                  BoxShadow(
                                    color:
                                        widget.iconColor.withValues(alpha: 0.04),
                                    blurRadius: 6,
                                  ),
                                ],
                              ),
                              child: Icon(
                                widget.icon,
                                color: widget.iconColor,
                                size: iconSize * 0.52,
                              ),
                            ),
                            const SizedBox(width: 12),
                            // Title + subtitle stacked
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    widget.title,
                                    style: GoogleFonts.outfit(
                                      color: C.textPrimary,
                                      fontSize: titleSize,
                                      fontWeight: FontWeight.w700,
                                      shadows: [
                                        Shadow(
                                          color: widget.iconColor
                                              .withValues(alpha: 0.45),
                                          blurRadius: 12,
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  Text(
                                    widget.subtitle,
                                    style: GoogleFonts.outfit(
                                      color: C.textMuted,
                                      fontSize: subtitleSize,
                                      height: 1.35,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),

                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Text(
                              'Open',
                              style: GoogleFonts.outfit(
                                color: widget.iconColor,
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(width: 4),
                            Icon(Icons.arrow_forward,
                                color: widget.iconColor, size: 14),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Image-based glyph widget for mode selection.
/// Maps `kind` to asset paths: 'enterprise' -> gear icon, 'home' -> plant icon.
/// If `kind` contains '/', treats it as a direct asset path.
class _ModeGlyph extends StatelessWidget {
  final double size;
  final String kind; // 'enterprise', 'home', or direct asset path

  const _ModeGlyph({
    required this.size,
    required this.kind,
  });

  /// Resolve asset path from kind name or direct path.
  static String assetForKind(String kind) {
    if (kind.contains('/')) {
      // Direct asset path provided (e.g., 'assets/tomato.png')
      return kind;
    }
    final lower = kind.toLowerCase();
    if (lower.contains('enterprise')) return 'assets/enterprise.png';
    if (lower.contains('home')) return 'assets/home_plant.png';
    return 'assets/logo.png'; // fallback
  }

  String _assetForKind() => assetForKind(kind);

  @override
  Widget build(BuildContext context) {
    final asset = _assetForKind();

    return SizedBox(
      width: size,
      height: size,
      child: Image.asset(
        asset,
        width: size,
        height: size,
        fit: BoxFit.contain,
        errorBuilder: (ctx, err, stack) {
          // Fallback icon if asset missing
          return Container(
            width: size,
            height: size,
            alignment: Alignment.center,
            child: Icon(
              Icons.image_not_supported,
              size: size * 0.6,
              color: Colors.grey,
            ),
          );
        },
      ),
    );
  }
}