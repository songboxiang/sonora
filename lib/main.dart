import "package:flutter/material.dart";
import "lms/lms_client.dart";
import "state/player_provider.dart";

void main() => runApp(const SonoraApp());

class SonoraApp extends StatelessWidget {
  const SonoraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: "Sonora",
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF534AB7)),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final LmsClient _client;
  late final PlayerProvider _player;
  final _host = TextEditingController(text: "127.0.0.1");
  final _port = TextEditingController(text: "9000");
  bool _configured = false;

  @override
  void initState() {
    super.initState();
    _client = LmsClient(const LmsConfig());
    _player = PlayerProvider(_client);
  }

  @override
  void dispose() {
    _player.dispose();
    _client.dispose();
    _host.dispose();
    _port.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final cfg = LmsConfig(
      host: _host.text.trim(),
      port: int.tryParse(_port.text.trim()) ?? 9000,
    );
    await _player.connect(cfg);
    if (_player.connected) {
      setState(() => _configured = true);
      _player.startPolling();
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_player.error)),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _player,
      builder: (context, _) {
        return Scaffold(
          appBar: AppBar(
            title: const Text("Sonora"),
            actions: [
              IconButton(
                icon: Icon(_player.connected ? Icons.wifi : Icons.wifi_off),
                tooltip: _player.connected ? "已连接 LMS" : "未连接",
                onPressed: _configured ? () => _player.refresh() : null,
              ),
            ],
          ),
          body: _configured ? _playerView() : _connectView(),
        );
      },
    );
  }

  Widget _connectView() {
    return Center(
      child: SizedBox(
        width: 360,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(Icons.audiotrack, size: 64, color: Color(0xFF534AB7)),
            const SizedBox(height: 16),
            const Text("连接 Lyrion Media Server",
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w500)),
            const SizedBox(height: 24),
            TextField(controller: _host, decoration: const InputDecoration(
              labelText: "服务器地址", border: OutlineInputBorder())),
            const SizedBox(height: 12),
            TextField(controller: _port, keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: "端口", border: OutlineInputBorder())),
            const SizedBox(height: 20),
            FilledButton(onPressed: _connect, child: const Text("连接")),
          ],
        ),
      ),
    );
  }

  Widget _playerView() {
    final s = _player.status;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Column(
            children: [
              _artwork(s.artworkUrl),
              const SizedBox(height: 24),
              Text(s.title.isEmpty ? "未在播放" : s.title,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w500),
                textAlign: TextAlign.center),
              const SizedBox(height: 6),
              Text([s.artist, s.album].where((x) => x.isNotEmpty).join(" · "),
                style: const TextStyle(fontSize: 14, color: Colors.grey),
                textAlign: TextAlign.center),
              const SizedBox(height: 28),
              _progress(s),
              const SizedBox(height: 20),
              _controls(),
              const SizedBox(height: 32),
              _volume(s.volume),
            ],
          ),
        ),
      ),
    );
  }

  Widget _artwork(String url) {
    return Container(
      width: 220, height: 220,
      decoration: BoxDecoration(
        color: Colors.grey.shade200,
        borderRadius: BorderRadius.circular(16),
      ),
      clipBehavior: Clip.antiAlias,
      child: url.isNotEmpty
          ? Image.network(url, fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => const Icon(Icons.album, size: 80))
          : const Icon(Icons.album, size: 80, color: Colors.grey),
    );
  }

  Widget _progress(PlaybackStatus s) {
    final pos = _player.seekPreview ?? s.position;
    return Column(
      children: [
        Slider(
          value: pos.toDouble().clamp(0, s.duration > 0 ? s.duration.toDouble() : 1),
          max: s.duration > 0 ? s.duration.toDouble() : 1,
          onChanged: (v) => _player.previewSeek(v.toInt()),
          onChangeEnd: (v) => _player.commitSeek(v.toInt()),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [Text(_fmt(pos)), Text(_fmt(s.duration))],
          ),
        ),
      ],
    );
  }

  Widget _controls() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        IconButton(icon: const Icon(Icons.skip_previous, size: 36),
          onPressed: _player.busy ? null : _player.previous),
        const SizedBox(width: 16),
        Container(
          width: 64, height: 64,
          decoration: const BoxDecoration(color: Color(0xFF534AB7), shape: BoxShape.circle),
          child: IconButton(
            icon: Icon(sIcon(_player.status.isPlaying), size: 32, color: Colors.white),
            onPressed: _player.busy ? null : _player.togglePlay,
          ),
        ),
        const SizedBox(width: 16),
        IconButton(icon: const Icon(Icons.skip_next, size: 36),
          onPressed: _player.busy ? null : _player.next),
      ],
    );
  }

  IconData sIcon(bool playing) => playing ? Icons.pause : Icons.play_arrow;

  Widget _volume(int vol) {
    return Row(
      children: [
        const Icon(Icons.volume_down, size: 20),
        Expanded(child: Slider(value: vol.toDouble(), max: 100,
          onChanged: (v) => _player.setVolume(v.toInt()))),
        const Icon(Icons.volume_up, size: 20),
      ],
    );
  }

  String _fmt(int sec) {
    final m = sec ~/ 60, s = sec % 60;
    return "${m.toString().padLeft(2, "0")}:${s.toString().padLeft(2, "0")}";
  }
}
