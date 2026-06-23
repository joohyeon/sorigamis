import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';
import 'data/db/database.dart';
import 'data/seed/seed_data.dart';
import 'providers/providers.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    final db = AppDatabase.open();
    await seedIfEmpty(db);

    runApp(
      ProviderScope(
        overrides: [databaseProvider.overrideWithValue(db)],
        child: const SorigamisApp(),
      ),
    );
  } catch (error, stack) {
    // DB open or seed failed (e.g. storage full, no writable docs dir).
    // Surface something actionable instead of a black/red screen.
    // TODO: route to a crash reporter once one is wired up.
    debugPrint('Fatal: app startup failed: $error\n$stack');
    runApp(const _StartupErrorApp());
  }
}

/// Minimal fallback shown when startup (DB init/seed) fails fatally.
class _StartupErrorApp extends StatelessWidget {
  const _StartupErrorApp();

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Sorigamis',
      home: Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: const [
                Icon(Icons.error_outline, size: 48),
                SizedBox(height: 16),
                Text(
                  'Sorigamis could not start.',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: 8),
                Text(
                  'Please restart the app. If the problem persists, '
                  'reinstall to reset local data.',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
