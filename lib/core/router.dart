import 'package:go_router/go_router.dart';
import '../features/recordings/recordings_screen.dart';
import '../features/skills/skill_editor_screen.dart';

final appRouter = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (context, state) => const RecordingsScreen()),
    GoRoute(
      path: '/skills/:id/edit',
      builder: (context, state) =>
          SkillEditorScreen(skillId: state.pathParameters['id']!),
    ),
  ],
);
