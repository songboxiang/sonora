import "dart:convert";
import "dart:io";

/// 负责把随 app 打包的 squeezelite 出厂核心复制到用户可写目录并拉起子进程。
///
/// 设计约束：
/// - 运行时绝不修改自身已签名的 bundle；实际执行的是 ~/Library/Application Support/Sonora/Core/squeezelite。
/// - 用户永远不需要手动执行二进制；调用方只需要 [start]。
/// - 参数构造是纯函数，便于单测；进程副作用集中在这里。
class CoreRunner {
  CoreRunner({
    required this.lmsHost,
    this.lmsPort = 9000,
    this.slimPort = 3483,
    this.playerName = "Sonora",
    this.device,
    this.mac,
    this.onLog,
  });

  final String lmsHost;
  final int lmsPort;
  /// slimproto 端口；不是 JSON-RPC 的 9000。
  final int slimPort;
  final String playerName;
  final String? device;
  final String? mac;
  final void Function(String line)? onLog;

  Process? _process;
  bool _stopping = false;

  bool get isRunning => _process != null;
  int? get pid => _process?.pid;

  /// 实际运行的可升级副本路径。
  static String userCorePath({String? home}) {
    final h = home ?? Platform.environment["HOME"] ?? "";
    return "$h/Library/Application Support/Sonora/Core/squeezelite";
  }

  /// 寻找随程序打包的出厂核心。
  ///
  /// 优先顺序：显式路径 → app bundle 内 Resources/Core → 开发目录 bin/。
  /// 返回 null 表示找不到（例如纯协议单测环境）。
  static String? bundledCorePath({
    String? executable,
    String? workingDirectory,
  }) {
    final exe = executable ?? Platform.resolvedExecutable;
    final app = RegExp(r"(.*\.app)/Contents/MacOS/[^/]+$").firstMatch(exe);
    if (app != null) {
      return "${app.group(1)}/Contents/Resources/Core/squeezelite";
    }
    final wd = workingDirectory ?? Directory.current.path;
    final local = "$wd/bin/squeezelite";
    if (File(local).existsSync()) return local;
    return null;
  }

  /// 从种子生成稳定的本地管理 MAC，避免 LMS 上残留的 02:00:00:00:00:00 被拒。
  static String macFromSeed(String seed) {
    final bytes = utf8.encode(seed);
    int hash(String prefix) {
      var h = 0x811c9dc5;
      for (final b in utf8.encode(prefix)) {
        h ^= b;
        h = (h * 0x01000193) & 0xffffffff;
      }
      for (final b in bytes) {
        h ^= b;
        h = (h * 0x01000193) & 0xffffffff;
      }
      return h;
    }

    final a = hash("a:");
    final b = hash("b:");
    final octets = <int>[
      0x02,
      (a >> 16) & 0xff,
      (a >> 8) & 0xff,
      a & 0xff,
      (b >> 16) & 0xff,
      b & 0xff,
    ];
    return octets.map((v) => v.toRadixString(16).padLeft(2, "0")).join(":");
  }

  /// 纯函数：构造 squeezelite 启动参数。
  static List<String> buildArgs({
    required String lmsHost,
    int slimPort = 3483,
    String playerName = "Sonora",
    String? device,
    String? mac,
  }) {
    final args = <String>["-s", "$lmsHost:$slimPort", "-n", playerName];
    if (device != null && device.isNotEmpty) {
      args.addAll(<String>["-a", device]);
    }
    if (mac != null && mac.isNotEmpty) {
      args.addAll(<String>["-m", mac]);
    }
    return args;
  }

  /// 确保用户目录里有可执行核心；不存在则从 bundle/开发目录复制。
  Future<String> ensureCore({
    String? bundledPath,
    String? userPath,
  }) async {
    final destPath = userPath ?? userCorePath();
    final dest = File(destPath);
    if (dest.existsSync()) return destPath;

    final srcPath = bundledPath ?? bundledCorePath();
    if (srcPath == null || !File(srcPath).existsSync()) {
      throw StateError(
        "未找到 squeezelite 出厂核心：请检查 bundle Contents/Resources/Core，"
        "或开发目录 bin/squeezelite",
      );
    }

    await dest.parent.create(recursive: true);
    await File(srcPath).copy(destPath);
    // chmod / quarantine 失败不应阻断启动，但要在日志里留痕。
    final chmod = await Process.run("chmod", ["755", destPath]);
    if (chmod.exitCode != 0) _log("chmod 失败：${chmod.stderr}");
    final xattr = await Process.run("xattr", ["-d", "com.apple.quarantine", destPath]);
    if (xattr.exitCode != 0 &&
        !xattr.stderr.toString().contains("No such xattr")) {
      _log("去 quarantine 失败：${xattr.stderr}");
    }
    return destPath;
  }

  /// 自动复制核心（如需）并拉起子进程。
  Future<Process> start({
    String? bundledPath,
    String? userPath,
  }) async {
    if (_process != null) return _process!;

    final corePath = await ensureCore(bundledPath: bundledPath, userPath: userPath);
    final effectiveMac = mac ??
        macFromSeed("sonora:${Platform.localHostname}:${Platform.environment["USER"] ?? ""}");
    final args = buildArgs(
      lmsHost: lmsHost,
      slimPort: slimPort,
      playerName: playerName,
      device: device,
      mac: effectiveMac,
    );
    _log("启动 $corePath ${args.join(" ")}");

    final p = await Process.start(corePath, args);
    _process = p;
    _stopping = false;

    p.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) => _log("[core:out] $line"));
    p.stderr
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) => _log("[core:err] $line"));

    p.exitCode.then((code) {
      if (!_stopping) _log("核心意外退出，exitCode=$code");
      _process = null;
    });
    return p;
  }

  /// 优雅停止：先 SIGTERM，超时才 SIGKILL。
  Future<void> stop() async {
    final p = _process;
    if (p == null) return;
    _stopping = true;
    _log("停止核心 pid=${p.pid}");
    p.kill(ProcessSignal.sigterm);
    await p.exitCode.timeout(
      const Duration(seconds: 3),
      onTimeout: () {
        p.kill(ProcessSignal.sigkill);
        return -1;
      },
    );
    _process = null;
    _stopping = false;
  }

  void _log(String line) => onLog?.call(line);
}
