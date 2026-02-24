import 'package:flutter/material.dart';
import '../theme.dart';
import '../widgets/shared.dart';
import '../services/api_client.dart';

class MqttSettingsScreen extends StatefulWidget {
  const MqttSettingsScreen({super.key});

  @override
  State<MqttSettingsScreen> createState() => _MqttSettingsScreenState();
}

class _MqttSettingsScreenState extends State<MqttSettingsScreen> {
  bool isLoading = false;
  bool isSaving = false;
  String? error;

  final ApiClient _api = ApiClient();

  late final TextEditingController _brokerCtrl;
  late final TextEditingController _portCtrl;
  late final TextEditingController _topicCtrl;
  late final TextEditingController _subscribeTopicCtrl;
  late final TextEditingController _keepaliveCtrl;
  int _qos = 1;

  @override
  void initState() {
    super.initState();
    _brokerCtrl = TextEditingController();
    _portCtrl = TextEditingController();
    _topicCtrl = TextEditingController();
    _subscribeTopicCtrl = TextEditingController();
    _keepaliveCtrl = TextEditingController();
    _loadConfig();
  }

  @override
  void dispose() {
    _brokerCtrl.dispose();
    _portCtrl.dispose();
    _topicCtrl.dispose();
    _subscribeTopicCtrl.dispose();
    _keepaliveCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadConfig() async {
    setState(() {
      isLoading = true;
      error = null;
    });
    try {
      final response = await _api.getMqttConfig();
      if (response['success'] == true) {
        final cfg = (response['config'] as Map<String, dynamic>?) ?? {};
        setState(() {
          _brokerCtrl.text = cfg['broker_url'] as String? ?? 'test.mosquitto.org';
          _portCtrl.text = '${cfg['port'] ?? 1883}';
          _topicCtrl.text = cfg['topic'] as String? ?? 'companyA/GH-A1/environment';
          _subscribeTopicCtrl.text =
              cfg['subscribe_topic'] as String? ?? 'companyA/+/environment';
          _qos = (cfg['qos'] as num?)?.toInt() ?? 1;
          _keepaliveCtrl.text = '${cfg['keepalive'] ?? 60}';
        });
      } else {
        setState(() => error = response['error'] as String? ?? 'Failed to load config');
      }
    } catch (e) {
      setState(() => error = e.toString());
    } finally {
      setState(() => isLoading = false);
    }
  }

  Future<void> _saveConfig() async {
    setState(() {
      isSaving = true;
      error = null;
    });
    try {
      final response = await _api.updateMqttConfig({
        'broker_url': _brokerCtrl.text.trim(),
        'port': int.tryParse(_portCtrl.text.trim()) ?? 1883,
        'topic': _topicCtrl.text.trim(),
        'subscribe_topic': _subscribeTopicCtrl.text.trim(),
        'qos': _qos,
        'keepalive': int.tryParse(_keepaliveCtrl.text.trim()) ?? 60,
      });
      if (!mounted) return;
      if (response['success'] == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('MQTT config saved'),
            backgroundColor: C.green,
            duration: Duration(seconds: 2),
          ),
        );
      } else {
        setState(() => error = response['error'] as String? ?? 'Save failed');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => isSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('MQTT Settings'),
        backgroundColor: C.panel,
        elevation: 0,
      ),
      backgroundColor: C.bg,
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Broker connection ──────────────────────────────────
                  Panel(
                    accentLeft: C.info,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const PanelTitle('Broker Connection'),
                        const SizedBox(height: 12),
                        _field('Broker URL', _brokerCtrl, 'test.mosquitto.org'),
                        const SizedBox(height: 10),
                        _field('Port', _portCtrl, '1883',
                            type: TextInputType.number),
                        const SizedBox(height: 10),
                        _field('Keepalive (s)', _keepaliveCtrl, '60',
                            type: TextInputType.number),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ── Topics & QoS ───────────────────────────────────────
                  Panel(
                    accentLeft: C.green,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const PanelTitle('Topics & QoS'),
                        const SizedBox(height: 12),
                        _field('Publish Topic', _topicCtrl,
                            'companyA/GH-A1/environment'),
                        const SizedBox(height: 10),
                        _field('Subscribe Topic', _subscribeTopicCtrl,
                            'companyA/+/environment'),
                        const SizedBox(height: 14),
                        Row(
                          children: [
                            const Text('QoS Level',
                                style: TextStyle(
                                    color: C.textMuted, fontSize: 14)),
                            const Spacer(),
                            ...List.generate(3, (q) {
                              final selected = _qos == q;
                              return Padding(
                                padding: const EdgeInsets.only(left: 8),
                                child: ChoiceChip(
                                  label: Text('$q'),
                                  selected: selected,
                                  onSelected: (_) =>
                                      setState(() => _qos = q),
                                  selectedColor:
                                      C.green.withValues(alpha: 0.25),
                                  labelStyle: TextStyle(
                                    color: selected ? C.green : C.textMuted,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              );
                            }),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ── Pipeline info ──────────────────────────────────────
                  Panel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        PanelTitle('About MQTT Pipeline'),
                        SizedBox(height: 8),
                        Text(
                          'The simulation engine publishes hourly plant-state '
                          'snapshots to the configured MQTT broker. The '
                          'subscriber validates each message and stores it to '
                          'Firebase Firestore.',
                          style: TextStyle(
                              color: C.textMuted, fontSize: 14, height: 1.5),
                        ),
                        SizedBox(height: 10),
                        _InfoRow(
                            icon: Icons.cloud_upload,
                            label: 'Publisher',
                            value: 'plant-metrics-mqtt/publisher/'),
                        _InfoRow(
                            icon: Icons.cloud_download,
                            label: 'Subscriber',
                            value: 'plant-metrics-mqtt/subscriber/'),
                        _InfoRow(
                            icon: Icons.storage,
                            label: 'Storage',
                            value: 'Firestore: mqtt_plant_states'),
                      ],
                    ),
                  ),

                  // ── Error banner ───────────────────────────────────────
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: C.danger.withValues(alpha: 0.1),
                        border: Border.all(
                            color: C.danger.withValues(alpha: 0.4)),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(error!,
                          style: const TextStyle(
                              color: C.danger, fontSize: 14)),
                    ),
                  ],
                  const SizedBox(height: 16),

                  // ── Save button ────────────────────────────────────────
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton.icon(
                      onPressed: isSaving ? null : _saveConfig,
                      icon: isSaving
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation(
                                      Colors.white)),
                            )
                          : const Icon(Icons.save),
                      label: const Text('Save Configuration',
                          style: TextStyle(
                              fontWeight: FontWeight.w600, fontSize: 16)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: C.green,
                        foregroundColor: Colors.white,
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
    );
  }

  Widget _field(
    String label,
    TextEditingController ctrl,
    String hint, {
    TextInputType? type,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(color: C.textMuted, fontSize: 14)),
        const SizedBox(height: 4),
        TextField(
          controller: ctrl,
          keyboardType: type,
          style: const TextStyle(fontSize: 15),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: const TextStyle(color: C.textDim),
            filled: true,
            fillColor: C.panelAlt,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(6),
              borderSide: const BorderSide(color: C.border),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(6),
              borderSide: const BorderSide(color: C.border),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(6),
              borderSide: const BorderSide(color: C.green),
            ),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          ),
        ),
      ],
    );
  }
}

// ── Small info row widget ─────────────────────────────────────────────────────

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        children: [
          Icon(icon, color: C.info, size: 16),
          const SizedBox(width: 8),
          Text(label,
              style: const TextStyle(color: C.textMuted, fontSize: 14)),
          const Spacer(),
          Text(value,
              style: const TextStyle(
                  color: C.textPrimary,
                  fontSize: 13,
                  fontFamily: 'monospace')),
        ],
      ),
    );
  }
}
