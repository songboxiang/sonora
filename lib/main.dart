import "dart:async";
import "dart:io";

import "package:flutter/material.dart";
import "package:just_audio/just_audio.dart";

import "core/models.dart";
import "core/services.dart";
import "core/installer.dart";
import "core/settings.dart";
import "core/updates.dart";
import "lms/library.dart";
import "lms/protocol.dart";
import "navidrome/audio.dart";
import "navidrome/subsonic.dart";
import "squeezelite/core_runner.dart";

void main() => runApp(const SonoraApp());

class SonoraApp extends StatelessWidget {
  const SonoraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Sonora v2",
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
      ),
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
    text: "/Users/song/.squeezelite_gui/config.json",
  );
  final _navName = TextEditingController(text: "我的音乐服务器");
  final _navHost = TextEditingController(text: "192.168.199.2:4533");
  final _navCreds = TextEditingController(
    text: "/Users/song/navidrome_creds.json",
  );
  final _navUser = TextEditingController();
  final _navPass = TextEditingController();
  final _navSearch = TextEditingController();
  final _deviceNameCtrl = TextEditingController();
  final _playerNameCtrl = TextEditingController(text: "Sonora-UI");
  final _lmsNameCtrl = TextEditingController(text: "我的 LMS 服务器");
  final _latencyCtrl = TextEditingController(text: "10");
  final _ratesCtrl = TextEditingController(text: "44100-384000");
  final _streamBufCtrl = TextEditingController(text: "2048");
  final _outBufCtrl = TextEditingController(text: "3445");
  final _modelCtrl = TextEditingController();
  final _extraCtrl = TextEditingController();
  final _settingsStore = SettingsStore();
  late AppSettings _settings;
  OpenSubsonicServer? get _activeServer => _settings.activeServer;
  String get _currentServerName => _activeServer?.name ?? "我的音乐服务器";
  CoreParams _coreParams = const CoreParams();
  List<OutputDevice> _deviceOptions = <OutputDevice>[];
  String _activeLibrary = "lms";
  List<AlbumInfo> _lmsAlbums = <AlbumInfo>[];
  List<SongInfo> _lmsSongs = <SongInfo>[];
  AlbumInfo? _selectedLmsAlbum;
  List<LyricLine> _lyrics = <LyricLine>[];
  String _albumNote = "";
  String _artistBio = "";

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
  NavidromeAudio? _audio;
  bool _audioSubscribed = false;
  bool _autoAdvancing = false;
  String _source = "lms";
  SongInfo? _currentSong;
  AudioInfo? _audioInfo;
  String _lastAudioTrackId = "";

  /// 连接页当前展开配置的服务器 key："lms" 或 OpenSubsonic 的 server id。
  String _selectedServerKey = "lms";
  String _navStatusText = "未检测";
  bool _navConnected = false;

  // 升级页（主体 / 核心下载校验，不做自动替换）
  final _appZipUrl = TextEditingController();
  final _appSumsUrl = TextEditingController();
  String _appCurrent = "2.1.0";
  String _appLatest = "-";
  List<String> _appNotes = <String>[];
  VerifyResult? _appVerify;
  String _coreCurrent = "-";
  ReleaseAsset? _coreAsset;
  VerifyResult? _coreVerify;
  UpdateInstaller? _installer;
  InstallResult? _appInstall;
  InstallResult? _coreInstall;
  List<BackupRecord> _appBackups = <BackupRecord>[];
  List<BackupRecord> _coreBackups = <BackupRecord>[];
  String? _appBackupId;
  String? _coreBackupId;

  @override
  void initState() {
    super.initState();
    _settings = _settingsStore.load();
    _lmsNameCtrl.text = _settings.lmsName;
    _host.text = _settings.lmsHost;
    _port.text = _settings.lmsPort;
    _slim.text = _settings.slimPort;
    _user.text = _settings.lmsUser;
    _pass.text = _settings.lmsPassword;
    _lmsCreds.text = _settings.lmsCredsPath;
    _loadActiveServerIntoControllers();
    _appZipUrl.text = _settings.appZipUrl;
    _appSumsUrl.text = _settings.appSumsUrl;
    _activeLibrary = _settings.activeLibrary == "navidrome"
        ? "navidrome"
        : "lms";
    _source = _activeLibrary;
    _selectedServerKey = _activeLibrary == "lms"
        ? "lms"
        : _settings.activeServerId;
    _coreParams = _settings.coreParams;
    _syncParamControllers();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_scanOutputDevices());
    });
    WidgetsBinding.instance.addObserver(this);
    // Headless verification hook: SONORA_AUTO_CONNECT=1 makes the real UI
    // exercise the same connect path a user clicks, without GUI automation.
    final autoConnect = Platform.environment["SONORA_AUTO_CONNECT"] == "1";
    final autoPlay = Platform.environment["SONORA_AUTO_PLAY"] == "1";
    final autoUpdate = Platform.environment["SONORA_AUTO_UPDATE"] == "1";
    if (autoConnect || autoPlay || autoUpdate) {
      // ignore: avoid_print
      print("SONORA headless hooks armed");
      WidgetsBinding.instance.addPostFrameCallback((_) {
        // ignore: avoid_print
        print("SONORA headless hooks firing");
        if (autoUpdate) {
          final zip = Platform.environment["SONORA_APP_ZIP"] ?? "";
          final sums = Platform.environment["SONORA_APP_SUMS"] ?? "";
          final core = Platform.environment["SONORA_CORE_VERIFY"] == "1";
          unawaited(() async {
            await _initUpdates();
            if (zip.isNotEmpty) {
              _appZipUrl.text = zip;
              if (sums.isNotEmpty) _appSumsUrl.text = sums;
              await _verifyAppDownload();
              if (Platform.environment["SONORA_APP_INSTALL"] == "1") {
                await _installApp();
                if (Platform.environment["SONORA_ROLLBACK"] == "1") {
                  await _rollbackApp();
                }
              }
            }
            if (core) {
              await _verifyCoreDownload();
              if (Platform.environment["SONORA_CORE_INSTALL"] == "1") {
                await _installCore();
                if (Platform.environment["SONORA_ROLLBACK"] == "1") {
                  await _rollbackCore();
                }
              }
            }
          }());
        } else {
          unawaited(autoConnect ? _connect() : _autoPlayNavidrome());
        }
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    unawaited(_runner?.stop());
    unawaited(_audio?.dispose());
    for (final c in <TextEditingController>[
      _host,
      _port,
      _slim,
      _user,
      _pass,
      _lmsCreds,
      _lmsNameCtrl,
      _navName,
      _navHost,
      _navCreds,
      _navUser,
      _navPass,
      _navSearch,
      _deviceNameCtrl,
      _playerNameCtrl,
      _latencyCtrl,
      _ratesCtrl,
      _streamBufCtrl,
      _outBufCtrl,
      _modelCtrl,
      _extraCtrl,
      _appZipUrl,
      _appSumsUrl,
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
    final stamped =
        "${DateTime.now().toIso8601String().substring(11, 19)} $line";
    if (Platform.environment["SONORA_AUTO_CONNECT"] == "1" ||
        Platform.environment["SONORA_AUTO_PLAY"] == "1" ||
        Platform.environment["SONORA_AUTO_UPDATE"] == "1") {
      // ignore: avoid_print
      print(stamped);
    }
    if (!mounted) return;
    setState(() {
      _logs.add(stamped);
      if (_logs.length > 200) _logs.removeAt(0);
    });
  }

  /// 升级页初始化：读取当前版本，检查远端版本源。
  Future<void> _initUpdates() async {
    _appCurrent = _readAppVersion();
    _ensureInstaller();
    _reloadCoreVersion();
    _refreshBackups();
    await _checkUpdates();
  }

  /// 升级服务惰性初始化；headless 可用环境变量注入假安装目标。
  UpdateInstaller _ensureInstaller() {
    final existing = _installer;
    if (existing != null) return existing;
    final created = UpdateInstaller(
      appTarget: Platform.environment["SONORA_APP_TARGET"],
      coreTarget: Platform.environment["SONORA_CORE_TARGET"],
      onLog: _log,
    );
    _installer = created;
    return created;
  }

  /// 用户目录的 manifest 优先于 bundle 内置清单，反映真实已装核心。
  void _reloadCoreVersion() {
    final user = readCoreManifest(userCoreManifestPath());
    final bundledPath =
        CoreRunner.bundledCorePath()?.replaceFirst(
          "/squeezelite",
          "/core-manifest.json",
        ) ??
        "";
    final m = user ?? readCoreManifest(bundledPath);
    if (m == null) {
      _coreCurrent = "未知";
      return;
    }
    final v = (m["version"] ?? "未知").toString();
    final rev = m["revision"];
    _coreCurrent = rev == null ? v : "$v r$rev";
  }

  void _refreshBackups() {
    final ins = _ensureInstaller();
    final apps = ins.listBackups(UpdateTrack.app);
    final cores = ins.listBackups(UpdateTrack.core);
    if (!mounted) return;
    setState(() {
      _appBackups = apps;
      _coreBackups = cores;
      if (_appBackupId == null || !apps.any((b) => b.id == _appBackupId)) {
        _appBackupId = apps.isEmpty ? null : apps.first.id;
      }
      if (_coreBackupId == null || !cores.any((b) => b.id == _coreBackupId)) {
        _coreBackupId = cores.isEmpty ? null : cores.first.id;
      }
    });
  }

  Widget _backupSelector(
    List<BackupRecord> backups,
    String? value,
    ValueChanged<String?> onChanged,
  ) {
    final valid = value != null && backups.any((b) => b.id == value)
        ? value
        : null;
    return DropdownButton<String>(
      value: valid,
      hint: const Text("选择备份版本"),
      isExpanded: true,
      items: backups.map((b) {
        final when = b.createdAt.length >= 19
            ? b.createdAt.substring(0, 19).replaceFirst("T", " ")
            : b.createdAt;
        return DropdownMenuItem<String>(
          value: b.id,
          child: Text(
            "${b.version} · $when",
            style: const TextStyle(fontSize: 12),
          ),
        );
      }).toList(),
      onChanged: backups.isEmpty ? null : onChanged,
    );
  }

  String _readAppVersion() {
    // 优先从运行中的 bundle Info.plist 读取；开发态回退到 pubspec 常量。
    final exe = Platform.resolvedExecutable;
    final m = RegExp(r"(.*\.app)/Contents/MacOS/[^/]+$").firstMatch(exe);
    if (m != null) {
      try {
        final plist = File(
          "${m.group(1)}/Contents/Info.plist",
        ).readAsStringSync();
        final v = RegExp(
          r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>",
        ).firstMatch(plist)?.group(1);
        if (v != null && v.isNotEmpty) return v;
      } catch (_) {}
    }
    return "2.1.0";
  }

  Future<void> _checkUpdates() async {
    setState(() => _busy = true);
    try {
      final atom = await getText(
        "https://github.com/songboxiang/sonora/releases.atom",
      );
      final v = parseReleaseVersion(atom);
      if (!mounted) return;
      setState(() {
        _appLatest = v ?? "未知";
        _appNotes = parseReleaseNotes(atom);
      });
      _log("主体最新版本：${v ?? '未知'}");
    } catch (e) {
      _log("主体版本检查失败 ${e.toString().split("\n").first}");
      if (mounted) setState(() => _appLatest = "检查失败");
    }
    try {
      final rss = await getText(
        "https://sourceforge.net/projects/lmsclients/rss?path=/squeezelite/osx/m1",
      );
      final asset = parseCoreRss(rss);
      if (!mounted) return;
      setState(() => _coreAsset = asset);
      _log(
        "核心最新版本：${asset?.displayVersion ?? '未知'}"
        " ${asset != null && asset.md5.isNotEmpty ? 'md5 可用' : 'md5 缺失'}",
      );
    } catch (e) {
      _log("核心版本检查失败 ${e.toString().split("\n").first}");
    }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _verifyAppDownload() async {
    final zipUrl = _appZipUrl.text.trim();
    final sumsUrl = _appSumsUrl.text.trim();
    if (zipUrl.isEmpty) {
      _log("请填写主体 zip 下载地址");
      return;
    }
    setState(() {
      _busy = true;
      _appVerify = null;
    });
    _log("主体下载校验：$zipUrl");
    final r = await verifyAppArchive(
      zipUrl: zipUrl,
      sumsUrl: sumsUrl.isEmpty ? null : sumsUrl,
      onLog: _log,
    );
    if (!mounted) return;
    setState(() {
      _appVerify = r;
      _busy = false;
    });
    _log("主体校验${r.ok ? '通过' : '失败'}（${r.stage}）：${r.detail}");
  }

  Future<void> _verifyCoreDownload() async {
    final asset = _coreAsset;
    if (asset == null) {
      _log("请先检查更新以获取核心下载地址");
      return;
    }
    setState(() {
      _busy = true;
      _coreVerify = null;
    });
    _log("核心下载校验：${asset.filename}");
    final r = await verifyCoreArchive(release: asset, onLog: _log);
    if (!mounted) return;
    setState(() {
      _coreVerify = r;
      _busy = false;
    });
    _log("核心校验${r.ok ? '通过' : '失败'}（${r.stage}）：${r.detail}");
  }

  Future<void> _installApp() async {
    final v = _appVerify;
    if (v == null || !v.ok) {
      _log("请先下载并校验主体，再执行替换");
      return;
    }
    if (mounted) setState(() => _busy = true);
    final r = await _ensureInstaller().installApp(
      zipPath: v.path,
      expectedSha: v.sha256,
    );
    if (!mounted) return;
    setState(() {
      _appInstall = r;
      _busy = false;
    });
    _refreshBackups();
    _log("主体替换${r.ok ? '成功' : '失败'}（${r.stage}）：${r.detail}");
  }

  Future<void> _installCore() async {
    final v = _coreVerify;
    final asset = _coreAsset;
    if (v == null || !v.ok || v.binaryPath.isEmpty || asset == null) {
      _log("请先下载并校验核心，再执行替换");
      return;
    }
    final wasRunning = _runner?.isRunning ?? false;
    if (wasRunning) await _stopCore();
    if (mounted) setState(() => _busy = true);
    late final InstallResult r;
    try {
      r = await _ensureInstaller().installCore(
        verification: v,
        version: asset.version,
        revision: asset.revision,
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    if (wasRunning && r.ok && _target != null) await _startCore(_target!);
    if (!mounted) return;
    setState(() => _coreInstall = r);
    _reloadCoreVersion();
    _refreshBackups();
    _log("核心替换${r.ok ? '成功' : '失败'}（${r.stage}）：${r.detail}");
  }

  Future<void> _rollbackApp() async {
    final id = _appBackupId;
    if (id == null) {
      _log("没有可回滚的主体备份");
      return;
    }
    if (mounted) setState(() => _busy = true);
    final r = await _ensureInstaller().rollback(
      track: UpdateTrack.app,
      backupId: id,
    );
    if (!mounted) return;
    setState(() {
      _appInstall = r;
      _busy = false;
    });
    _refreshBackups();
    _log("主体回滚${r.ok ? '成功' : '失败'}（${r.stage}）：${r.detail}");
  }

  Future<void> _rollbackCore() async {
    final id = _coreBackupId;
    if (id == null) {
      _log("没有可回滚的核心备份");
      return;
    }
    final wasRunning = _runner?.isRunning ?? false;
    if (wasRunning) await _stopCore();
    if (mounted) setState(() => _busy = true);
    late final InstallResult r;
    try {
      r = await _ensureInstaller().rollback(
        track: UpdateTrack.core,
        backupId: id,
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    if (wasRunning && r.ok && _target != null) await _startCore(_target!);
    if (!mounted) return;
    setState(() => _coreInstall = r);
    _reloadCoreVersion();
    _refreshBackups();
    _log("核心回滚${r.ok ? '成功' : '失败'}（${r.stage}）：${r.detail}");
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

  CoreParams _collectParamsFromFields() {
    return _coreParams.copyWith(
      deviceName: _deviceNameCtrl.text.trim(),
      playerName: _playerNameCtrl.text.trim().isEmpty
          ? "Sonora-UI"
          : _playerNameCtrl.text.trim(),
      latencyMs: int.tryParse(_latencyCtrl.text.trim()) ?? 10,
      rates: _ratesCtrl.text.trim(),
      streamBufferKb: int.tryParse(_streamBufCtrl.text.trim()) ?? 2048,
      outputBufferKb: int.tryParse(_outBufCtrl.text.trim()) ?? 3445,
      modelName: _modelCtrl.text.trim(),
      extraArgs: _extraCtrl.text.trim(),
    );
  }

  void _syncParamControllers() {
    _deviceNameCtrl.text = _coreParams.deviceName;
    _playerNameCtrl.text = _coreParams.playerName;
    _latencyCtrl.text = _coreParams.latencyMs.toString();
    _ratesCtrl.text = _coreParams.rates;
    _streamBufCtrl.text = _coreParams.streamBufferKb.toString();
    _outBufCtrl.text = _coreParams.outputBufferKb.toString();
    _modelCtrl.text = _coreParams.modelName;
    _extraCtrl.text = _coreParams.extraArgs;
  }

  List<Widget> _serverListWidgets() {
    final items = <Widget>[
      Card(
        child: ListTile(
          selected: _selectedServerKey == "lms",
          leading: const Icon(Icons.dns_outlined),
          title: Text(_settings.lmsName),
          subtitle: Text(
            "${_settings.lmsHost}:${_settings.lmsPort} · $_lmsVersion",
          ),
          trailing: Wrap(
            spacing: 4,
            children: <Widget>[
              if (_activeLibrary != "lms")
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => unawaited(_switchLibrary("lms")),
                  child: const Text("切换"),
                ),
              TextButton(
                onPressed: () => unawaited(_selectServerConfig("lms")),
                child: const Text("修改"),
              ),
            ],
          ),
        ),
      ),
    ];
    for (final server in _settings.servers) {
      final active =
          _settings.activeServerId == server.id &&
          _activeLibrary == "navidrome";
      items.add(
        Card(
          child: ListTile(
            selected: _selectedServerKey == server.id,
            leading: const Icon(Icons.cloud_outlined),
            title: Text(server.name),
            subtitle: Text(
              server.host.isEmpty
                  ? "未设置地址"
                  : "${server.host} · ${server.id == _settings.activeServerId ? _navStatusText : "未选中"}",
            ),
            trailing: Wrap(
              spacing: 4,
              children: <Widget>[
                if (active && _selectedServerKey != server.id)
                  const Icon(Icons.check_circle, color: Colors.indigo),
                if (!active)
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => unawaited(_switchServer(server.id)),
                    child: const Text("切换"),
                  ),
                TextButton(
                  onPressed: () => unawaited(_selectServerConfig(server.id)),
                  child: const Text("修改"),
                ),
                IconButton(
                  tooltip: "删除服务器",
                  icon: const Icon(Icons.delete_outline),
                  onPressed: _settings.servers.length <= 1
                      ? null
                      : () => unawaited(_deleteServer(server.id)),
                ),
              ],
            ),
          ),
        ),
      );
    }
    items.add(
      OutlinedButton.icon(
        onPressed: _addServer,
        icon: const Icon(Icons.add),
        label: const Text("添加服务器"),
      ),
    );
    return items;
  }

  Future<void> _selectServerConfig(String key) async {
    if (key != "lms" && _selectedServerKey != "lms") {
      _syncActiveServerFromControllers();
    }
    if (key == "lms") {
      if (mounted) setState(() => _selectedServerKey = "lms");
      return;
    }
    final server = _settings.servers.firstWhere(
      (item) => item.id == key,
      orElse: () => _settings.servers.first,
    );
    if (mounted) {
      setState(() {
        _settings.activeServerId = server.id;
        _selectedServerKey = server.id;
      });
    } else {
      _settings.activeServerId = server.id;
      _selectedServerKey = server.id;
    }
    _loadActiveServerIntoControllers();
    await _saveSettings();
    await _testNavConnection();
  }

  Future<void> _testNavConnection() async {
    final target = _navidromeTarget();
    if (target == null) {
      if (mounted) {
        setState(() {
          _navConnected = false;
          _navStatusText = "未连接 · 凭证不完整";
        });
      }
      return;
    }
    if (mounted) setState(() => _busy = true);
    try {
      final info = await probeNavidrome(
        target,
        onError: (m) => _log("OpenSubsonic $m"),
      );
      if (!mounted) return;
      setState(() {
        _navConnected = info.reachable;
        _navStatusText = info.reachable
            ? "已连接 · ${info.version.isEmpty ? "未知版本" : info.version}"
            : "未连接 · ${info.statusText}";
      });
      _log("$_currentServerName $_navStatusText");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  List<Widget> _serverDetailWidgets() {
    void markCustom() {
      if (_coreParams.profile != "custom") {
        _coreParams = _coreParams.copyWith(profile: "custom");
      }
    }

    if (_selectedServerKey != "lms") {
      return <Widget>[
        const Text("服务器配置", style: TextStyle(fontWeight: FontWeight.bold)),
        const SizedBox(height: 6),
        _field("服务器名称", _navName),
        _field("地址（IP:端口）", _navHost),
        _field("账号", _navUser),
        _field("密码", _navPass, obscure: true),
        _field("凭证路径（账号密码为空时读取）", _navCreds),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: <Widget>[
            ElevatedButton.icon(
              onPressed: _busy ? null : () => unawaited(_testNavConnection()),
              icon: const Icon(Icons.link),
              label: const Text("测试连接"),
            ),
            OutlinedButton.icon(
              onPressed: () => unawaited(_saveSettings()),
              icon: const Icon(Icons.save),
              label: const Text("保存配置"),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          _navStatusText,
          style: TextStyle(
            color: _navConnected ? Colors.green.shade700 : Colors.grey.shade700,
          ),
        ),
      ];
    }

    return <Widget>[
      const Text("服务器配置", style: TextStyle(fontWeight: FontWeight.bold)),
      const SizedBox(height: 6),
      _field("服务器名称", _lmsNameCtrl),
      _field("主机", _host),
      _field("JSON-RPC 端口", _port),
      _field("slimproto 端口", _slim),
      _field("用户名（可留空，用配置文件）", _user),
      _field("密码", _pass, obscure: true),
      _field("旧配置路径（只读导入）", _lmsCreds),
      const SizedBox(height: 8),
      Wrap(
        spacing: 8,
        runSpacing: 8,
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
          OutlinedButton.icon(
            onPressed: () => unawaited(_saveSettings()),
            icon: const Icon(Icons.save),
            label: const Text("保存配置"),
          ),
        ],
      ),
      const Divider(),
      const Text("输出设备", style: TextStyle(fontWeight: FontWeight.bold)),
      Wrap(
        spacing: 8,
        children: <Widget>[
          ElevatedButton.icon(
            onPressed: () => unawaited(_scanOutputDevices()),
            icon: const Icon(Icons.radar),
            label: const Text("扫描设备"),
          ),
        ],
      ),
      if (_deviceOptions.isEmpty)
        const Text(
          "尚未扫描。上一次使用的设备会自动作为默认值；点「扫描设备」列出可用输出。",
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
      DropdownButtonFormField<String>(
        initialValue: _deviceOptions.any((d) => d.name == _coreParams.device)
            ? _coreParams.device
            : null,
        hint: const Text("选择输出设备（-o）"),
        isExpanded: true,
        items: _deviceOptions
            .map(
              (d) =>
                  DropdownMenuItem<String>(value: d.name, child: Text(d.name)),
            )
            .toList(),
        onChanged: _deviceOptions.isEmpty
            ? null
            : (v) {
                if (v == null) return;
                setState(
                  () => _coreParams = _coreParams.copyWith(
                    device: v,
                    deviceName: v,
                    profile: "custom",
                  ),
                );
              },
      ),
      _helpText("device"),
      _field("设备显示名称（重命名）", _deviceNameCtrl, onChanged: (_) => markCustom()),
      _helpText("deviceName"),
      const Divider(),
      const Text("参数配置", style: TextStyle(fontWeight: FontWeight.bold)),
      Wrap(
        spacing: 8,
        children: coreProfiles.entries
            .map(
              (e) => FilterChip(
                label: Text(e.value),
                selected: _coreParams.profile == e.key,
                onSelected: (_) => _applyCoreProfile(e.key),
              ),
            )
            .toList(),
      ),
      const SizedBox(height: 8),
      _field("播放器名称（-n）", _playerNameCtrl, onChanged: (_) => markCustom()),
      _helpText("playerName"),
      _field("目标延迟毫秒（-a 第一段）", _latencyCtrl, onChanged: (_) => markCustom()),
      _helpText("latencyMs"),
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text("允许 macOS 重采样（-a 第二段）"),
        value: _coreParams.allowResample,
        onChanged: (v) => setState(
          () => _coreParams = _coreParams.copyWith(
            allowResample: v,
            profile: "custom",
          ),
        ),
      ),
      _helpText("allowResample"),
      _field("支持采样率（-r）", _ratesCtrl, onChanged: (_) => markCustom()),
      _helpText("rates"),
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text("DSD over PCM 直通（-D）"),
        value: _coreParams.dop,
        onChanged: (v) => setState(
          () => _coreParams = _coreParams.copyWith(dop: v, profile: "custom"),
        ),
      ),
      _helpText("dop"),
      Row(
        children: <Widget>[
          Expanded(
            child: _field(
              "流缓冲 KB",
              _streamBufCtrl,
              onChanged: (_) => markCustom(),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: _field(
              "输出缓冲 KB",
              _outBufCtrl,
              onChanged: (_) => markCustom(),
            ),
          ),
        ],
      ),
      _helpText("buffers"),
      _field("播放器型号（-M，可留空）", _modelCtrl, onChanged: (_) => markCustom()),
      _helpText("modelName"),
      _field("额外参数", _extraCtrl, onChanged: (_) => markCustom()),
      _helpText("extraArgs"),
    ];
  }

  List<Widget> _lmsLibraryWidgets() {
    return <Widget>[
      Row(
        children: <Widget>[
          Text("LMS 专辑 ${_lmsAlbums.length} 张"),
          const Spacer(),
          ElevatedButton.icon(
            onPressed: _busy ? null : () => unawaited(_loadLmsAlbums()),
            icon: const Icon(Icons.refresh),
            label: const Text("加载专辑"),
          ),
        ],
      ),
      if (_selectedLmsAlbum != null) _infoCard("当前专辑", _selectedLmsAlbum!.name),
      ..._lmsAlbums.map(
        (a) => ListTile(
          leading: const CircleAvatar(child: Icon(Icons.album)),
          title: Text(a.name),
          subtitle: Text(a.artist.isEmpty ? "未知艺人" : a.artist),
          onTap: () => unawaited(_loadLmsSongs(a)),
        ),
      ),
      const Divider(),
      Text("歌曲 ${_lmsSongs.length} 首"),
      ..._lmsSongs.map(
        (s) => ListTile(
          title: Text(s.title),
          subtitle: Text(
            "${s.artist.isEmpty ? '未知艺人' : s.artist} · ${formatDuration(s.duration)}",
          ),
          trailing: const Icon(Icons.play_arrow),
          onTap: () => unawaited(_playLmsSong(s)),
        ),
      ),
    ];
  }

  List<Widget> _navLibraryWidgets() {
    return <Widget>[
      Row(
        children: <Widget>[
          Expanded(child: _field("搜索歌曲 / 专辑", _navSearch)),
          const SizedBox(width: 8),
          ElevatedButton.icon(
            onPressed: _busy ? null : () => unawaited(_searchNavidrome()),
            icon: const Icon(Icons.search),
            label: const Text("搜索"),
          ),
        ],
      ),
      const SizedBox(height: 8),
      ElevatedButton.icon(
        onPressed: _busy ? null : () => unawaited(_loadAlbums()),
        icon: const Icon(Icons.library_music_outlined),
        label: const Text("加载专辑"),
      ),
      const Divider(),
      Text("专辑 ${_albums.length} 张 · $_currentServerName（入口以专辑为准）"),
      if (_albumNote.isNotEmpty) _infoCard("专辑简介", _albumNote),
      if (_artistBio.isNotEmpty) _infoCard("艺人简介", _artistBio),
      ..._albums.map(
        (a) => ListTile(
          leading: a.coverUrl.isEmpty
              ? null
              : CircleAvatar(backgroundImage: NetworkImage(a.coverUrl)),
          title: Text(a.name),
          subtitle: Text(a.artist.isEmpty ? "未知艺人" : a.artist),
          onTap: () => unawaited(_loadSongs(a)),
        ),
      ),
      const Divider(),
      Text("歌曲 ${_songs.length} 首"),
      ..._songs.map(
        (s) => ListTile(
          leading: s.coverUrl.isEmpty
              ? null
              : CircleAvatar(backgroundImage: NetworkImage(s.coverUrl)),
          title: Text(s.title),
          subtitle: Text(
            "${s.artist.isEmpty ? '未知艺人' : s.artist} · ${formatDuration(s.duration)}",
          ),
          trailing: const Icon(Icons.play_arrow),
          onTap: () => unawaited(_playNavidromeSong(s)),
        ),
      ),
    ];
  }

  Widget _helpText(String key) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        coreParamHelp[key] ?? "",
        style: const TextStyle(fontSize: 11, color: Colors.grey),
      ),
    );
  }

  void _loadActiveServerIntoControllers() {
    final s = _activeServer;
    final creds = s?.credsPath ?? "";
    _navName.text = s?.name ?? "我的音乐服务器";
    _navHost.text = s?.host ?? "";
    _navUser.text = s?.user ?? "";
    _navPass.text = s?.password ?? "";
    _navCreds.text = creds.isEmpty && (s?.user ?? "").isEmpty
        ? defaultNavCredsPath
        : creds;
  }

  void _syncActiveServerFromControllers() {
    final s = _activeServer;
    final name = _navName.text.trim().isEmpty
        ? "我的音乐服务器"
        : _navName.text.trim();
    final host = _navHost.text.trim();
    final user = _navUser.text.trim();
    final password = _navPass.text;
    var credsPath = _navCreds.text.trim();
    if (credsPath.isEmpty && user.isEmpty && password.isEmpty) {
      credsPath = defaultNavCredsPath;
      _navCreds.text = credsPath;
    }
    if (s == null) {
      final created = OpenSubsonicServer(
        id: "default",
        name: name,
        host: host,
        user: user,
        password: password,
        credsPath: credsPath,
      );
      _settings.servers.add(created);
      _settings.activeServerId = created.id;
      return;
    }
    final index = _settings.servers.indexWhere((item) => item.id == s.id);
    if (index >= 0) {
      _settings.servers[index] = s.copyWith(
        name: name,
        host: host,
        user: user,
        password: password,
        credsPath: credsPath,
      );
    }
  }

  void _addServer() {
    _syncActiveServerFromControllers();
    final id = DateTime.now().microsecondsSinceEpoch.toString();
    final created = OpenSubsonicServer(
      id: id,
      name: "新服务器 ${_settings.servers.length + 1}",
      host: _navHost.text.trim(),
      user: _navUser.text.trim(),
      password: _navPass.text,
      credsPath: _navCreds.text.trim(),
    );
    if (mounted) {
      setState(() {
        _settings.servers.add(created);
        _settings.activeServerId = id;
        _selectedServerKey = id;
      });
    } else {
      _settings.servers.add(created);
      _settings.activeServerId = id;
      _selectedServerKey = id;
    }
    _loadActiveServerIntoControllers();
    _log("已添加服务器，请修改名称与地址后保存");
  }

  Future<void> _deleteServer(String id) async {
    if (_settings.servers.length <= 1) {
      _log("至少保留一台服务器");
      return;
    }
    _syncActiveServerFromControllers();
    final removed = _settings.servers.firstWhere(
      (s) => s.id == id,
      orElse: () => _settings.servers.first,
    );
    if (mounted) {
      setState(() {
        _settings.servers.removeWhere((s) => s.id == id);
        if (_settings.activeServerId == id) {
          _settings.activeServerId = _settings.servers.first.id;
        }
        if (_selectedServerKey == id) {
          _selectedServerKey = _settings.servers.first.id;
        }
      });
    } else {
      _settings.servers.removeWhere((s) => s.id == id);
      if (_settings.activeServerId == id) {
        _settings.activeServerId = _settings.servers.first.id;
      }
      if (_selectedServerKey == id) {
        _selectedServerKey = _settings.servers.first.id;
      }
    }
    _loadActiveServerIntoControllers();
    await _saveSettings();
    if (_activeLibrary == "navidrome") await _loadAlbums();
    _log("已删除服务器：${removed.name}");
  }

  Future<void> _saveSettings() async {
    _coreParams = _collectParamsFromFields();
    _syncActiveServerFromControllers();
    _settings
      ..lmsName = _lmsNameCtrl.text.trim().isEmpty
          ? "我的 LMS 服务器"
          : _lmsNameCtrl.text.trim()
      ..lmsHost = _host.text.trim()
      ..lmsPort = _port.text.trim()
      ..slimPort = _slim.text.trim()
      ..lmsUser = _user.text.trim()
      ..lmsPassword = _pass.text
      ..lmsCredsPath = _lmsCreds.text.trim()
      ..activeLibrary = _activeLibrary
      ..appZipUrl = _appZipUrl.text.trim()
      ..appSumsUrl = _appSumsUrl.text.trim()
      ..coreParams = _coreParams;
    try {
      await _settingsStore.save(_settings);
      _log(
        "配置已保存（上次输出设备：${_coreParams.device.isEmpty ? '默认' : _coreParams.device}）",
      );
    } catch (e) {
      _log("配置保存失败 ${e.toString().split("\n").first}");
    }
  }

  Future<void> _scanOutputDevices() async {
    var core = CoreRunner.userCorePath();
    if (!File(core).existsSync()) {
      final bundled = CoreRunner.bundledCorePath();
      if (bundled != null && File(bundled).existsSync()) core = bundled;
    }
    if (!File(core).existsSync()) {
      _log("找不到核心二进制，无法扫描输出设备");
      return;
    }
    try {
      final r = await Process.run(core, [
        "-l",
      ]).timeout(const Duration(seconds: 8));
      final devices = parseOutputDevices("${r.stdout}\n${r.stderr}");
      if (!mounted) return;
      setState(() {
        _deviceOptions = devices;
        if (devices.isNotEmpty &&
            !devices.any(
              (d) => d.id == _coreParams.device || d.name == _coreParams.device,
            )) {
          _coreParams = _coreParams.copyWith(
            device: devices.first.name,
            deviceName: devices.first.name,
            profile: "custom",
          );
        }
      });
      _log("扫描到 ${devices.length} 个输出设备");
    } catch (e) {
      _log("设备扫描失败 ${e.toString().split("\n").first}");
    }
  }

  void _applyCoreProfile(String profile) {
    final p = paramsForProfile(profile, base: _collectParamsFromFields());
    setState(() => _coreParams = p);
    _syncParamControllers();
    _log("已套用音质预设：${coreProfiles[profile] ?? profile}");
  }

  Future<void> _switchServer(String id) async {
    if (id == _settings.activeServerId && _activeLibrary == "navidrome") {
      _log("已经是当前服务器：$_currentServerName");
      return;
    }
    if (mounted) setState(() => _busy = true);
    try {
      _syncActiveServerFromControllers();
      final server = _settings.servers.firstWhere(
        (s) => s.id == id,
        orElse: () => _settings.servers.first,
      );
      if (mounted) {
        setState(() {
          _settings.activeServerId = server.id;
          _selectedServerKey = server.id;
          _activeLibrary = "navidrome";
          _source = "navidrome";
          _audioInfo = _currentSong?.audio;
          _albums = const <AlbumInfo>[];
          _songs = const <SongInfo>[];
          _albumNote = "";
          _artistBio = "";
          _lyrics = const <LyricLine>[];
        });
      } else {
        _settings.activeServerId = server.id;
        _selectedServerKey = server.id;
        _activeLibrary = "navidrome";
        _source = "navidrome";
        _audioInfo = _currentSong?.audio;
        _albums = const <AlbumInfo>[];
        _songs = const <SongInfo>[];
        _albumNote = "";
        _artistBio = "";
        _lyrics = const <LyricLine>[];
      }
      _loadActiveServerIntoControllers();
      await _stopCore();
      await _saveSettings();
      await _loadAlbums();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _switchLibrary(String id) async {
    if (id != "lms" && id != "navidrome") return;
    if (id == _activeLibrary) {
      _log("已经在 ${id == "lms" ? "LMS" : "OpenSubsonic"} 曲库");
      return;
    }
    if (mounted) setState(() => _busy = true);
    try {
      if (id == "lms") {
        await _audio?.stop();
        if (!mounted) return;
        setState(() {
          _activeLibrary = "lms";
          _source = "lms";
          _selectedServerKey = "lms";
          _audioInfo = const AudioInfo();
          _lastAudioTrackId = "";
        });
        _log("切换到 LMS 曲库，自动开启引擎");
        await _connect();
        await _loadLmsAlbums();
      } else {
        await _stopCore();
        if (!mounted) return;
        setState(() {
          _activeLibrary = "navidrome";
          _source = "navidrome";
          _audioInfo = _currentSong?.audio;
        });
        _log("切换到 OpenSubsonic 曲库（$_currentServerName），引擎已自动关闭");
        await _loadAlbums();
      }
      await _saveSettings();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadLmsAlbums() async {
    final target = _target;
    if (target == null) {
      _log("请先连接 LMS 再加载曲库");
      return;
    }
    if (mounted) setState(() => _busy = true);
    try {
      final albums = await fetchLmsAlbums(target, onError: _log);
      if (!mounted) return;
      setState(() {
        _lmsAlbums = albums;
        _lmsSongs = const <SongInfo>[];
        _selectedLmsAlbum = null;
      });
      _log("LMS 专辑 ${albums.length} 张");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadLmsSongs(AlbumInfo album) async {
    final target = _target;
    if (target == null) return;
    final songs = await fetchLmsTracks(
      target,
      album: album.name,
      onError: _log,
    );
    if (!mounted) return;
    setState(() {
      _selectedLmsAlbum = album;
      _lmsSongs = songs;
    });
    _log("$_currentServerName / ${album.name}：${songs.length} 首");
  }

  Future<void> _playLmsSong(SongInfo song) async {
    final target = _target;
    final playerId = _playerId;
    if (target == null || playerId == null) {
      _log("没有可用的 LMS 播放器，请先连接并等待核心注册");
      return;
    }
    final ok = await playLmsTrack(target, playerId, song.id, onError: _log);
    _lastAudioTrackId = "";
    _log(ok ? "LMS 播放：${song.title}" : "LMS 播放失败：${song.title}");
    unawaited(_refreshStatus());
  }

  Future<void> _connect() async {
    setState(() => _busy = true);
    try {
      await _audio?.stop();
      if (!mounted) return;
      setState(() => _source = "lms");
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
    final playerName = _coreParams.playerName;
    final runner = CoreRunner(
      lmsHost: target.host,
      lmsPort: target.port,
      slimPort: target.slimPort,
      playerName: playerName,
      params: _coreParams,
      onLog: _log,
    );
    _runner = runner;
    setState(() => _coreStatus = "启动中...");
    try {
      final p = await runner.start();
      if (!mounted) return;
      setState(() => _coreStatus = "已启动 pid=${p.pid}");
      _log(
        "核心已自动拉起 pid=${p.pid}（设备 ${_coreParams.device.isEmpty ? '默认' : _coreParams.device}）",
      );
      await _saveSettings();

      final before = await lmsPlayerCount(
        target,
        onError: (m) => _log("播放器 $m"),
      );
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

  PlaybackStatus _navStatus({
    required int position,
    int? duration,
    required bool playing,
  }) {
    final song = _currentSong;
    return PlaybackStatus(
      mode: playing ? "play" : "pause",
      title: song?.title ?? "",
      artist: song?.artist ?? "",
      album: song?.album ?? "",
      duration: duration ?? song?.duration ?? 0,
      position: position,
      volume: _volume,
      artworkUrl: song?.coverUrl ?? "",
    );
  }

  void _subscribeAudio() {
    if (_audioSubscribed || _audio == null) return;
    _audioSubscribed = true;
    _audio!.positionStream.listen((p) {
      if (!mounted || _source != "navidrome") return;
      setState(() {
        _status = _navStatus(
          position: p.inSeconds,
          duration: _audio?.duration?.inSeconds,
          playing: _audio?.isPlaying ?? false,
        );
      });
    });
    _audio!.durationStream.listen((d) {
      if (!mounted || _source != "navidrome" || d == null) return;
      setState(() {
        _status = _navStatus(
          position: _audio?.position.inSeconds ?? 0,
          duration: d.inSeconds,
          playing: _audio?.isPlaying ?? false,
        );
      });
    });
    _audio!.stateStream.listen((s) {
      if (!mounted || _source != "navidrome") return;
      setState(() {
        _status = _navStatus(
          position: _audio?.position.inSeconds ?? 0,
          duration: _audio?.duration?.inSeconds,
          playing: s.playing,
        );
      });
      if (s.processingState == ProcessingState.completed &&
          !_autoAdvancing &&
          _songs.isNotEmpty) {
        _autoAdvancing = true;
        _log("当前曲目结束，自动播放下一首");
        unawaited(
          _skipNavidrome(1).whenComplete(() {
            _autoAdvancing = false;
          }),
        );
      }
    });
  }

  Future<void> _playNavidromeSong(SongInfo song) async {
    final target = _navidromeTarget();
    if (target == null) return;
    await _stopCore();
    _audio ??= NavidromeAudio(onLog: _log);
    if (!mounted) return;
    setState(() {
      _source = "navidrome";
      _currentSong = song;
      _audioInfo = song.audio;
      _status = _navStatus(position: 0, playing: true);
    });
    _subscribeAudio();
    _log("OpenSubsonic 播放：${song.title}");
    final lines = await fetchNavidromeLyrics(target, song.id, onError: _log);
    if (!mounted) return;
    setState(() => _lyrics = lines);
    try {
      await _audio!.playSong(host: target.host, auth: target.auth, song: song);
      await _audio!.setVolume(_volume / 100.0);
    } catch (e) {
      _log("OpenSubsonic 播放失败 ${e.toString().split('\n').first}");
    }
  }

  Future<void> _togglePlay() async {
    if (_source == "navidrome") {
      final a = _audio;
      if (a == null) return;
      if (a.isPlaying) {
        await a.pause();
      } else {
        await a.resume();
      }
      if (!mounted) return;
      setState(() {
        _status = _navStatus(
          position: a.position.inSeconds,
          duration: a.duration?.inSeconds,
          playing: a.isPlaying,
        );
      });
      return;
    }
    await _command(
      _status.isPlaying ? ["pause"] : ["play"],
      _status.isPlaying ? "暂停" : "播放",
    );
  }

  Future<void> _seek(int seconds) async {
    if (_source == "navidrome") {
      await _audio?.seek(Duration(seconds: seconds));
      return;
    }
    await _command(["seek", seconds.toString()], "跳转");
  }

  Future<void> _setVolume(int value) async {
    if (_source == "navidrome") {
      await _audio?.setVolume(value / 100.0);
      return;
    }
    await _command([
      "mixer",
      "volume",
      sliderToLms(value).toString(),
    ], "音量 $value");
  }

  Future<void> _skip(int delta) async {
    if (_source == "navidrome") {
      await _skipNavidrome(delta);
      return;
    }
    await _command([
      "playlist",
      "jump",
      delta > 0 ? "+1" : "-1",
    ], delta > 0 ? "下一首" : "上一首");
  }

  Future<void> _skipNavidrome(int delta) async {
    if (_songs.isEmpty) return;
    final i = _songs.indexOf(_currentSong ?? _songs.first);
    final next = (i + delta) % _songs.length;
    await _playNavidromeSong(_songs[next]);
  }

  Future<void> _autoPlayNavidrome() async {
    await _loadAlbums();
    if (_albums.isEmpty) {
      _log("自动播放失败：没有专辑");
      return;
    }
    final target = _navidromeTarget();
    if (target == null) return;
    final songs = await fetchNavidromeAlbum(
      target,
      _albums.first.id,
      onError: (m) => _log("专辑详情 $m"),
    );
    if (songs.isEmpty) {
      _log("自动播放失败：没有歌曲");
      return;
    }
    await _playNavidromeSong(songs.first);
    await Future.delayed(const Duration(seconds: 3));
    final d = _audio?.duration;
    if (d != null && d.inSeconds > 2) {
      final targetSec = d.inSeconds ~/ 2;
      await _audio!.seek(Duration(seconds: targetSec));
      _log("自动播放 seek 到 ${targetSec}s / ${d.inSeconds}s");
      await Future.delayed(const Duration(seconds: 1));
      _log("自动播放 seek 后位置 ${_audio?.position.inSeconds}s");
    } else {
      _log("自动播放无有效 duration，跳过 seek");
    }
  }

  Future<void> _refreshLmsAudioInfo(String trackId) async {
    final target = _target;
    if (target == null || trackId.isEmpty) return;
    final info = await fetchLmsTrackAudioInfo(
      target,
      trackId,
      onError: (m) => _log("音质信息 $m"),
    );
    if (!mounted) return;
    setState(() => _audioInfo = info);
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
    if (s.trackId.isNotEmpty && s.trackId != _lastAudioTrackId) {
      _lastAudioTrackId = s.trackId;
      unawaited(_refreshLmsAudioInfo(s.trackId));
    }
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
    _syncActiveServerFromControllers();
    final host = _navHost.text.trim();
    if (host.isEmpty) {
      _log("请先填写 OpenSubsonic 服务器地址");
      return null;
    }
    var credsPath = _navCreds.text.trim();
    if (credsPath.isEmpty) {
      credsPath = defaultNavCredsPath;
      _navCreds.text = credsPath;
    }
    var user = _navUser.text.trim();
    var pass = _navPass.text;
    if (user.isEmpty || pass.isEmpty) {
      final c = readCreds(credsPath);
      user = c["user"] ?? c["lms_user"] ?? "";
      pass = c["password"] ?? c["pass"] ?? "";
    }
    if (user.isEmpty || pass.isEmpty) {
      _navStatusText = "未连接 · 凭证不完整";
      _navConnected = false;
      _log("OpenSubsonic 服务器 $_currentServerName 凭证不完整：$credsPath");
      return null;
    }
    return NavidromeTarget(
      host: host,
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
      final info = await probeNavidrome(
        target,
        onError: (m) => _log("OpenSubsonic $m"),
      );
      _log(
        "OpenSubsonic 服务器 $_currentServerName "
        "${info.version.isEmpty ? "未知版本" : info.version} "
        "${info.reachable ? "ok" : "失败"}",
      );
      final albums = await fetchNavidromeAlbums(
        target,
        onError: (m) => _log("曲库 $m"),
      );
      if (!mounted) return;
      setState(() {
        _albums = albums;
        _songs = const <SongInfo>[];
        _navConnected = info.reachable;
        _navStatusText = info.reachable
            ? "已连接 · ${info.version.isEmpty ? "未知版本" : info.version} · ${albums.length} 张专辑"
            : "未连接 · ${info.statusText}";
      });
      _log("$_currentServerName 专辑 ${albums.length} 张");
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
    final note = await fetchNavidromeAlbumNote(target, album.id, onError: _log);
    final bio = await fetchNavidromeArtistBio(
      target,
      album.artistId,
      onError: _log,
    );
    if (!mounted) return;
    setState(() {
      _songs = songs;
      _albumNote = note;
      _artistBio = bio;
      _lyrics = const <LyricLine>[];
    });
    _log("$_currentServerName / ${album.name}：${songs.length} 首");
  }

  Future<void> _searchNavidrome() async {
    final target = _navidromeTarget();
    if (target == null) return;
    final query = _navSearch.text.trim();
    if (query.isEmpty) {
      await _loadAlbums();
      return;
    }
    if (mounted) setState(() => _busy = true);
    final r = await searchNavidrome(target, query, onError: _log);
    if (!mounted) return;
    setState(() {
      _albums = r.albums;
      _songs = r.songs;
      _albumNote = "";
      _artistBio = "";
      _lyrics = const <LyricLine>[];
      _busy = false;
    });
    _log(
      "$_currentServerName 搜索 $query：专辑 ${r.albums.length} / 歌曲 ${r.songs.length}",
    );
  }

  int _currentLyricIndex() {
    if (_lyrics.isEmpty) return -1;
    final ms = _status.position * 1000;
    var found = -1;
    for (var i = 0; i < _lyrics.length; i++) {
      if (_lyrics[i].timeMs <= ms) {
        found = i;
      } else {
        break;
      }
    }
    return found;
  }

  Widget _infoCard(String title, String body) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.all(8),
      color: Colors.grey.shade200,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text(body, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }

  Widget _field(
    String label,
    TextEditingController controller, {
    bool obscure = false,
    void Function(String)? onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: TextField(
        controller: controller,
        obscureText: obscure,
        onChanged: onChanged,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
          isDense: true,
        ),
      ),
    );
  }

  Widget _qualityCard() {
    final isLms = _source != "navidrome";
    final modeText = isLms
        ? (_coreParams.allowResample
              ? "允许 macOS 重采样（-a ${_coreParams.latencyMs}:1）"
              : "完美码率直通（-a ${_coreParams.latencyMs}:0）")
        : "客户端流解码（不经 squeezelite）";
    final modeColor = isLms
        ? (_coreParams.allowResample
              ? Colors.orange.shade700
              : Colors.green.shade700)
        : Colors.indigo;
    final device = isLms
        ? (_coreParams.deviceName.isNotEmpty
              ? _coreParams.deviceName
              : _coreParams.device)
        : "just_audio · $_currentServerName";
    final audio = _audioInfo;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(Icons.high_quality_outlined, color: modeColor, size: 18),
                const SizedBox(width: 6),
                const Text(
                  "当前播放效果",
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 6),
            _statusRow("输出模式", modeText),
            _statusRow("音质", audio == null ? "-" : audio.summary),
            _statusRow(
              "无损",
              audio == null ? "-" : (audio.lossless ? "是" : "否 / 未知"),
            ),
            _statusRow("输出", device.isEmpty ? "-" : device),
          ],
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
      length: 4,
      child: Scaffold(
        key: _scaffoldKey,
        appBar: AppBar(
          title: const Text("Sonora v2"),
          bottom: const TabBar(
            tabs: <Widget>[
              Tab(text: "连接"),
              Tab(text: "播放"),
              Tab(text: "曲库"),
              Tab(text: "升级"),
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
                      style: const TextStyle(
                        fontSize: 11,
                        fontFamily: "monospace",
                      ),
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
                  const Text(
                    "音乐服务器",
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 8),
                  ..._serverListWidgets(),
                  const Divider(),
                  ..._serverDetailWidgets(),
                  if (_busy) const LinearProgressIndicator(),
                  const Divider(),
                  _statusRow("LMS 版本", _lmsVersion),
                  _statusRow("播放器数量", _playerCount < 0 ? "-" : "$_playerCount"),
                  _statusRow("核心状态", _coreStatus),
                  _statusRow("OpenSubsonic 状态", _navStatusText),
                  _statusRow(
                    "当前曲库",
                    _activeLibrary == "lms"
                        ? "LMS"
                        : "OpenSubsonic · $_currentServerName",
                  ),
                  _statusRow(
                    "输出设备",
                    _coreParams.deviceName.isEmpty
                        ? "默认"
                        : _coreParams.deviceName,
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    "服务器列表可切换/添加/修改/删除；选中一台后，下方显示它自己的配置。"
                    "本地音质参数与输出设备只属于 LMS 服务器。",
                    style: TextStyle(fontSize: 12, color: Colors.grey),
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
                    "音源：${_source == "navidrome" ? "OpenSubsonic 客户端流（$_currentServerName）" : "LMS 外部播放器"}",
                  ),
                  Text(
                    _status.title.isEmpty ? "未播放" : _status.title,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  Text(_status.artist.isEmpty ? "" : "艺人：${_status.artist}"),
                  Text(_status.album.isEmpty ? "" : "专辑：${_status.album}"),
                  _qualityCard(),
                  if (_source == "navidrome" &&
                      _currentSong != null &&
                      _currentSong!.coverUrl.isNotEmpty)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.network(
                        _currentSong!.coverUrl,
                        width: 140,
                        height: 140,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => const SizedBox(
                          width: 140,
                          height: 140,
                          child: Icon(Icons.album),
                        ),
                      ),
                    ),
                  const SizedBox(height: 12),
                  Text(
                    "${formatDuration(_status.position)} / ${formatDuration(_status.duration)}",
                  ),
                  Slider(
                    value: _status.duration == 0
                        ? 0
                        : (_status.position > _status.duration
                              ? _status.duration.toDouble()
                              : _status.position.toDouble()),
                    max: _status.duration == 0
                        ? 1
                        : _status.duration.toDouble(),
                    onChanged: (_) {},
                    onChangeEnd: (v) => unawaited(_seek(v.round())),
                  ),
                  if (_source == "navidrome" && _lyrics.isNotEmpty) ...<Widget>[
                    const Text(
                      "歌词",
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                    SizedBox(
                      height: 140,
                      child: ListView.builder(
                        itemCount: _lyrics.length,
                        itemBuilder: (context, i) {
                          final active = i == _currentLyricIndex();
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 3),
                            child: Text(
                              _lyrics[i].text,
                              style: TextStyle(
                                fontSize: 13,
                                color: active
                                    ? Colors.indigo
                                    : Colors.grey.shade700,
                                fontWeight: active
                                    ? FontWeight.bold
                                    : FontWeight.normal,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                  const SizedBox(height: 8),
                  Row(
                    children: <Widget>[
                      IconButton(
                        icon: const Icon(Icons.skip_previous),
                        onPressed: () => unawaited(_skip(-1)),
                      ),
                      IconButton(
                        icon: Icon(
                          _status.isPlaying
                              ? Icons.pause_circle_filled
                              : Icons.play_circle_filled,
                        ),
                        iconSize: 40,
                        onPressed: () => unawaited(_togglePlay()),
                      ),
                      IconButton(
                        icon: const Icon(Icons.skip_next),
                        onPressed: () => unawaited(_skip(1)),
                      ),
                    ],
                  ),
                  if (_source == "navidrome" && _songs.isNotEmpty) ...<Widget>[
                    const Divider(),
                    Text("播放队列 ${_songs.length} 首"),
                    SizedBox(
                      height: 150,
                      child: ListView.builder(
                        itemCount: _songs.length,
                        itemBuilder: (context, i) {
                          final song = _songs[i];
                          final active = song.id == _currentSong?.id;
                          return ListTile(
                            dense: true,
                            selected: active,
                            leading: Text("${i + 1}"),
                            title: Text(song.title),
                            subtitle: Text(
                              song.artist.isEmpty ? "未知艺人" : song.artist,
                            ),
                            trailing: Text(formatDuration(song.duration)),
                            onTap: () => unawaited(_playNavidromeSong(song)),
                          );
                        },
                      ),
                    ),
                  ],
                  const Divider(),
                  Text(
                    _source == "navidrome"
                        ? "音量（客户端流 $_volume%）"
                        : "音量（界面值 $_volume / LMS 值 ${sliderToLms(_volume)}）",
                  ),
                  Slider(
                    value: _volume.toDouble(),
                    min: 0,
                    max: 100,
                    onChanged: (v) => setState(() => _volume = v.round()),
                    onChangeEnd: (v) => unawaited(_setVolume(v.round())),
                  ),
                ],
              ),
            ),
            SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      const Text(
                        "曲库",
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                        ),
                      ),
                      const Spacer(),
                      Text(
                        _activeLibrary == "lms"
                            ? "当前：$_settings.lmsName"
                            : "当前：$_currentServerName",
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.grey,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  _statusRow(
                    "连接状态",
                    _activeLibrary == "lms"
                        ? "$_lmsVersion · $_coreStatus"
                        : _navStatusText,
                  ),
                  const Divider(),
                  if (_activeLibrary == "lms") ..._lmsLibraryWidgets(),
                  if (_activeLibrary == "navidrome") ..._navLibraryWidgets(),
                ],
              ),
            ),
            SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Text(
                    "主体（程序）",
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  _statusRow("当前版本", _appCurrent),
                  _statusRow("最新版本", _appLatest),
                  if (_appNotes.isNotEmpty)
                    Container(
                      margin: const EdgeInsets.symmetric(vertical: 6),
                      padding: const EdgeInsets.all(8),
                      color: Colors.grey.shade200,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: _appNotes
                            .map(
                              (n) => Text(
                                "· $n",
                                style: const TextStyle(fontSize: 12),
                              ),
                            )
                            .toList(),
                      ),
                    ),
                  _field("主体 zip 下载地址（留空则只检查版本）", _appZipUrl),
                  _field("SHA256SUMS 地址（zip 同目录）", _appSumsUrl),
                  ElevatedButton.icon(
                    onPressed: _busy
                        ? null
                        : () => unawaited(_verifyAppDownload()),
                    icon: const Icon(Icons.download_outlined),
                    label: const Text("下载并校验主体"),
                  ),
                  if (_appVerify != null)
                    _statusRow(
                      "主体校验",
                      "${_appVerify!.ok ? '通过' : '失败'} · ${_appVerify!.stage} · ${_appVerify!.detail}",
                    ),
                  const SizedBox(height: 6),
                  ElevatedButton.icon(
                    onPressed: (_busy || _appVerify?.ok != true)
                        ? null
                        : () => unawaited(_installApp()),
                    icon: const Icon(Icons.swap_horiz),
                    label: const Text("安装替换主体"),
                  ),
                  if (_appInstall != null)
                    _statusRow(
                      "主体替换",
                      "${_appInstall!.ok ? '成功' : '失败'} · ${_appInstall!.stage} · ${_appInstall!.detail}",
                    ),
                  if (_appBackups.isNotEmpty) ...<Widget>[
                    _backupSelector(_appBackups, _appBackupId, (v) {
                      if (mounted) setState(() => _appBackupId = v);
                    }),
                    ElevatedButton.icon(
                      onPressed: _busy ? null : () => unawaited(_rollbackApp()),
                      icon: const Icon(Icons.undo),
                      label: const Text("回滚主体"),
                    ),
                  ],
                  const Divider(),
                  const Text(
                    "Squeezelite 核心",
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  _statusRow("当前版本", _coreCurrent),
                  _statusRow("最新版本", _coreAsset?.displayVersion ?? "-"),
                  _statusRow("来源", _coreAsset?.filename ?? "-"),
                  ElevatedButton.icon(
                    onPressed: _busy
                        ? null
                        : () => unawaited(_verifyCoreDownload()),
                    icon: const Icon(Icons.download_outlined),
                    label: const Text("下载并校验核心"),
                  ),
                  if (_coreVerify != null)
                    _statusRow(
                      "核心校验",
                      "${_coreVerify!.ok ? '通过' : '失败'} · ${_coreVerify!.stage} · ${_coreVerify!.detail}",
                    ),
                  const SizedBox(height: 6),
                  ElevatedButton.icon(
                    onPressed:
                        (_busy ||
                            _coreVerify?.ok != true ||
                            _coreVerify!.binaryPath.isEmpty)
                        ? null
                        : () => unawaited(_installCore()),
                    icon: const Icon(Icons.swap_horiz),
                    label: const Text("安装替换核心"),
                  ),
                  if (_coreInstall != null)
                    _statusRow(
                      "核心替换",
                      "${_coreInstall!.ok ? '成功' : '失败'} · ${_coreInstall!.stage} · ${_coreInstall!.detail}",
                    ),
                  if (_coreBackups.isNotEmpty) ...<Widget>[
                    _backupSelector(_coreBackups, _coreBackupId, (v) {
                      if (mounted) setState(() => _coreBackupId = v);
                    }),
                    ElevatedButton.icon(
                      onPressed: _busy
                          ? null
                          : () => unawaited(_rollbackCore()),
                      icon: const Icon(Icons.undo),
                      label: const Text("回滚核心"),
                    ),
                  ],
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    children: <Widget>[
                      ElevatedButton.icon(
                        onPressed: _busy
                            ? null
                            : () => unawaited(_checkUpdates()),
                        icon: const Icon(Icons.refresh),
                        label: const Text("重新检查版本"),
                      ),
                    ],
                  ),
                  if (_busy) const LinearProgressIndicator(),
                  const SizedBox(height: 12),
                  const Text(
                    "替换前自动备份到 ~/Library/Application Support/Sonora/Backups；"
                    "健康检查失败会尝试自动回滚，也可在上方手动选择备份回滚。"
                    "主体替换需重启生效；核心替换会短暂停止核心并自动拉起。"
                    "核心 md5 / 文件大小来自 SourceForge RSS，无需手动填写。",
                    style: TextStyle(fontSize: 12),
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
