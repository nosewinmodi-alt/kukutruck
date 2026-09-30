import 'package:flutter/material.dart';

import 'api.dart';
import 'strings.dart';

String _today() => DateTime.now().toIso8601String().substring(0, 10);
void _snack(BuildContext c, String m) => ScaffoldMessenger.of(c).showSnackBar(SnackBar(content: Text(m)));
String _alert(Map a) => Strings.t('a_${a['code']}') + (a['flock'] != null ? ': ${a['flock']}' : '');

// ───────────────────────────── Login / register ─────────────────────────────
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phone = TextEditingController(), _pass = TextEditingController(), _name = TextEditingController(), _farm = TextEditingController();
  bool _reg = false, _consent = false, _busy = false;

  Future<void> _go() async {
    if (_reg && !_consent) return _snack(context, Strings.t('consent'));
    setState(() => _busy = true);
    try {
      final r = await Api.post(_reg ? '/auth/register' : '/auth/login', {
        'phone': _phone.text.trim(), 'password': _pass.text,
        if (_reg) ...{'name': _name.text.trim(), 'farm_name': _farm.text.trim(), 'consent': true, 'account_type': 'farm'},
      });
      await Api.setToken(r['access_token'] as String);
    } on ApiException catch (e) {
      if (mounted) _snack(context, e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Strings.t;
    return Scaffold(
      appBar: AppBar(title: const Text('🥚 KukuTrack')),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        Text(_reg ? t('register') : t('login'), style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 16),
        if (_reg) ...[TextField(controller: _name, decoration: InputDecoration(labelText: t('name'))), const SizedBox(height: 12)],
        TextField(controller: _phone, keyboardType: TextInputType.phone, decoration: InputDecoration(labelText: t('phone'))),
        const SizedBox(height: 12),
        TextField(controller: _pass, obscureText: true, decoration: InputDecoration(labelText: t('password'))),
        if (_reg) ...[
          const SizedBox(height: 12),
          TextField(controller: _farm, decoration: InputDecoration(labelText: t('farm'))),
          CheckboxListTile(value: _consent, onChanged: (v) => setState(() => _consent = v ?? false), title: Text(t('consent')), controlAffinity: ListTileControlAffinity.leading, contentPadding: EdgeInsets.zero),
        ],
        const SizedBox(height: 16),
        FilledButton(onPressed: _busy ? null : _go, child: Text(_reg ? t('register') : t('login'))),
        TextButton(onPressed: () => setState(() => _reg = !_reg), child: Text(_reg ? t('login') : t('register'))),
        TextButton(onPressed: Strings.toggle, child: Text(t('lang'))),
      ]),
    );
  }
}

// ───────────────────────────── Home: dashboard + flocks ─────────────────────────────
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<List<dynamic>> _data = _load();

  Future<List<dynamic>> _load() async {
    await Api.flush();
    return Future.wait([Api.cachedGet('dash', '/reports/dashboard'), Api.cachedGet('flocks', '/flocks')]);
  }

  Future<void> _refresh() async {
    setState(() => _data = _load());
    await _data;
  }

  Widget _stat(String label, Object v) => Expanded(
        child: Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: const TextStyle(fontSize: 12)), Text('$v', style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
        ]))),
      );

  @override
  Widget build(BuildContext context) {
    final t = Strings.t;
    return Scaffold(
      appBar: AppBar(title: const Text('🥚 KukuTrack'), actions: [
        ValueListenableBuilder<int>(
          valueListenable: Api.pending,
          builder: (_, n, __) => n == 0 ? const SizedBox() : Center(child: Chip(label: Text('$n ${t('pending')}'))),
        ),
        IconButton(icon: const Icon(Icons.translate), onPressed: Strings.toggle),
        IconButton(icon: const Icon(Icons.logout), tooltip: t('logout'), onPressed: () => Api.setToken(null)),
      ]),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<dynamic>>(
          future: _data,
          builder: (ctx, snap) {
            if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
            if (snap.hasError) return ListView(children: [Padding(padding: const EdgeInsets.all(24), child: Text('${snap.error}'))]);
            final d = snap.data![0] as Map, flocks = snap.data![1] as List;
            return ListView(padding: const EdgeInsets.all(12), children: [
              Row(children: [_stat(t('birds'), d['live_birds']), _stat(t('eggsToday'), d['eggs_today'])]),
              Row(children: [_stat(t('eggs7'), d['eggs_7d']), const Spacer()]),
              for (final a in d['alerts'] as List)
                Card(color: a['level'] == 'critical' ? Colors.red.shade100 : Colors.amber.shade100, child: ListTile(dense: true, leading: const Icon(Icons.warning_amber), title: Text(_alert(a as Map)))),
              const SizedBox(height: 8),
              Text(t('flocks'), style: Theme.of(context).textTheme.titleLarge),
              if (flocks.isEmpty) Padding(padding: const EdgeInsets.all(16), child: Text(t('none'))),
              for (final f in flocks)
                Card(child: ListTile(
                  title: Text(f['name']),
                  subtitle: Text('${f['kind']} · ${t('day')} ${f['age_days']} · ${f['kpis']['live_birds']}/${f['initial_count']}'),
                  trailing: f['logged_today'] == true ? const Icon(Icons.check_circle, color: Colors.green) : Chip(label: Text(t('notLogged'))),
                  onTap: () async {
                    await Navigator.push(ctx, MaterialPageRoute(builder: (_) => FlockScreen(id: f['id'] as int)));
                    _refresh();
                  },
                )),
            ]);
          },
        ),
      ),
    );
  }
}

// ───────────────────────────── Flock: KPIs, daily record, vaccinations ─────────────────────────────
class FlockScreen extends StatefulWidget {
  final int id;
  const FlockScreen({super.key, required this.id});
  @override
  State<FlockScreen> createState() => _FlockScreenState();
}

class _FlockScreenState extends State<FlockScreen> {
  final _eggs = TextEditingController(text: '0'), _cracked = TextEditingController(text: '0'), _deaths = TextEditingController(text: '0'), _feed = TextEditingController(text: '0');
  late Future<List<dynamic>> _data = _load();

  Future<List<dynamic>> _load() => Future.wait([
        Api.cachedGet('f${widget.id}', '/flocks/${widget.id}'),
        Api.cachedGet('v${widget.id}', '/vaccinations?flock_id=${widget.id}'),
      ]);

  Future<void> _save(Map f) async {
    final data = {
      'flock_id': widget.id, 'log_date': _today(),
      'eggs': f['kind'] == 'broiler' ? 0 : int.tryParse(_eggs.text) ?? 0,
      'cracked': f['kind'] == 'broiler' ? 0 : int.tryParse(_cracked.text) ?? 0,
      'deaths': int.tryParse(_deaths.text) ?? 0,
      'feed_kg': double.tryParse(_feed.text) ?? 0,
    };
    try {
      final sent = await Api.submit('log', data);
      if (mounted) _snack(context, sent ? Strings.t('saved') : Strings.t('savedOffline'));
      if (sent) setState(() => _data = _load());
    } on ApiException catch (e) {
      if (mounted) _snack(context, e.message);
    }
  }

  Widget _field(TextEditingController c, String label) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TextField(controller: c, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: label)),
      );

  @override
  Widget build(BuildContext context) {
    final t = Strings.t;
    return Scaffold(
      appBar: AppBar(title: const Text('KukuTrack')),
      body: FutureBuilder<List<dynamic>>(
        future: _data,
        builder: (_, snap) {
          if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snap.hasError) return Center(child: Text('${snap.error}'));
          final f = snap.data![0] as Map, vs = snap.data![1] as List, k = f['kpis'] as Map;
          final broiler = f['kind'] == 'broiler';
          return ListView(padding: const EdgeInsets.all(12), children: [
            Text('${f['name']}  ·  ${t('day')} ${f['age_days']}', style: Theme.of(context).textTheme.headlineSmall),
            for (final a in f['alerts'] as List) Card(color: Colors.amber.shade100, child: ListTile(dense: true, title: Text(_alert(a as Map)))),
            Wrap(spacing: 8, runSpacing: 8, children: [
              _kpi(t('birds'), '${k['live_birds']}'), _kpi(t('mortality'), '${k['mortality_pct']}%'),
              _kpi(broiler ? t('fcr') : t('henday'), '${(broiler ? k['fcr'] : k['hen_day_pct']) ?? '–'}'),
              if (k['profit'] != null) _kpi(t('profit'), 'KES ${(k['profit'] as num).round()}'),
            ]),
            const SizedBox(height: 12),
            Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t('logToday'), style: Theme.of(context).textTheme.titleMedium), const SizedBox(height: 10),
              if (!broiler) ...[_field(_eggs, t('eggs')), _field(_cracked, t('cracked'))],
              _field(_deaths, t('deaths')), _field(_feed, t('feed')),
              FilledButton(onPressed: () => _save(f), child: Text(t('save'))),
            ]))),
            Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t('vacc'), style: Theme.of(context).textTheme.titleMedium),
              for (final v in vs)
                ListTile(
                  contentPadding: EdgeInsets.zero, dense: true, title: Text(v['vaccine']), subtitle: Text(v['due_date']),
                  trailing: v['done_on'] != null
                      ? const Icon(Icons.check_circle, color: Colors.green)
                      : TextButton(
                          child: Text(t('done')),
                          onPressed: () async {
                            try {
                              await Api.post('/vaccinations/${v['id']}/done');
                              setState(() => _data = _load());
                            } on ApiException catch (e) {
                              if (mounted) _snack(context, e.message);
                            }
                          }),
                ),
            ]))),
          ]);
        },
      ),
    );
  }

  Widget _kpi(String l, String v) => SizedBox(width: 160, child: Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(l, style: const TextStyle(fontSize: 12)), Text(v, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
      ]))));
}
