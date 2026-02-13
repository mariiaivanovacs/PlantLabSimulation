import 'package:flutter/material.dart';
import 'theme.dart';
import 'screens/dashboard.dart';

void main() {
  runApp(const PlantLabApp());
}

class PlantLabApp extends StatelessWidget {
  const PlantLabApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Plant Lab Simulator',
      debugShowCheckedModeBanner: false,
      theme: PlantLabTheme.darkTheme,
      home: const DashboardScreen(),
    );
  }
}
