import "dart:convert";
import "dart:io";

/// 两条曲库轨道。切换轨道会改变引擎与播放方式。
enum LibraryTrack { lms, navidrome }

/// `squeezelite -l` 输出的一行设备。
class OutputDevice {
  const OutputDevice({required this.id, required this.name, this.raw = ""});

  /// 传给 -o 的编号/名称。
  final String id;

  /// 界面上显示的友好名称。
  final String name;
  final String raw;
}

/// 解析 `  0 - Apple Virtual Sound Device [Core Audio]` 这样的行。
List<OutputDevice> parseOutputDevices(String text) {
  final out = <OutputDevice>[];
  for (final line in text.split(RegExp(r"\r?\n"))) {
    final m = RegExp(r"^\s*(\d+)\s+-\s+(.+?)\s*$").firstMatch(line);
    if (m == null) continue;
    out.add(
      OutputDevice(id: m.group(1)!, name: m.group(2)!.trim(), raw: line.trim()),
    );
  }
  return out;
}

/// 一套 squeezelite 启动参数。所有字段都能在「修改配置」里编辑。
class CoreParams {
  const CoreParams({
    this.profile = "bitperfect",
    this.device = "",
    this.deviceName = "",
    this.playerName = "Sonora-UI",
    this.latencyMs = 10,
    this.allowResample = false,
    this.rates = "44100-384000",
    this.dop = false,
    this.streamBufferKb = 2048,
    this.outputBufferKb = 3445,
    this.modelName = "",
    this.extraArgs = "",
  });

  final String profile;
  final String device;
  final String deviceName;
  final String playerName;
  final int latencyMs;
  final bool allowResample;
  final String rates;
  final bool dop;
  final int streamBufferKb;
  final int outputBufferKb;
  final String modelName;
  final String extraArgs;

  CoreParams copyWith({
    String? profile,
    String? device,
    String? deviceName,
    String? playerName,
    int? latencyMs,
    bool? allowResample,
    String? rates,
    bool? dop,
    int? streamBufferKb,
    int? outputBufferKb,
    String? modelName,
    String? extraArgs,
  }) {
    return CoreParams(
      profile: profile ?? this.profile,
      device: device ?? this.device,
      deviceName: deviceName ?? this.deviceName,
      playerName: playerName ?? this.playerName,
      latencyMs: latencyMs ?? this.latencyMs,
      allowResample: allowResample ?? this.allowResample,
      rates: rates ?? this.rates,
      dop: dop ?? this.dop,
      streamBufferKb: streamBufferKb ?? this.streamBufferKb,
      outputBufferKb: outputBufferKb ?? this.outputBufferKb,
      modelName: modelName ?? this.modelName,
      extraArgs: extraArgs ?? this.extraArgs,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    "profile": profile,
    "device": device,
    "deviceName": deviceName,
    "playerName": playerName,
    "latencyMs": latencyMs,
    "allowResample": allowResample,
    "rates": rates,
    "dop": dop,
    "streamBufferKb": streamBufferKb,
    "outputBufferKb": outputBufferKb,
    "modelName": modelName,
    "extraArgs": extraArgs,
  };

  static CoreParams fromJson(Map<String, dynamic> m) => CoreParams(
    profile: (m["profile"] ?? "bitperfect").toString(),
    device: (m["device"] ?? "").toString(),
    deviceName: (m["deviceName"] ?? "").toString(),
    playerName: (m["playerName"] ?? "Sonora-UI").toString(),
    latencyMs: int.tryParse((m["latencyMs"] ?? 10).toString()) ?? 10,
    allowResample:
        m["allowResample"] == true || m["allowResample"].toString() == "true",
    rates: (m["rates"] ?? "44100-384000").toString(),
    dop: m["dop"] == true || m["dop"].toString() == "true",
    streamBufferKb:
        int.tryParse((m["streamBufferKb"] ?? 2048).toString()) ?? 2048,
    outputBufferKb:
        int.tryParse((m["outputBufferKb"] ?? 3445).toString()) ?? 3445,
    modelName: (m["modelName"] ?? "").toString(),
    extraArgs: (m["extraArgs"] ?? "").toString(),
  );
}

const Map<String, String> coreProfiles = <String, String>{
  "bitperfect": "完美码率直通",
  "best": "最佳音质",
  "dsd": "DSD直通",
  "usb": "USB DAC 直连",
  "custom": "自定义",
};

/// 每个参数在 UI 上的帮助释意。
const Map<String, String> coreParamHelp = <String, String>{
  "device": "-o：输出到哪个设备。点「扫描」列出 CoreAudio 设备；选 USB DAC 可绕过系统混音。",
  "deviceName": "给设备起一个易记的名字，只是在本软件里显示，不会写回系统。",
  "playerName": "-n：LMS 里显示的播放器名称。改名后 LMS 会把它当成一个新播放器。",
  "latencyMs": "-a 第一段：目标延迟（毫秒）。越小响应越快，太小可能爆音；一般 10~30。",
  "allowResample": "-a 第二段：是否允许 macOS 重采样。0=不重采样（码率直通，音质最佳）；1=兼容性好但精度会损失。",
  "rates": "-r：告诉 LMS 本机支持的采样率范围，如 44100-384000 或 44100,48000,96000,192000。",
  "dop": "-D：设备支持 DSD over PCM 时打开，可把 DSD 信号以 DoP 直通给 DAC。不支持的设备请关闭。",
  "buffers": "-b：流缓冲/输出缓冲（KB）。大缓冲更稳但延迟更高；默认 2048:3445。",
  "modelName": "-M：上报给 LMS 的播放器型号，仅用于显示与皮肤匹配，可留空。",
  "extraArgs": "其它原样追加给 squeezelite 的参数，例如 -c flac,pcm,dsd；不了解时留空。",
};

/// 预设一键填入参数；用户改动任何一项后 profile 变为 custom。
CoreParams paramsForProfile(
  String profile, {
  CoreParams base = const CoreParams(),
}) {
  switch (profile) {
    case "best":
      return base.copyWith(
        profile: "best",
        latencyMs: 20,
        allowResample: false,
        rates: "44100-384000",
        dop: true,
        streamBufferKb: 4096,
        outputBufferKb: 8192,
      );
    case "dsd":
      return base.copyWith(
        profile: "dsd",
        latencyMs: 20,
        allowResample: false,
        rates: "44100-384000",
        dop: true,
        streamBufferKb: 4096,
        outputBufferKb: 8192,
        extraArgs: "-c flac,pcm,dsd",
      );
    case "usb":
      return base.copyWith(
        profile: "usb",
        latencyMs: 10,
        allowResample: false,
        rates: "44100-384000",
        dop: true,
        streamBufferKb: 2048,
        outputBufferKb: 4096,
      );
    case "bitperfect":
      return base.copyWith(
        profile: "bitperfect",
        latencyMs: 10,
        allowResample: false,
        rates: "44100-384000",
        dop: false,
        streamBufferKb: 2048,
        outputBufferKb: 3445,
      );
    default:
      return base.copyWith(profile: "custom");
  }
}

/// 由参数构造完整启动命令行。纯函数，便于单测。
List<String> buildCoreArgs({
  required CoreParams params,
  required String lmsHost,
  int slimPort = 3483,
  String mac = "",
}) {
  final args = <String>["-s", "$lmsHost:$slimPort", "-n", params.playerName];
  if (params.device.trim().isNotEmpty) {
    args.addAll(<String>["-o", params.device.trim()]);
  }
  final latency = params.latencyMs.clamp(1, 500);
  args.addAll(<String>["-a", "$latency:${params.allowResample ? 1 : 0}"]);
  if (params.rates.trim().isNotEmpty) {
    args.addAll(<String>["-r", params.rates.trim()]);
  }
  if (params.dop) args.add("-D");
  final sb = params.streamBufferKb.clamp(64, 65536);
  final ob = params.outputBufferKb.clamp(64, 65536);
  args.addAll(<String>["-b", "$sb:$ob"]);
  if (params.modelName.trim().isNotEmpty) {
    args.addAll(<String>["-M", params.modelName.trim()]);
  }
  if (params.extraArgs.trim().isNotEmpty) {
    args.addAll(
      params.extraArgs.trim().split(RegExp(r"\s+")).where((s) => s.isNotEmpty),
    );
  }
  if (mac.trim().isNotEmpty) args.addAll(<String>["-m", mac.trim()]);
  return args;
}

/// 全部可持久化的界面配置。
class AppSettings {
  AppSettings({
    this.lmsHost = "192.168.199.2",
    this.lmsPort = "9000",
    this.slimPort = "3483",
    this.lmsUser = "",
    this.lmsPassword = "",
    this.lmsCredsPath = "/Users/song/.squeezelite_gui/config.json",
    this.navHost = "192.168.199.2:4533",
    this.navUser = "",
    this.navPassword = "",
    this.navCredsPath = "/Users/song/navidrome_creds.json",
    this.activeLibrary = "lms",
    this.appZipUrl = "",
    this.appSumsUrl = "",
    this.coreParams = const CoreParams(),
  });

  String lmsHost;
  String lmsPort;
  String slimPort;
  String lmsUser;
  String lmsPassword;
  String lmsCredsPath;
  String navHost;
  String navUser;
  String navPassword;
  String navCredsPath;
  String activeLibrary;
  String appZipUrl;
  String appSumsUrl;
  CoreParams coreParams;

  /// 上一次实际使用的输出设备，下次启动默认选中。
  String get lastDevice => coreParams.device;

  Map<String, dynamic> toJson() => <String, dynamic>{
    "lmsHost": lmsHost,
    "lmsPort": lmsPort,
    "slimPort": slimPort,
    "lmsUser": lmsUser,
    "lmsPassword": lmsPassword,
    "lmsCredsPath": lmsCredsPath,
    "navHost": navHost,
    "navUser": navUser,
    "navPassword": navPassword,
    "navCredsPath": navCredsPath,
    "activeLibrary": activeLibrary,
    "appZipUrl": appZipUrl,
    "appSumsUrl": appSumsUrl,
    "coreParams": coreParams.toJson(),
  };

  static AppSettings fromJson(Map<String, dynamic> m) => AppSettings(
    lmsHost: (m["lmsHost"] ?? "192.168.199.2").toString(),
    lmsPort: (m["lmsPort"] ?? "9000").toString(),
    slimPort: (m["slimPort"] ?? "3483").toString(),
    lmsUser: (m["lmsUser"] ?? "").toString(),
    lmsPassword: (m["lmsPassword"] ?? "").toString(),
    lmsCredsPath:
        (m["lmsCredsPath"] ?? "/Users/song/.squeezelite_gui/config.json")
            .toString(),
    navHost: (m["navHost"] ?? "192.168.199.2:4533").toString(),
    navUser: (m["navUser"] ?? "").toString(),
    navPassword: (m["navPassword"] ?? "").toString(),
    navCredsPath: (m["navCredsPath"] ?? "/Users/song/navidrome_creds.json")
        .toString(),
    activeLibrary: (m["activeLibrary"] ?? "lms").toString(),
    appZipUrl: (m["appZipUrl"] ?? "").toString(),
    appSumsUrl: (m["appSumsUrl"] ?? "").toString(),
    coreParams: m["coreParams"] is Map<String, dynamic>
        ? CoreParams.fromJson(m["coreParams"] as Map<String, dynamic>)
        : const CoreParams(),
  );
}

/// 用户目录下的 JSON 配置；密码只落在本机，不写日志。
class SettingsStore {
  SettingsStore({String? path}) : path = path ?? SettingsStore.defaultPath();

  static String defaultPath({String? home}) =>
      "${home ?? Platform.environment["HOME"] ?? ""}"
      "/Library/Application Support/Sonora/settings.json";

  final String path;

  AppSettings load() {
    try {
      final f = File(path);
      if (!f.existsSync()) return AppSettings();
      final decoded = jsonDecode(f.readAsStringSync());
      if (decoded is Map<String, dynamic>) return AppSettings.fromJson(decoded);
    } catch (_) {}
    return AppSettings();
  }

  Future<void> save(AppSettings settings) async {
    final f = File(path);
    await f.parent.create(recursive: true);
    await f.writeAsString("${jsonEncode(settings.toJson())}\n");
  }
}
