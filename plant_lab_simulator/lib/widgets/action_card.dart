import 'package:flutter/material.dart';
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
          Text(label, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text(description, style: const TextStyle(color: C.textMuted)),
          const SizedBox(height: 8),
          ElevatedButton(
            onPressed: () => _execute(context),
            child: const Text("Execute"),
          )
        ],
      ),
    );
  }
}
