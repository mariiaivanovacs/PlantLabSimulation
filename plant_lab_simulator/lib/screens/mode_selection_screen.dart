import 'dart:ui' as ui;

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

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedScale(
          scale: _hovered ? 1.025 : 1.0,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: BackdropFilter(
              filter: ui.ImageFilter.blur(sigmaX: 12, sigmaY: 12),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.all(24),
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
                    Icon(widget.icon, color: widget.iconColor, size: 36),
                    const SizedBox(height: 16),
                    Text(
                      widget.title,
                      style: GoogleFonts.outfit(
                        color: C.textPrimary,
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        shadows: [
                          Shadow(
                            color: widget.iconColor.withValues(alpha: 0.55),
                            blurRadius: 14,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      widget.subtitle,
                      style: GoogleFonts.outfit(
                        color: C.textMuted,
                        fontSize: 13,
                        height: 1.5,
                      ),
                    ),
                    const SizedBox(height: 16),
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
          ),
        ),
      ),
    );
  }
}
