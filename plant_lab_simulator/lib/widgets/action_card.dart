import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme.dart';
import '../services/api_client.dart';
import 'shared.dart';

class ActionCard extends StatelessWidget {
  final String toolType;
  final Map<String, dynamic> params;
  final String label;
  final String description;

  const ActionCard({
    super.key,
    required this.toolType,
    required this.params,
    required this.label,
    required this.description,
  });

  Future<void> _execute(BuildContext context) async {
    final api = ApiClient();
    try {
      final res = await api.executeAction(toolType, params);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res.success ? "Executed" : "Failed"),
          backgroundColor: res.success ? C.green : C.danger,
        ),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Error: $e"),
          backgroundColor: C.danger,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: GoogleFonts.outfit(
                  fontWeight: FontWeight.w700,
                  fontSize: 17,
                  color: C.textPrimary,
                  shadows: [
                    Shadow(
                      color: C.green.withValues(alpha: 0.4),
                      blurRadius: 10,
                    ),
                  ])),
          const SizedBox(height: 8),
          Text(description,
              style: GoogleFonts.outfit(color: C.textMuted, fontSize: 14)),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: () => _execute(context),
            child: Text("Execute",
                style: GoogleFonts.outfit(
                    fontSize: 15, fontWeight: FontWeight.w600)),
          )
        ],
      ),
    );
  }
}
