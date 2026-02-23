// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:async';
import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../theme.dart';
import '../../services/firestore_service.dart';
import '../../services/gemini_service.dart';
import '../../models/plant_record.dart';
import 'home_health_screen.dart';

/// Two-step wizard for registering a new plant in Home Plant mode.
///
/// Step 1 — Identify: upload an image OR type the plant name.
///           Gemini returns "tomato" | "lettuce" | "basil" | "none".
///           If "none" the user is asked to try again.
///
/// Step 2 — Age + nickname: how long it's been growing, give it a name.
///           Creates the Firestore document and navigates to HomeHealthScreen.
class PlantOnboardingScreen extends StatefulWidget {
  /// When true the screen is navigated to as the very first Home Plant screen
  /// (replace). When false it's pushed on top (e.g. "Add another plant").
  final bool isFirstPlant;

  const PlantOnboardingScreen({super.key, this.isFirstPlant = true});

  @override
  State<PlantOnboardingScreen> createState() => _PlantOnboardingScreenState();
}

class _PlantOnboardingScreenState extends State<PlantOnboardingScreen> {
  // ── shared state ────────────────────────────────────────────────────────────
  int _step = 0; // 0 = identify, 1 = age+name

  // ── step 0 ──────────────────────────────────────────────────────────────────
  Uint8List? _imageBytes;
  String? _imageB64;
  final _nameCtrl = TextEditingController();
  bool _identifying = false;
  String? _identifyError;

  // ── step 1 ──────────────────────────────────────────────────────────────────
  String _identified = '';     // set after step 0 succeeds
  int _ageDays = 1;
  final _nickCtrl = TextEditingController();
  bool _saving = false;
  String? _saveError;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _nickCtrl.dispose();
    super.dispose();
  }

  // ── image pick (dart:html, web only) ────────────────────────────────────────

  Future<void> _pickImage() async {
    final input = html.FileUploadInputElement()
      ..accept = 'image/*'
      ..click();

    await input.onChange.first;
    final file = input.files?.first;
    if (file == null) return;

    final reader = html.FileReader();
    reader.readAsArrayBuffer(file);
    await reader.onLoad.first;

    final bytes = Uint8List.fromList(reader.result as List<int>);
    setState(() {
      _imageBytes = bytes;
      _imageB64 = base64Encode(bytes);
      _identifyError = null;
    });
  }

  // ── step 0: identify ────────────────────────────────────────────────────────

  Future<void> _identify() async {
    final hasImage = _imageB64 != null;
    final hasName = _nameCtrl.text.trim().isNotEmpty;
    if (!hasImage && !hasName) {
      setState(() =>
          _identifyError = 'Please upload a photo or type the plant name.');
      return;
    }

    setState(() {
      _identifying = true;
      _identifyError = null;
    });

    try {
      final result = await GeminiService.instance.identifyPlant(
        imageB64: _imageB64,
        plantName: hasName ? _nameCtrl.text.trim() : null,
      );

      if (result == 'none') {
        setState(() {
          _identifying = false;
          _identifyError =
              'We only support tomato, lettuce, and sweet basil.\n'
              'Please try a clearer photo or type the name again.';
        });
        return;
      }

      // Success — move to step 1
      setState(() {
        _identified = result;
        _nickCtrl.text = _defaultNickname(result);
        _identifying = false;
        _step = 1;
      });
    } catch (e) {
      setState(() {
        _identifying = false;
        _identifyError = e.toString();
      });
    }
  }

  // ── step 1: save ─────────────────────────────────────────────────────────────

  Future<void> _save() async {
    final nick = _nickCtrl.text.trim();
    if (nick.isEmpty) {
      setState(() => _saveError = 'Please give your plant a name.');
      return;
    }

    setState(() {
      _saving = true;
      _saveError = null;
    });

    try {
      final plant = await FirestoreService.instance.addPlant(
        name: nick,
        identifiedAs: _identified,
        ageDays: _ageDays,
      );

      if (!mounted) return;

      if (widget.isFirstPlant) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
              builder: (_) => HomeHealthScreen(initialPlant: plant)),
        );
      } else {
        Navigator.pop(context, plant); // return to caller
      }
    } catch (e) {
      setState(() {
        _saving = false;
        _saveError = e.toString();
      });
    }
  }

  // ── helpers ──────────────────────────────────────────────────────────────────

  String _defaultNickname(String identified) {
    switch (identified) {
      case 'tomato':
        return 'My Tomato';
      case 'lettuce':
        return 'My Lettuce';
      case 'basil':
        return 'My Basil';
      default:
        return 'My Plant';
    }
  }

  String _plantEmoji(String id) {
    switch (id) {
      case 'tomato':
        return '🍅';
      case 'lettuce':
        return '🥬';
      case 'basil':
        return '🌿';
      default:
        return '🪴';
    }
  }

  // ── build ────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: C.bg,
      appBar: AppBar(
        backgroundColor: C.bg,
        leading: _step == 1
            ? IconButton(
                icon: const Icon(Icons.arrow_back, color: C.textMuted),
                onPressed: () => setState(() => _step = 0),
              )
            : (!widget.isFirstPlant
                ? IconButton(
                    icon: const Icon(Icons.arrow_back, color: C.textMuted),
                    onPressed: () => Navigator.pop(context),
                  )
                : null),
        title: Text(
          _step == 0 ? 'Identify Your Plant' : 'Set Up Your Plant',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        elevation: 0,
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: _step == 0 ? _buildIdentifyStep() : _buildAgeStep(),
          ),
        ),
      ),
    );
  }

  // ── Step 0 ───────────────────────────────────────────────────────────────────

  Widget _buildIdentifyStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Upload a photo of your plant, or type its name below.',
          style: TextStyle(color: C.textMuted, fontSize: 14),
        ),
        const SizedBox(height: 20),

        // ── Image drop zone ──────────────────────────────────────────────────
        GestureDetector(
          onTap: _identifying ? null : _pickImage,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            height: 180,
            decoration: BoxDecoration(
              color: C.panelAlt,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                  color: _imageBytes != null
                      ? C.green.withValues(alpha: 0.5)
                      : C.border,
                  width: _imageBytes != null ? 1.5 : 1),
            ),
            child: _imageBytes != null
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(11),
                    child: Image.memory(_imageBytes!, fit: BoxFit.cover,
                        width: double.infinity),
                  )
                : Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: const [
                      Icon(Icons.add_photo_alternate_outlined,
                          color: C.textMuted, size: 40),
                      SizedBox(height: 10),
                      Text('Tap to upload a photo',
                          style:
                              TextStyle(color: C.textMuted, fontSize: 13)),
                    ],
                  ),
          ),
        ),

        if (_imageBytes != null) ...[
          const SizedBox(height: 6),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: () => setState(() {
                _imageBytes = null;
                _imageB64 = null;
              }),
              child: const Text('Remove photo',
                  style: TextStyle(color: C.danger, fontSize: 12)),
            ),
          ),
        ],

        const SizedBox(height: 20),
        const Row(children: [
          Expanded(child: Divider(color: C.border)),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: Text('OR', style: TextStyle(color: C.textMuted, fontSize: 12)),
          ),
          Expanded(child: Divider(color: C.border)),
        ]),
        const SizedBox(height: 20),

        // ── Text name input ──────────────────────────────────────────────────
        TextField(
          controller: _nameCtrl,
          style: const TextStyle(fontSize: 14),
          decoration: InputDecoration(
            hintText: 'e.g. tomato, lettuce, basil…',
            hintStyle: const TextStyle(color: C.textMuted),
            filled: true,
            fillColor: C.panelAlt,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: C.border),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: C.border),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: C.green, width: 1.5),
            ),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          ),
          onSubmitted: (_) => _identify(),
        ),

        if (_identifyError != null) ...[
          const SizedBox(height: 12),
          _errorBox(_identifyError!),
        ],

        const SizedBox(height: 24),
        SizedBox(
          height: 48,
          child: ElevatedButton(
            onPressed: _identifying ? null : _identify,
            style: ElevatedButton.styleFrom(
              backgroundColor: C.green,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8)),
            ),
            child: _identifying
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Text('Identify Plant',
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 15,
                        color: Colors.white)),
          ),
        ),
      ],
    );
  }

  // ── Step 1 ───────────────────────────────────────────────────────────────────

  Widget _buildAgeStep() {
    final emoji = _plantEmoji(_identified);
    final label = _identified[0].toUpperCase() + _identified.substring(1);

    final ageOptions = [1, 2, 3, 5, 7, 14, 21, 30, 60, 90];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Identification result badge
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: C.green.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: C.green.withValues(alpha: 0.3)),
          ),
          child: Row(
            children: [
              Text(emoji, style: const TextStyle(fontSize: 28)),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Identified as',
                      style: TextStyle(color: C.textMuted, fontSize: 12)),
                  Text(label,
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w700)),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 28),

        // Plant nickname
        const Text('Give it a name',
            style: TextStyle(
                fontSize: 14, fontWeight: FontWeight.w600, color: C.textMuted)),
        const SizedBox(height: 8),
        TextField(
          controller: _nickCtrl,
          style: const TextStyle(fontSize: 14),
          decoration: InputDecoration(
            hintText: 'e.g. Balcony Tomato',
            hintStyle: const TextStyle(color: C.textMuted),
            filled: true,
            fillColor: C.panelAlt,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: C.border),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: C.border),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: C.green, width: 1.5),
            ),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          ),
        ),

        const SizedBox(height: 24),

        // Age selector
        const Text('How long has it been growing?',
            style: TextStyle(
                fontSize: 14, fontWeight: FontWeight.w600, color: C.textMuted)),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: ageOptions.map((days) {
            final selected = _ageDays == days;
            final label = days < 7
                ? '$days day${days == 1 ? '' : 's'}'
                : days < 30
                    ? '${days ~/ 7} week${days ~/ 7 == 1 ? '' : 's'}'
                    : '${days ~/ 30} month${days ~/ 30 == 1 ? '' : 's'}';
            return GestureDetector(
              onTap: () => setState(() => _ageDays = days),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 100),
                padding: const EdgeInsets.symmetric(
                    horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: selected
                      ? C.green.withValues(alpha: 0.15)
                      : C.panelAlt,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: selected ? C.green : C.border,
                    width: selected ? 1.5 : 1,
                  ),
                ),
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: selected
                        ? FontWeight.w600
                        : FontWeight.normal,
                    color: selected ? C.green : C.textMuted,
                  ),
                ),
              ),
            );
          }).toList(),
        ),

        if (_saveError != null) ...[
          const SizedBox(height: 12),
          _errorBox(_saveError!),
        ],

        const SizedBox(height: 28),
        SizedBox(
          height: 48,
          child: ElevatedButton(
            onPressed: _saving ? null : _save,
            style: ElevatedButton.styleFrom(
              backgroundColor: C.green,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8)),
            ),
            child: _saving
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Text('Add Plant',
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 15,
                        color: Colors.white)),
          ),
        ),
      ],
    );
  }

  Widget _errorBox(String msg) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: C.danger.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: C.danger.withValues(alpha: 0.4)),
      ),
      child: Text(msg,
          style: const TextStyle(color: C.danger, fontSize: 13)),
    );
  }
}
