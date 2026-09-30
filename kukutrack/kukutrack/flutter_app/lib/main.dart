import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

import 'api.dart';
import 'screens.dart';
import 'strings.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Api.load();
  await Strings.load();
  runApp(const KukuApp());
}

class KukuApp extends StatefulWidget {
  const KukuApp({super.key});
  @override
  State<KukuApp> createState() => _KukuAppState();
}

class _KukuAppState extends State<KukuApp> {
  StreamSubscription<List<ConnectivityResult>>? _sub;

  @override
  void initState() {
    super.initState();
    Api.flush();
    // Sync queued records automatically whenever connectivity returns.
    _sub = Connectivity().onConnectivityChanged.listen((r) {
      if (!r.contains(ConnectivityResult.none)) Api.flush();
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const ink = Color(0xFF1F2A1B), yolk = Color(0xFFE8A317), shell = Color(0xFFF6EFE0);
    return ValueListenableBuilder<String>(
      valueListenable: Strings.lang,
      builder: (_, __, ___) => MaterialApp(
        title: 'KukuTrack',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(seedColor: ink, primary: ink, secondary: yolk, surface: shell),
          scaffoldBackgroundColor: shell,
          appBarTheme: const AppBarTheme(backgroundColor: ink, foregroundColor: shell),
          inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
        ),
        home: ValueListenableBuilder<bool>(
          valueListenable: Api.loggedIn,
          builder: (_, on, __) => on ? const HomeScreen() : const LoginScreen(),
        ),
      ),
    );
  }
}
