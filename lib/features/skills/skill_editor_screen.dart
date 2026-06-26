import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/db/database.dart';
import '../../providers/providers.dart';

class SkillEditorScreen extends ConsumerStatefulWidget {
  const SkillEditorScreen({super.key, required this.skillId});
  final String skillId;

  @override
  ConsumerState<SkillEditorScreen> createState() => _SkillEditorScreenState();
}

class _SkillEditorScreenState extends ConsumerState<SkillEditorScreen> {
  bool? _requireReview;
  String? _name;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_requireReview == null) _load();
  }

  Future<void> _load() async {
    final dao = ref.read(skillDaoProvider);
    final all = await dao.getAllSkills();
    final match = all.where((s) => s.id == widget.skillId).firstOrNull;
    if (mounted && match != null) {
      setState(() {
        _requireReview = match.requireReview;
        _name = match.name;
      });
    }
  }

  Future<void> _toggleRequireReview(bool value) async {
    setState(() => _requireReview = value);
    await ref.read(skillDaoProvider).updateRequireReview(widget.skillId, value);
  }

  @override
  Widget build(BuildContext context) {
    if (_requireReview == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(title: Text(_name ?? widget.skillId)),
      body: ListView(
        children: [
          SwitchListTile(
            title: const Text('Require review before actions fire'),
            subtitle: const Text(
              'Hermes will pause and show you results before sending to Slack, Linear, or webhooks.',
            ),
            value: _requireReview!,
            onChanged: _toggleRequireReview,
          ),
        ],
      ),
    );
  }
}
