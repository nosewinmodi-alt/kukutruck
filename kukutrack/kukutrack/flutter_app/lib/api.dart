import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Override at build time: flutter run --dart-define=API_BASE=https://app.example.co.ke/api
/// (10.0.2.2 is the host machine as seen from the Android emulator.)
const apiBase = String.fromEnvironment('API_BASE', defaultValue: 'http://10.0.2.2:8000/api');

class ApiException implements Exception {
  final String message;
  final int? status;
  ApiException(this.message, [this.status]);
  @override
  String toString() => message;
}

class NetworkException extends ApiException {
  NetworkException() : super('No network');
}

class Api {
  static const _store = FlutterSecureStorage();
  static String? token;
  static final loggedIn = ValueNotifier<bool>(false);
  static final pending = ValueNotifier<int>(0);

  static Future<void> load() async {
    token = await _store.read(key: 'token');
    loggedIn.value = token != null;
    pending.value = (await _queue()).length;
  }

  static Future<void> setToken(String? t) async {
    token = t;
    if (t == null) {
      await _store.delete(key: 'token');
      final p = await SharedPreferences.getInstance();
      for (final k in p.getKeys().where((k) => k.startsWith('c_') || k == 'queue').toList()) {
        await p.remove(k); // do not leave one farm's cached data on the phone after logout
      }
      pending.value = 0;
    } else {
      await _store.write(key: 'token', value: t);
    }
    loggedIn.value = t != null;
  }

  static Future<dynamic> _send(String method, String path, [Object? body]) async {
    final req = http.Request(method, Uri.parse('$apiBase$path'))
      ..headers['Content-Type'] = 'application/json'
      ..headers.addAll({if (token != null) 'Authorization': 'Bearer $token'});
    if (body != null) req.body = jsonEncode(body);
    http.Response r;
    try {
      r = await http.Response.fromStream(await req.send().timeout(const Duration(seconds: 20)));
    } catch (_) {
      throw NetworkException();
    }
    dynamic data;
    try {
      data = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {}
    if (r.statusCode == 401 && token != null) await setToken(null);
    if (r.statusCode >= 400) {
      final d = data is Map ? data['detail'] : null;
      final msg = d is String ? d : d is List ? d.map((e) => e['msg']).join('; ') : 'Error ${r.statusCode}';
      throw ApiException(msg, r.statusCode);
    }
    return data;
  }

  static Future<dynamic> get(String path) => _send('GET', path);
  static Future<dynamic> post(String path, [Object? body]) => _send('POST', path, body ?? {});

  /// GET with an on-device fallback so screens still render offline.
  static Future<dynamic> cachedGet(String key, String path) async {
    final p = await SharedPreferences.getInstance();
    try {
      final d = await get(path);
      await p.setString('c_$key', jsonEncode(d));
      return d;
    } on NetworkException {
      final s = p.getString('c_$key');
      if (s != null) return jsonDecode(s);
      rethrow;
    }
  }

  // ---------- offline queue (the server endpoints are idempotent) ----------
  static Future<List<dynamic>> _queue() async {
    final p = await SharedPreferences.getInstance();
    return jsonDecode(p.getString('queue') ?? '[]') as List<dynamic>;
  }

  static Future<void> _saveQueue(List<dynamic> q) async {
    await (await SharedPreferences.getInstance()).setString('queue', jsonEncode(q));
    pending.value = q.length;
  }

  /// type: 'log' | 'tx'. Returns true if saved on the server, false if queued for later.
  static Future<bool> submit(String type, Map<String, dynamic> data) async {
    try {
      final r = await post('/sync/push', {
        'logs': type == 'log' ? [data] : [],
        'transactions': type == 'tx' ? [data] : [],
      });
      final errs = r['errors'] as List;
      if (errs.isNotEmpty) throw ApiException('${errs.first['error']}');
      return true;
    } on NetworkException {
      final q = await _queue()..add({'type': type, 'data': data});
      await _saveQueue(q);
      return false;
    }
  }

  /// Send everything queued while offline. Returns how many records the server accepted.
  static Future<int> flush() async {
    final q = await _queue();
    if (q.isEmpty || token == null) return 0;
    try {
      final r = await post('/sync/push', {
        'logs': [for (final i in q) if (i['type'] == 'log') i['data']],
        'transactions': [for (final i in q) if (i['type'] == 'tx') i['data']],
      });
      await _saveQueue([]);
      return q.length - (r['errors'] as List).length;
    } on ApiException {
      return 0; // still offline (or server unhappy): keep the queue
    }
  }
}
