import 'package:flutter/material.dart';

class C {
  // Core palette
  static const green = Color(0xFF3FA34D);
  static const greenSoft = Color(0xFF6FCF97);
  static const greenDark = Color(0xFF064E3B);
  static const greenDeep = Color(0xFF052E16);
  static const olive = Color(0xFF6B8E23);
  static const soil = Color(0xFF5A3E2B);

  // Backgrounds
  static const bg = Color(0xFF0F1115);
  static const panel = Color(0xFF151821);
  static const surface = Color(0xFF151821);
  static const panelAlt = Color(0xFF1A1F2B);
  static const border = Color(0xFF243428);
  static const cardBg = Color(0xFF0D0F12);

  // Status
  static const warn = Color(0xFFF59E0B);
  static const warnDim = Color(0xFF92400E);
  static const danger = Color(0xFFB91C1C);
  static const dangerSoft = Color(0xFFFCA5A5);
  static const dangerDim = Color(0xFF7F1D1D);
  static const info = Color(0xFF2563EB);
  static const infoDim = Color(0xFF1E3A5F);

  // Text
  static const textPrimary = Color(0xFFE5E7EB);
  static const textMuted = Color(0xFF9CA3AF);
  static const textDim = Color(0xFF6B7280);

  // Tool colors
  static const water = Color(0xFF3B82F6);
  static const light = Color(0xFFFBBF24);
  static const nutrient = Color(0xFF8B5CF6);
  static const hvac = Color(0xFFEF4444);
  static const humidity = Color(0xFF06B6D4);
  static const vent = Color(0xFF10B981);
}

class PlantLabTheme {
  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: C.bg,
      textTheme: ThemeData.dark().textTheme.apply(
        bodyColor: C.textPrimary,
        displayColor: C.textPrimary,
      ),
      colorScheme: const ColorScheme.dark(
        primary: C.green,
        onPrimary: Colors.white,
        secondary: C.greenSoft,
        onSecondary: Colors.white,
        surface: C.panel,
        error: C.danger,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          foregroundColor: Colors.white,
          textStyle: const TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 15,
            color: Colors.white,
          ),
        ),
      ),
    );
  }
}
