import "dart:async";
import "dart:io";

import "package:flutter/material.dart";

import "core/models.dart";
import "core/services.dart";
import "lms/protocol.dart";
import "navidrome/subsonic.dart";
import "squeezelite/core_runner.dart";

void main() => runApp(const SonoraApp());

class SonoraApp extends StatelessWidget {
  const SonoraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Sonora v2",
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo)),
      home: const SonoraHome(),
    );
  }
}

class SonoraHome extends StatefulWidget {
  const SonoraHome({super.key});

  @override
  State<SonoraHome> createState() => _SonoraHomeState();
}

class _SonoraHomeState extends State<SonoraHome> with WidgetsBindingObserver {
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  final _host = TextEditingController(text: "192.168.199.2");
  final _port = TextEditingController(text: "9000");
  final _slim = TextEditingController(text: "3483");
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _lmsCreds = TextEditingController(
      text: "/Users/song/.squeezelite_gui/config.json");
  final _navHost = TextEditingController(text: "192.168.199.2:4533");
  final _navCreds = TextEditingController(
      text: "/Users/song/navidrome_creds.json");

  LmsTarget? _target;
  CoreRunner? _runner;
  Timer? _timer;
  String? _playerId;
  bool _busy = false;
  String _lmsVersion = "-";
  int _playerCount = -1;
  String _coreStatus = "未启动";
  PlaybackStatus _status = const PlaybackStatus();
  int _volume = 100;
  List<String> _logs = <String>[];
  List<AlbumInfo> _albums = <AlbumInfo>[];
  List<SongInfo> _songs = <SongInfo>[];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Headless verification hook: SONORA_AUTO_CONNECT=1 makes the real UI
    // exercise the same connect path a user clicks, without GUI automation.
    if (Platform.environment["SONORA_AUTO_CONNECT"] == "1") {
      // ignore: avoid_print
      print("SONORA_AUTO_CONNECT armed");
      WidgetsBinding.instance.addPostFrameCallback((_) {
        // ignore: avoid_print
        print("SONORA_AUTO_CONNECT firing");
        unawaited(_connect());
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    unawaited(_runner?.stop());
    for (final c in <TextEditingController>[
      _host, _port, _slim, _user, _pass, _lmsCreds, _navHost, _navCreds,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) unawaited(_stopCore());
  }

  void _log(String line) {
    final stamped = "${DateTime.now().toIso8601String().substring(11, 19)} $line";
    if (Platform.environment["SONORA_AUTO_CONNECT"] == "1") {
      // ignore: avoid_print
      print(stamped);
    }
    if (!mounted) return;
    setState(() {
      _logs.add(stamped);
      if (_logs.length > 200) _logs.removeAt(0);
    });
  }

  void _importLmsCreds() {
    final path = _lmsCreds.text.trim();
    final c = readCreds(path);
    if (c.isEmpty) {
      _log("凭证文件为空或不存在：$path");
      return;
    }
    final host = c["lms_host"];
    if (host != null && host.isNotEmpty) _host.text = host;
    final port = int.tryParse(c["lms_port"] ?? "");
    if (port != null) _port.text = port.toString();
    final slim = int.tryParse(c["slim_port"] ?? "");
    if (slim != null) _slim.text = slim.toString();
    final user = c["lms_user"] ?? c["user"];
    if (user != null && user.isNotEmpty) _user.text = user;
    final pass = c["lms_pass"] ?? c["pass"] ?? c["password"];
    if (pass != null && pass.isNotEmpty) _pass.text = pass;
    _log("已从本地配置导入连接参数（密码未显示）");
  }

  Future<void> _connect() async {
    setState(() => _busy = true);
    try {
      if (_lmsCreds.text.trim().isNotEmpty && _user.text.isEmpty) {
        _importLmsCreds();
      }
      final target = LmsTarget(
        host: _host.text.trim(),
        port: int.tryParse(_port.text.trim()) ?? 9000,
        slimPort: int.tryParse(_slim.text.trim()) ?? 3483,
        user: _user.text.trim().isEmpty ? null : _user.text.trim(),
        pass: _pass.text.isEmpty ? null : _pass.text,
      );
      _target = target;
      _log("连接 LMS ${target.baseUrl}");
      if (Platform.environment["SONORA_AUTO_CONNECT"] == "1") {
        try {
          final s = await Socket.connect(
            target.host,
            target.port,
            timeout: const Duration(seconds: 5),
          );
          _log("raw socket ok ${s.remoteAddress.address}");
          s.destroy();
        } catch (e) {
          _log("raw socket err $e");
        }
      }
      final info = await probeLms(target, onError: (m) => _log("LMS $m"));
      if (!mounted) return;
      setState(() => _lmsVersion = info.version.isEmpty ? "-" : info.version);
      if (!info.reachable) {
        _log("LMS 不可达：${info.error ?? '未知错误'}");
        return;
      }
      _log("LMS 已连接，版本 ${info.version}");
      await _startCore(target);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _startCore(LmsTarget target) async {
    if (_runner != null) {
      _log("核心已在运行，跳过重复启动");
      return;
    }
    const playerName = "Sonora-UI";
    final runner = CoreRunner(
      lmsHost: target.host,
      lmsPort: target.port,
      slimPort: target.slimPort,
      playerName: playerName,
      onLog: _log,
    );
    _runner = runner;
    setState(() => _coreStatus = "启动中...");
    try {
      final p = await runner.start();
      if (!mounted) return;
      setState(() => _coreStatus = "已启动 pid=${p.pid}");
      _log("核心已自动拉起 pid=${p.pid}");

      final before = await lmsPlayerCount(target, onError: (m) => _log("播放器 $m"));
      if (!mounted) return;
      setState(() => _playerCount = before);
      _log("播放器 count=$before（可能含离线残留）");

      final online = await waitForOnlinePlayers(
        target,
        timeout: const Duration(seconds: 15),
        onError: (m) => _log("播放器 $m"),
      );
      if (!mounted) return;
      setState(() => _playerCount = online.length);
      _log("在线播放器 ${online.length} 个");
      if (online.isEmpty) {
        _log("未检测到在线播放器注册");
        return;
      }

      final ours = online.where((p) => p.name == playerName).toList();
      final chosen = ours.isNotEmpty ? ours.first : online.first;
      _playerId = chosen.id;
      _log("播放器：${chosen.name} (${chosen.id})");
      _timer?.cancel();
      _timer = Timer.periodic(
        const Duration(seconds: 2),
        (_) => unawaited(_refreshStatus()),
      );
      await _refreshStatus();
    } catch (e) {
      if (mounted) setState(() => _coreStatus = "失败");
      _log("核心启动失败 ${e.toString().split('\n').first}");
    }
  }

  Future<void> _stopCore() async {
    _timer?.cancel();
    _timer = null;
    final runner = _runner;
    if (runner == null) return;
    await runner.stop();
    _runner = null;
    _playerId = null;
    if (mounted) setState(() => _coreStatus = "已停止");
    _log("核心已停止");
  }

  Future<void> _refreshStatus() async {
    final target = _target;
    final id = _playerId;
    if (target == null || id == null || id.isEmpty) return;
    final s = await fetchLmsStatus(target, id, onError: (m) => _log("状态 $m"));
    if (!mounted) return;
    setState(() {
      _status = s;
      _volume = s.volume;
    });
  }

  Future<void> _command(List<String> cmd, String label) async {
    final target = _target;
    final id = _playerId;
    if (target == null || id == null || id.isEmpty) {
      _log("请先连接并启动核心");
      return;
    }
    _log("控制：$label");
    await sendLmsCommand(target, id, cmd, onError: (m) => _log("控制 $m"));
    unawaited(_refreshStatus());
  }

  NavidromeTarget? _navidromeTarget() {
    final c = readCreds(_navCreds.text.trim());
    final user = c["user"];
    final pass = c["password"] ?? c["pass"];
    if (user == null || pass == null) {
      _log("Navidrome 凭证不完整：${_navCreds.text}");
      return null;
    }
    return NavidromeTarget(
      host: _navHost.text.trim(),
      auth: SubsonicAuth(
        user: user,
        password: pass,
        salt: DateTime.now().microsecondsSinceEpoch.toString(),
        client: "Sonora",
      ),
    );
  }

  Future<void> _loadAlbums() async {
    final target = _navidromeTarget();
    if (target == null) return;
    setState(() => _busy = true);
    try {
      final info = await probeNavidrome(target, onError: (m) => _log("Navidrome $m"));
      _log("Navidrome ${info.version.isEmpty ? '未知版本' : info.version} "
          "${info.reachable ? 'ok' : '失败'}");
      final albums = await fetchNavidromeAlbums(
        target,
        onError: (m) => _log("曲库 $m"),
      );
      if (!mounted) return;
      setState(() {
        _albums = albums;
        _songs = const <SongInfo>[];
      });
      _log("专辑 ${albums.length} 张");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadSongs(AlbumInfo album) async {
    final target = _navidromeTarget();
    if (target == null) return;
    final songs = await fetchNavidromeAlbum(
      target,
      album.id,
      onError: (m) => _log("专辑详情 $m"),
    );
    if (!mounted) return;
    setState(() => _songs = songs);
    _log("${album.name}：${songs.length} 首");
  }

  Widget _field(String label, TextEditingController controller,
      {bool obscure = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: TextField(
        controller: controller,
        obscureText: obscure,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
          isDense: true,
        ),
      ),
    );
  }

  Widget _statusRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: <Widget>[
          SizedBox(width: 90, child: Text("$label：")),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        key: _scaffoldKey,
        appBar: AppBar(
          title: const Text("Sonora v2"),
          bottom: const TabBar(
            tabs: <Widget>[
              Tab(text: "连接"),
              Tab(text: "播放"),
              Tab(text: "曲库"),
            ],
          ),
          actions: <Widget>[
            IconButton(
              icon: const Icon(Icons.article_outlined),
              tooltip: "日志",
              onPressed: () => _scaffoldKey.currentState?.openEndDrawer(),
            ),
          ],
        ),
        endDrawer: Drawer(
          child: SafeArea(
            child: Column(
              children: <Widget>[
                ListTile(
                  title: const Text("运行日志"),
                  trailing: TextButton(
                    onPressed: () => setState(() => _logs = <String>[]),
                    child: const Text("清空"),
                  ),
                ),
                Expanded(
                  child: ListView.builder(
                    itemCount: _logs.length,
                    itemBuilder: (context, i) => Text(
                      _logs.reversed.toList()[i],
                      style: const TextStyle(fontSize: 11, fontFamily: "monospace"),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        body: TabBarView(
          children: <Widget>[
            SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _field("LMS 主机", _host),
                  _field("JSON-RPC 端口", _port),
                  _field("slimproto 端口", _slim),
                  _field("用户名（可留空，用配置文件）", _user),
                  _field("密码", _pass, obscure: true),
                  _field("旧配置路径（只读导入）", _lmsCreds),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    children: <Widget>[
                      ElevatedButton.icon(
                        onPressed: _busy ? null : _importLmsCreds,
                        icon: const Icon(Icons.file_open_outlined),
                        label: const Text("导入凭证"),
                      ),
                      ElevatedButton.icon(
                        onPressed: _busy ? null : () => unawaited(_connect()),
                        icon: const Icon(Icons.link),
                        label: const Text("连接并自动拉起核心"),
                      ),
                      OutlinedButton.icon(
                        onPressed: _busy ? null : () => unawaited(_stopCore()),
                        icon: const Icon(Icons.stop_circle_outlined),
                        label: const Text("停止核心"),
                      ),
                    ],
                  ),
                  if (_busy) const LinearProgressIndicator(),
                  const Divider(),
                  _statusRow("LMS 版本", _lmsVersion),
                  _statusRow("播放器数量", _playerCount < 0 ? "-" : "$_playerCount"),
                  _statusRow("核心状态", _coreStatus),
                  const SizedBox(height: 12),
                  const Text(
                    "连接时会自动把内置 squeezelite 复制到用户目录并拉起子进程；"
                    "不需要手动启动。",
                  ),
                ],
              ),
            ),
            SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    _status.title.isEmpty ? "未播放" : _status.title,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  Text(_status.artist.isEmpty ? "" : "艺人：${_status.artist}"),
                  Text(_status.album.isEmpty ? "" : "专辑：${_status.album}"),
                  const SizedBox(height: 12),
                  Text("${formatDuration(_status.position)} / ${formatDuration(_status.duration)}"),
                  Slider(
                    value: _status.duration == 0
                        ? 0
                        : (_status.position > _status.duration
                            ? _status.duration.toDouble()
                            : _status.position.toDouble()),
                    max: _status.duration == 0 ? 1 : _status.duration.toDouble(),
                    onChanged: (_) {},
                    onChangeEnd: (v) =>
                        unawaited(_command(["seek", v.round().toString()], "跳转")),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: <Widget>[
                      IconButton(
                        icon: const Icon(Icons.skip_previous),
                        onPressed: () => unawaited(
                            _command(["playlist", "jump", "-1"], "上一首")),
                      ),
                      IconButton(
                        icon: Icon(_status.isPlaying
                            ? Icons.pause_circle_filled
                            : Icons.play_circle_filled),
                        iconSize: 40,
                        onPressed: () => unawaited(_command(
                          _status.isPlaying ? ["pause"] : ["play"],
                          _status.isPlaying ? "暂停" : "播放",
                        )),
                      ),
                      IconButton(
                        icon: const Icon(Icons.skip_next),
                        onPressed: () => unawaited(
                            _command(["playlist", "jump", "+1"], "下一首")),
                      ),
                    ],
                  ),
                  const Divider(),
                  Text("音量（界面值 $_volume / LMS 值 ${sliderToLms(_volume)}）"),
                  Slider(
                    value: _volume.toDouble(),
                    min: 0,
                    max: 100,
                    onChanged: (v) => setState(() => _volume = v.round()),
                    onChangeEnd: (v) => unawaited(_command(
                      ["mixer", "volume", sliderToLms(v.round()).toString()],
                      "音量 ${v.round()}",
                    )),
                  ),
                ],
              ),
            ),
            SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _field("Navidrome 地址", _navHost),
                  _field("凭证路径", _navCreds),
                  const SizedBox(height: 8),
                  ElevatedButton.icon(
                    onPressed: _busy ? null : () => unawaited(_loadAlbums()),
                    icon: const Icon(Icons.library_music_outlined),
                    label: const Text("加载专辑"),
                  ),
                  const Divider(),
                  Text("专辑 ${_albums.length} 张（入口以专辑为准）"),
                  ..._albums.map(
                    (a) => ListTile(
                      title: Text(a.name),
                      subtitle: Text(a.artist.isEmpty ? "未知艺人" : a.artist),
                      onTap: () => unawaited(_loadSongs(a)),
                    ),
                  ),
                  const Divider(),
                  Text("歌曲 ${_songs.length} 首"),
                  ..._songs.map(
                    (s) => ListTile(
                      title: Text(s.title),
                      subtitle: Text(
                          "${s.artist.isEmpty ? '未知艺人' : s.artist} · ${formatDuration(s.duration)}"),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
