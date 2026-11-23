# -*- coding: utf-8 -*-
"""Bridge API: 前端 JS 调用的 Python 接口。

阶段 1：只暴露「正在播放」最小闭环所需的纯逻辑函数。
所有函数直接调用 legacy_core（Tk v1.6.0 原样代码），保证逻辑一致。
返回值必须 JSON-serializable；异常统一转 {ok:false,error}。
"""
import os
import sys
import json
import base64
import traceback
import subprocess
import threading
import tempfile
import signal
import time as _time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legacy_core as c

CFG = c.load_config()
_AUDIO_STATE = {}   # parse_sl_output 的增量状态（跨 getAudio 调用）

# ---- squeezelite 引擎进程状态 ----
_ENGINE = {"proc": None, "pid": 0, "start_ts": 0.0, "logs": [],
           "exit_code": None, "argv": [], "watchdog": None}
_ENGINE_LOCK = threading.Lock()
_LOG_MAX = 400


def _wrap(fn):
    """统一错误处理：成功返回原值，失败返回 {ok:False,error}。"""
    def inner(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            return {"ok": False, "error": str(e)[:300],
                    "trace": traceback.format_exc(limit=3)}
    inner.__name__ = fn.__name__
    return inner


# ---- 元信息 / 配置 ----
@_wrap
def getMeta():
    return {"version": c.VERSION, "appName": "Sonora 颂诺",
            "platform": sys.platform, "bridge": "pywebview-v2.0.14"}


@_wrap
def getConfig():
    d = dict(CFG)
    # 不把密码明文发给前端展示（前端只需 host/port/user 用于展示）
    for k in ("lms_password", "password"):
        if k in d:
            d[k] = "******" if d[k] else ""
    return d


@_wrap
def setTheme(name):
    if name not in c.THEMES:
        return {"ok": False, "error": "unknown theme: %s" % name}
    CFG["theme"] = name
    c.save_config(CFG)
    return {"ok": True, "theme": name}


# ---- 播放器 / 状态 ----
@_wrap
def getConnection():
    """返回 LMS 连接状态，供顶部徽标实时显示（连通/断开/未配置）。"""
    host = (CFG.get("lms_host") or "").strip()
    if not host:
        return {"connected": False, "state": "unconfigured",
                "label": "未配置服务器", "url": ""}
    try:
        r = c.lms_current(CFG)
        if r and r.get("ok"):
            # 服务器连通后，检查是否有 squeezelite 播放器注册：
            # 无播放器时所有播放/静音命令都会失败，需明确告知用户。
            player_count = 0
            try:
                ps = c.np_players(CFG)
                player_count = len(ps)
            except Exception:
                player_count = -1  # 查询失败，不确定
            if player_count == 0:
                return {"connected": True, "state": "noplayer",
                        "label": "已连服务器·播放器未启动",
                        "url": r.get("url", ""), "version": r.get("version", ""),
                        "playerCount": 0,
                        "error": "LMS 服务器已连接，但没有 squeezelite 播放器在线。请到「播放器引擎」页启动引擎。"}
            return {"connected": True, "state": "online",
                    "label": "已连接", "url": r.get("url", ""),
                    "version": r.get("version", ""), "playerCount": player_count}
        return {"connected": False, "state": "offline",
                "label": "连接失败", "url": (r or {}).get("url", ""),
                "error": (r or {}).get("error", "")}
    except Exception as e:
        return {"connected": False, "state": "offline",
                "label": "连接失败", "error": str(e)[:120]}


@_wrap
def getPlayers():
    ps = c.np_players(CFG)
    return [{"id": str(p.get("id", "")), "name": str(p.get("name", "")),
             "connected": bool(p.get("connected", 0))} for p in ps]


@_wrap
# ---- 音量感知曲线（滑块线性 0-100 <-> LMS 刻度）----
def vol_to_lms(v):
    """滑块 0-100(线性) -> LMS mixer volume(感知平方曲线，低段更细腻)。"""
    try:
        x = max(0.0, min(100.0, float(v))) / 100.0
    except Exception:
        x = 0.6
    return int(round(100.0 * (x ** 2)))

def vol_from_lms(v):
    """LMS mixer volume -> 滑块 0-100(线性)。"""
    try:
        x = max(0.0, min(100.0, float(v))) / 100.0
    except Exception:
        x = 0.6
    return int(round(100.0 * (x ** 0.5)))

def getStatus(playerId=""):
    pid = str(playerId or CFG.get("np_playerid") or "")
    if not pid:
        ps = c.np_players(CFG)
        pick = c.np_pick_player(CFG, ps, "")
        pid = str(pick.get("id", "")) if pick else ""
    if not pid:
        return {"ok": False, "error": "no player available", "mode": "stop", "track": {}}
    st = c.np_status(CFG, pid)
    st["playerId"] = pid
    try:
        st["volume"] = vol_from_lms(st.get("volume", 100))
    except Exception:
        pass
    return st


# ---- 封面 / 歌词 / 简介 / 音频 ----
@_wrap
def getCover(track, size=420):
    """取高清封面。LMS 默认 cover_300x300 放大到 440px 会发虚，
    优先尝试 cover_1000x1000 / 原始 cover.jpg，再回退 300x300。"""
    if not isinstance(track, dict):
        return None
    coverid = str(track.get("coverid") or track.get("artwork_track_id") or "")
    url = str(track.get("artwork_url") or "")
    if not coverid and not url:
        return None
    full_url = c.np_cover_url(CFG, coverid, url)
    if not full_url:
        return None
    candidates = []
    if not url and "cover_300x300" in full_url:
        candidates.append(full_url.replace("cover_300x300", "cover_1000x1000"))
        candidates.append(full_url.replace("cover_300x300.jpg", "cover.jpg"))
    candidates.append(full_url)
    seen = set()
    candidates = [u for u in candidates if u and not (u in seen or seen.add(u))]

    def _valid_image(d):
        return bool(d and len(d) > 512 and (
            d[:8] == b"\x89PNG\r\n\x1a\n" or d[:3] == b"\xff\xd8\xff" or
            d[:6] in (b"GIF87a", b"GIF89a") or d[:4] == b"RIFF"))

    def _decode(d):
        try:
            return c.decode_cover_png(
                d, max_size=int(size), square=True,
                pad_color=c.THEMES.get(CFG.get("theme", "light"), {})
                           .get("cover_pad", "#0d292d"))
        except Exception:
            return None

    hdr = None
    try:
        hdr = c.lms_auth_headers(CFG)
    except Exception:
        pass
    import urllib.request as _ur
    for u in candidates:
        data = None
        try:
            data = c.http_get(u, timeout=8)
        except Exception:
            data = None
        if not _valid_image(data) and hdr:
            try:
                req = _ur.Request(u, headers=hdr)
                with _ur.urlopen(req, timeout=8) as _r:
                    data = _r.read()
            except Exception:
                data = None
        if not _valid_image(data):
            continue
        png = _decode(data)
        if png:
            return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return None

@_wrap
def getLyrics(track):
    """取歌词：优先用传入曲目；若字段不足则用当前播放状态补全。
    np_status(with_lyrics=True) 也会随状态带回 LMS 内嵌歌词。"""
    full = dict(track) if isinstance(track, dict) else {}
    pid = str(CFG.get("np_playerid") or "")
    if not pid:
        try:
            pid = _pick_pid()
        except Exception:
            pass
    try:
        if pid:
            stt = c.np_status(CFG, pid, with_lyrics=True)
            cur = stt.get("track") or {}
            if cur:
                # 传入 track 为空或与当前一致时，用完整曲目字段
                if not full.get("id") or not full.get("title") or str(cur.get("id")) == str(full.get("id")):
                    for k in ("id", "title", "artist", "album", "duration", "url", "lyrics"):
                        if cur.get(k) not in (None, ""):
                            full[k] = cur.get(k)
                # status 直接带回的歌词优先（仅当传入曲为空或与当前曲一致，避免切歌串曲）
                _id_ok = (not full.get("id")) or (str(cur.get("id")) == str(full.get("id")))
                if _id_ok and cur.get("lyrics") and not full.get("_embedded_lyrics"):
                    full["_embedded_lyrics"] = cur.get("lyrics")
    except Exception:
        pass
    text, src = "", ""
    embedded = full.pop("_embedded_lyrics", "") if isinstance(full, dict) else ""
    # 最高优先级：用户手动选定/粘贴的歌词（按 title|artist 持久化）
    choice = None
    try:
        choice = c.lyric_choice_get(c.lyric_choice_key(full))
    except Exception:
        pass
    if choice and choice.get("text"):
        text, src = choice.get("text", ""), "手动选定 · " + str(choice.get("source") or "")
    if embedded and not text:
        text, src = embedded, "LMS 内嵌"
    if not text:
        text, src = c.np_lyrics_resolve(CFG, full, pid)
    parsed = c.parse_lrc(text or "")
    return {"text": text or "", "source": src or "",
            "timed": bool(parsed.get("timed")),
            "lines": parsed.get("lines", [])}


@_wrap
def getLyricSources(track):
    """返回歌词候选列表，供前端手动选择 Correct source。"""
    full = dict(track) if isinstance(track, dict) else {}
    if not full.get("title"):
        try:
            pid = str(CFG.get("np_playerid") or "")
            if not pid:
                pid = _pick_pid()
            if pid:
                stt = c.np_status(CFG, pid, with_lyrics=False)
                cur = stt.get("track") or {}
                if cur:
                    for k in ("id", "title", "artist", "album", "duration"):
                        if cur.get(k) not in (None, ""):
                            full[k] = cur.get(k)
        except Exception:
            pass
    cands = c.lyrics_collect(full.get("title", ""), full.get("artist", ""),
                             full.get("album", ""), _safe_float(full.get("duration")))
    # LMS 内嵌歌词作为第一个候选
    try:
        pid = str(CFG.get("np_playerid") or "") or _pick_pid()
        if pid:
            stt = c.np_status(CFG, pid, with_lyrics=True)
            emb = (stt.get("track") or {}).get("lyrics") or ""
            if emb:
                cands.insert(0, {"source": "LMS 内嵌歌词", "text": emb,
                                 "timed": bool(c.parse_lrc(emb).get("timed"))})
    except Exception:
        pass
    # 去重（按 text）
    seen, uniq = set(), []
    for x in cands:
        t = (x.get("text") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        uniq.append({"source": x.get("source", ""), "text": x.get("text", ""),
                     "timed": bool(x.get("timed"))})
    choice = None
    try:
        choice = c.lyric_choice_get(c.lyric_choice_key(full))
    except Exception:
        pass
    return {"items": uniq,
            "current": (choice or {}).get("source", "") if choice else ""}


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return 0.0


# ---- 专注模式：动态切换原生标题栏外观（消除顶部漏边）----
_FOCUS_CHROME = {"on": False}


def setFocusChrome(on):
    """进入专注模式(True)把 macOS 原生标题栏/窗口背景改为深色；
    退出(False)恢复浅色。失败不影响功能，仅影响观感。"""
    _FOCUS_CHROME["on"] = bool(on)
    if sys.platform != "darwin":
        return {"ok": False, "reason": "not-macos"}
    try:
        import webview as _wv
        win = None
        try:
            win = _wv.windows[0] if getattr(_wv, "windows", None) else None
        except Exception:
            pass
        ns = getattr(win, "native", None) if win else None
        if ns is None:
            return {"ok": False, "reason": "no-native-window"}
        from AppKit import NSColor
        if on:
            col = NSColor.colorWithCalibratedRed_green_blue_alpha_(10/255.0, 20/255.0, 22/255.0, 1.0)
            try:
                ns.setOpaque_(True)
            except Exception:
                pass
        else:
            col = NSColor.colorWithCalibratedRed_green_blue_alpha_(250/255.0, 250/255.0, 250/255.0, 1.0)
        ns.setBackgroundColor_(col)
        try:
            ns.setTitlebarAppearsTransparent_(bool(on))
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_wrap
def setLyricChoice(track, source, text):
    """用户选择/粘贴歌词后持久化；返回解析后的歌词对象供前端直接显示。"""
    key = c.lyric_choice_key(track if isinstance(track, dict) else {})
    text = str(text or "")
    src = str(source or "手动")
    ok = c.lyric_choice_set(key, src, text)
    parsed = c.parse_lrc(text)
    return {"ok": ok, "source": "手动选定 · " + src, "text": text,
            "timed": bool(parsed.get("timed")), "lines": parsed.get("lines", [])}


@_wrap
def clearLyricChoice(track):
    key = c.lyric_choice_key(track if isinstance(track, dict) else {})
    return {"ok": c.lyric_choice_clear(key)}


@_wrap
def getBio(artist, album=""):
    a, b, src = c.bio_fetch(CFG, str(artist or ""), str(album or ""))
    return {"artist": a or "", "album": b or "", "source": src or ""}


def web_audio_verdict(spec, full, volume, rate, sl_state):
    """转码/直通判定：优先依据 LMS status 的 url/type（不依赖 squeezelite 日志）。
    url 为 file:// = LMS 直接流送源文件、未转码；
    url 含 stream/transcode 或 type=pcm = LMS 已转码。"""
    url = str(full.get("url") or "")
    ltype = str(full.get("type") or "").lower()
    ext = str(spec.get("ext") or "").lower()
    fmt = str(spec.get("format") or "")
    low = url.lower()
    transcode = None
    reason = ""
    if low.startswith("file:"):
        transcode = False
        reason = "LMS 从源文件直送（%s），未经转码" % (fmt or ext or ltype)
    elif ("/stream/" in low or "stream.mp3" in low or "stream.flac" in low
          or "transcode" in low or "transcoded" in low):
        transcode = True
        reason = "LMS 输出为转码流（URL: %s）" % url[:80]
    elif ltype in ("pcm", "wav", "aif", "aiff") and ext not in (".pcm", ".wav", ".aif", ".aiff"):
        transcode = True
        reason = "源文件为 %s，LMS 输出 type=%s（PCM），说明已解码转码" % (fmt or ext, ltype)
    elif low:
        transcode = False
        reason = "LMS 直接流送源文件（%s）" % (fmt or ext or ltype)
    else:
        reason = "LMS 未提供流 URL"
    # squeezelite 日志若可用，作为补充证据（不改变 file:// 的直送结论）
    if isinstance(sl_state, dict) and sl_state:
        try:
            if sl_state.get("converted"):
                transcode = True
                reason = str(sl_state.get("note") or "输出设备不支持，已转换为 PCM")
            elif sl_state.get("rate") and spec.get("rate_hz") and int(sl_state["rate"]) != int(spec["rate_hz"]):
                transcode = True
                reason = "输出采样率与源文件不同（源 %s → 输出 %s）" % (
                    spec.get("rate"), str(sl_state["rate"]))
        except Exception:
            pass
    try:
        vol = int(float(volume))
    except Exception:
        vol = 100
    try:
        rate_f = float(rate)
    except Exception:
        rate_f = 1.0
    notes = []
    if vol != 100:
        notes.append("音量 %d%%（非 100，会改动 PCM）" % vol)
    if abs(rate_f - 1.0) > 0.001:
        notes.append("播放速率 %s" % rate)
    if transcode is True:
        level, title, short = "warn", "已转码", "已转码"
    elif transcode is False:
        level, title, short = "ok", "未转码 · 源文件直送", "未转码"
    else:
        level, title, short = "unknown", "待确认", "待确认"
    detail = reason + ("；" + "；".join(notes) if notes else "")
    return {"level": level, "title": title, "detail": detail, "short": short,
            "transport": ("transcoded" if transcode is True else
                          "direct" if transcode is False else "unknown"),
            "volume": vol, "rate": rate}

@_wrap
def getAudio(track):
    """从 LMS 当前播放状态直接取完整曲目字段解析音频规格，不依赖前端传参。
    这样格式/码率/位深来自真实 status 标签（url/type/samplerate/samplesize/bitrate）。"""
    # 优先用 LMS np_status 的完整 track（含 url/type/samplerate/samplesize/bitrate/filesize）
    full = dict(track) if isinstance(track, dict) else {}
    try:
        pid = _pick_pid()
        if pid:
            stt = c.np_status(CFG, pid)
            cur = stt.get("track") or {}
            # 只有当前正在播放的曲目才覆盖；否则沿用前端传入
            if cur and (not full.get("id") or str(cur.get("id")) == str(full.get("id"))):
                for k in ("url", "type", "samplerate", "samplesize", "bitrate",
                          "filesize", "duration", "title", "artist", "album",
                          "artwork_track_id", "coverid", "id"):
                    if cur.get(k) not in (None, ""):
                        full[k] = cur.get(k)
    except Exception:
        pass
    spec = c.audio_spec(full) or {}
    # squeezelite 输出日志解析（若进程在跑）；parse_sl_output 返回 (state, bool)
    sl_state = {}
    try:
        sl_state = {k: v for k, v in _AUDIO_STATE.items() if k != "lines"}
    except Exception:
        pass
    if not sl_state:
        # 兼容外部启动/旧版本进程：从已记录的引擎日志反推输出状态
        try:
            with _ENGINE_LOCK:
                _logs = list(_ENGINE.get("logs", []))
            _st = {}
            for _line in _logs:
                try:
                    _r = c.parse_sl_output(_line, _st)
                    if isinstance(_r, tuple):
                        _st = _r[0] or _st
                    elif isinstance(_r, dict):
                        _st = _r
                except Exception:
                    pass
            sl_state = _st
        except Exception:
            pass
    # verdict 的 st 参数用 LMS status 的 volume/rate，sl 参数用日志解析结果
    vst = {"volume": 100, "rate": 1}
    try:
        pid = _pick_pid()
        if pid:
            stt = c.np_status(CFG, pid)
            vst = {"volume": stt.get("volume", 100), "rate": stt.get("rate", 1)}
    except Exception:
        pass
    verdict = web_audio_verdict(spec, full, vst.get("volume", 100),
                                vst.get("rate", 1), sl_state)
    return {"spec": spec, "verdict": verdict, "slState": sl_state,
            "url": str(full.get("url") or "")}


# ---- 播放控制 ----
@_wrap
def playControl(cmd):
    valid = {"play", "pause", "next", "prev", "stop"}
    cmd = str(cmd or "")
    if cmd not in valid:
        return {"ok": False, "error": "invalid cmd: %s" % cmd}
    pid = str(CFG.get("np_playerid") or "")
    if not pid:
        ps = c.np_players(CFG)
        pick = c.np_pick_player(CFG, ps, "")
        pid = str(pick.get("id", "")) if pick else ""
    if not pid:
        return {"ok": False, "error": "no player"}
    # 注意：lms_rpc 内部会 list(cmd)，必须传列表；传字符串会被拆成单字符导致 LMS 断连
    # 对齐 Tk 版已验证命令：playlist index ±1（jump 在短队列/边界会回退到开头）
    rpc_map = {"play": ["play"], "pause": ["pause"], "stop": ["stop"],
               "next": ["playlist", "index", "+1"], "prev": ["playlist", "index", "-1"]}
    c.lms_rpc(CFG, rpc_map[cmd], pid, _id=60)
    return {"ok": True, "cmd": cmd}


# ---- 音乐库（阶段 1 顺手暴露，前端可选实现）----
@_wrap
def libBrowse(mode="albums", start=0, count=50, filters=None, query=""):
    items, total = c.lib_browse(CFG, str(mode), int(start), int(count),
                                str(query or ""), filters or [])
    # 与 getLibrary 一致：给条目注入缩略封面，让下钻曲目/艺术家/流派也有封面
    for it in items:
        cid = c.lib_cover_id(it) if hasattr(c, "lib_cover_id") else (
            it.get("artwork_track_id") or it.get("coverid") or "")
        it["_cover"] = _lib_thumb(cid) if cid else None
        # 保留完整字段（含 url/type/samplerate 等），供音频信息与歌词使用
    return {"items": items, "total": total}


@_wrap
def libPlay(mode, itemId):
    cmd = c.lib_play_cmd(str(mode), str(itemId))
    pid = str(CFG.get("np_playerid") or "")
    if not pid:
        ps = c.np_players(CFG)
        pick = c.np_pick_player(CFG, ps, "")
        pid = str(pick.get("id", "")) if pick else ""
    c.lms_rpc(CFG, cmd, pid, _id=61)
    return {"ok": True}


# ---- 音乐库一次性聚合（v2 首页音乐库）----
_LIB_CACHE = {"ts": 0.0, "data": None}
_LIB_TTL = 300  # 5 分钟缓存


def _lib_thumb(cid):
    """按 coverid 抓一张 96px JPEG 缩略图，返回 data URL；失败返回 None。"""
    if not cid:
        return None
    try:
        url = c.np_cover_url(CFG, str(cid), "")
        candidates = []
        if url:
            candidates.append(url)
            candidates.append(url.replace("cover_300x300", "cover_96x96")
                                 .replace("cover.jpg", "cover_96x96.jpg"))
            # 原始 cover（无尺寸后缀）兜底
            candidates.append(url.replace("cover_300x300.jpg", "cover.jpg")
                                 .replace("cover_96x96.jpg", "cover.jpg"))
        import urllib.request
        hdr = c.lms_auth_headers(CFG)
        raw = None
        for u in [x for x in candidates if x]:
            try:
                req = urllib.request.Request(u, headers=hdr)
                with urllib.request.urlopen(req, timeout=4) as r:
                    raw = r.read()
                if raw and len(raw) >= 100:
                    break
            except Exception:
                raw = None
                continue
        if not raw or len(raw) < 100:
            return None
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((96, 96))
            buf = io.BytesIO(); im.save(buf, "JPEG", quality=68)
            raw = buf.getvalue()
        except Exception:
            pass
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


@_wrap
def getLibrary(limit=120):
    """返回 albums/artists/titles/genres 四类数据，albums/titles 带缩略封面。
    结果缓存 5 分钟，避免每次进入音乐库都重抓上百张封面。"""
    import time as _t
    now = _t.time()
    if _LIB_CACHE["data"] and (now - _LIB_CACHE["ts"]) < _LIB_TTL:
        return _LIB_CACHE["data"]
    out = {}
    for mode in ("albums", "artists", "titles", "genres"):
        try:
            items, total = c.lib_browse(CFG, mode, 0, int(limit))
        except Exception:
            items, total = [], 0
        for it in items:
            it["_cover"] = None
        if mode in ("albums", "titles"):
            for it in items:
                cid = it.get("artwork_track_id") or it.get("coverid") or ""
                if cid:
                    it["_cover"] = _lib_thumb(cid)
        out[mode] = {"items": items, "total": total}
    _LIB_CACHE["data"] = out
    _LIB_CACHE["ts"] = now
    return out


# ================= 阶段 2：设置子页 Bridge =================
@_wrap
def testServer(host="", port="9000", user="", password=""):
    """测试 LMS 连通：临时用给定参数调 lms_current，不改全局配置。"""
    tmp = dict(CFG)
    tmp["lms_host"] = str(host or "").strip()
    tmp["lms_port"] = str(port or "9000").strip()
    tmp["lms_user"] = str(user or "").strip()
    tmp["lms_pass"] = str(password or "")
    if not tmp["lms_host"]:
        return {"ok": False, "error": "请填写服务器地址"}
    return c.lms_current(tmp)


@_wrap
def saveServer(host, port="9000", user="", password="", playerId=""):
    CFG["lms_host"] = str(host or "").strip()
    CFG["lms_port"] = str(port or "9000").strip()
    CFG["lms_user"] = str(user or "").strip()
    CFG["lms_pass"] = str(password or "")
    if playerId:
        CFG["np_playerid"] = str(playerId)
    c.save_config(CFG)
    _LIB_CACHE["ts"] = 0; _LIB_CACHE["data"] = None   # 音乐库缓存失效
    return {"ok": True, "config": getConfig()}


@_wrap
def scanDevices():
    devs, reasons, binary = c.scan_devices(CFG)
    # 兜底：若扫描结果为空或只有一个笼统项，补充 LMS 端已连接的播放器
    try:
        ps = c.np_players(CFG)
        known = {d["name"].lower() for d in devs}
        for p in ps:
            if p.get("connected") and p.get("name"):
                nm = str(p["name"])
                if nm.lower() not in known:
                    devs.append({"id": "", "name": nm, "raw": nm,
                                 "source": "lms", "is_default": False,
                                 "playerid": str(p.get("id", ""))})
                    known.add(nm.lower())
    except Exception:
        pass
    # 再兜底：macOS 常见默认设备占位，保证界面至少可选项
    if not devs:
        devs = [{"id": "", "name": "系统默认输出 (default)", "raw": "default",
                 "source": "fallback", "is_default": True}]
        reasons.append("未扫描到具体设备，已提供默认输出项；可在上方填写设备名")
    return {"devices": devs, "reasons": reasons, "binary": binary or ""}


@_wrap
def saveDevice(device="", deviceName="", deviceShort="", hostName=None, nameTemplate=None):
    CFG["device"] = str(device or "")
    CFG["device_name"] = str(deviceName or "")
    CFG["device_short"] = str(deviceShort or "")
    if hostName is not None:
        CFG["host_name"] = str(hostName or "").strip()
    if nameTemplate is not None:
        CFG["name_template"] = str(nameTemplate or "").strip() or "{host} - {short}"
    c.save_config(CFG)
    # 计算最终在 LMS 显示的播放器名，便于前端回显
    try:
        nm = c.make_player_name(
            CFG.get("host_name") or c.local_host_name(),
            CFG.get("device_short") or "",
            CFG.get("name_template") or "{host} - {short}")
    except Exception:
        nm = ""
    return {"ok": True, "playerName": nm}


@_wrap
def getParams():
    """返回参数定义 + 当前值 + 预览命令 + 校验结果。"""
    values = {}
    for pdef in c.PARAMS:
        k = pdef["key"]
        values[k] = CFG.get(k, pdef.get("default", ""))
    extra = CFG.get("extra", "")
    argv = c.build_argv(CFG, values)
    return {"params": c.PARAMS, "values": values,
            "preview": c.preview_cmd(argv),
            "problems": c.validate_all(values, extra),
            "binary": c.find_binary(CFG) or ""}


@_wrap
def applyBestParams():
    """一键应用最优音质（bit-perfect）方案：每个参数取 recommend，
    但保留由设备/名称/LMS 页维护的联动项（output/name/server）。"""
    linked = {"output", "name", "server"}
    applied = {}
    for pdef in c.PARAMS:
        k = pdef.get("key")
        if not k or k in linked:
            continue
        rec = pdef.get("recommend", "")
        applied[k] = rec
    # 合并进现有 params（只覆盖非联动项）
    params = dict(CFG.get("params") or {})
    params.update(applied)
    CFG["params"] = params
    c.save_config(CFG)
    argv = c.build_argv(CFG, params)
    return {"ok": True, "applied": applied,
            "preview": c.preview_cmd(argv),
            "problems": c.validate_all(params, CFG.get("extra", ""))}


@_wrap
def saveParams(values=None, extra=""):
    values = values or {}
    for k, v in values.items():
        CFG[k] = v
    CFG["extra"] = str(extra or "")
    problems = c.validate_all(values, CFG.get("extra", ""))
    if problems:
        return {"ok": False, "problems": problems}
    c.save_config(CFG)
    argv = c.build_argv(CFG, values)
    return {"ok": True, "preview": c.preview_cmd(argv)}


@_wrap
def getLaunchInfo():
    binary = c.find_binary(CFG) or ""
    values = {}
    for pdef in c.PARAMS:
        k = pdef["key"]
        values[k] = CFG.get(k, pdef.get("default", ""))
    argv = c.build_argv(CFG, values)
    ver = c.sq_local_version(binary) if binary else None
    if isinstance(ver, dict):
        ver = ver.get("version") or ver.get("raw") or ""
    return {"binary": binary, "command": c.preview_cmd(argv),
            "version": ver or "",
            "autoRun": bool(CFG.get("auto_start")),
            "problems": c.validate_all(values, CFG.get("extra", ""))}


@_wrap
def setAutoStart(on=False):
    """真实开机自启：生成/卸载 macOS LaunchAgent，独立拉起 squeezelite。

    开启时用当前参数构建 argv，写入 ~/Library/LaunchAgents/，RunAtLoad+KeepAlive，
    这样即使 app 未打开，开机后也会自动启动 squeezelite 引擎并注册到 LMS。
    """
    on = bool(on)
    CFG["auto_start"] = on
    c.save_config(CFG)
    if not on:
        # 卸载：先 unload 再删 plist
        try:
            import subprocess as _sp
            if os.path.exists(c.LAUNCH_AGENT):
                _sp.run(["launchctl", "unload", c.LAUNCH_AGENT],
                        capture_output=True, timeout=10)
                os.remove(c.LAUNCH_AGENT)
                return {"ok": True, "autoStart": False,
                        "message": "已卸载开机自启（LaunchAgent 已移除）"}
        except Exception as e:
            return {"ok": False, "error": "卸载开机自启失败: %s" % str(e)[:150]}
        return {"ok": True, "autoStart": False, "message": "开机自启已关闭"}
    # 开启：校验参数并构建 argv
    values = {}
    for pdef in c.PARAMS:
        k = pdef["key"]
        values[k] = CFG.get(k, pdef.get("default", ""))
    problems = c.validate_all(values, CFG.get("extra", ""))
    if problems:
        return {"ok": False, "error": "参数未通过校验，无法设置开机自启：\n" + "\n".join(problems)}
    argv = c.build_argv(CFG, values)
    binary = argv[0]
    if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        return {"ok": False,
                "error": "找不到可执行的 squeezelite：%s\n请先在「播放器引擎」页指定二进制路径或更新安装。" % binary}
    ok, msg = c.make_launch_agent(CFG, argv, None)
    if not ok:
        return {"ok": False, "error": msg}
    # 立即 load，使本次登录即生效（无需重启）
    try:
        import subprocess as _sp
        _sp.run(["launchctl", "unload", c.LAUNCH_AGENT], capture_output=True, timeout=10)
        r = _sp.run(["launchctl", "load", c.LAUNCH_AGENT], capture_output=True, text=True, timeout=10)
        loaded = (r.returncode == 0)
        extra = "（已立即生效）" if loaded else "（下次登录生效：%s）" % (r.stderr or "")[:80]
    except Exception:
        extra = "（下次登录生效）"
    return {"ok": True, "autoStart": True,
            "message": "已设置开机自启 %s" % extra,
            "plist": c.LAUNCH_AGENT, "command": c.preview_cmd(argv)}


@_wrap
def getAutoStartStatus():
    """查询系统级开机自启状态（LaunchAgent 是否存在且已加载）。"""
    installed = os.path.exists(c.LAUNCH_AGENT)
    loaded = False
    if installed:
        try:
            import subprocess as _sp
            r = _sp.run(["launchctl", "list", "com.squeezelite.gui"],
                        capture_output=True, timeout=6)
            loaded = (r.returncode == 0)
        except Exception:
            loaded = False
    return {"ok": True, "enabled": bool(CFG.get("auto_start")),
            "installed": installed, "loaded": loaded,
            "plist": c.LAUNCH_AGENT, "isMac": c.IS_MAC}


@_wrap
def checkUpdates():
    """聚合 squeezelite 与 LMS 的最新版本信息（联网失败降级返回本地版本）。"""
    out = {"local": "", "squeezelite": {}, "lms": {}, "errors": []}
    binary = c.find_binary(CFG) or ""
    try:
        out["local"] = c.sq_local_version(binary) if binary else ""
    except Exception as e:
        out["errors"].append("本地版本: " + str(e)[:80])
    try:
        out["squeezelite"] = c.sq_latest(None, CFG)
    except Exception as e:
        out["errors"].append("squeezelite: " + str(e)[:80])
    try:
        out["lms"] = c.lms_latest(None, CFG)
    except Exception as e:
        out["errors"].append("LMS: " + str(e)[:80])
    return out


@_wrap
def getChangeLog(kind="sl"):
    items, used = c.changelog(str(kind or "sl"), None, CFG)
    return {"items": items[:20], "source": used}


@_wrap
def setAutoUpgrade(on=False):
    CFG["auto_upgrade_check"] = bool(on)
    c.save_config(CFG)
    return {"ok": True, "autoUpgrade": bool(on)}


@_wrap
def upgradeSqueezelite():
    """下载最新版本并就地替换 squeezelite 二进制（旧版自动备份）。

    从版本源重新查询最新 item，避免信任前端传入的下载地址。
    升级完成后若引擎正在运行，自动重启引擎使新二进制生效。
    """
    if not c.IS_MAC:
        return {"ok": False, "error": "自动更新 squeezelite 仅支持 macOS（当前 %s）" % sys.platform}
    logs = []
    def _log(msg):
        txt = str(msg)
        logs.append(txt)
        if len(logs) > 80:
            del logs[:-80]
    try:
        latest = c.sq_latest(_log, CFG)
        item = (latest.get("latest") or {})
        if not item.get("url"):
            return {"ok": False, "error": "未取得二进制下载地址（版本源降级）。请到 SourceForge 手动下载。",
                    "logs": logs}
        was_running = _engine_alive()
        if was_running:
            try:
                stopEngine()
                _log("升级前已暂停引擎")
            except Exception:
                pass
        ok, msg = c.upgrade_squeezelite(CFG, item, _log)
        if ok and was_running:
            try:
                time.sleep(0.5)
                r = startEngine()
                if r.get("ok"):
                    _log("升级后已自动重启引擎")
                else:
                    _log("升级成功，但引擎重启失败：%s" % r.get("error", ""))
            except Exception as e:
                _log("引擎重启异常: %s" % e)
        return {"ok": bool(ok), "message": msg, "logs": logs,
                "version": (c.sq_local_version(c.find_binary(CFG) or "", None) or {}).get("version", "")}
    except Exception as e:
        return {"ok": False, "error": "升级异常: %s" % str(e)[:200], "logs": logs}


# ================= 多端同播（LMS sync group）=================
@_wrap
def getSyncStatus():
    """返回所有播放器及其同步组信息。
    每个 player 带 syncWith（与之同步的 player id 列表）与 isMaster。
    LMS 约定：["sync","?"] 返回的 result 里 sync_loop/sync 给出组内成员；
    不同版本字段不一，做兼容解析。"""
    ps = c.np_players(CFG)
    out = []
    for p in ps:
        pid = str(p.get("id", ""))
        sync_with = []
        if p.get("connected"):
            try:
                r = c.lms_rpc(CFG, ["sync", "?"], pid, _id=72)
                # r 形如 {"sync_loop":[{"sync":"aa:bb:..,cc:dd:.."}]} 或 {"sync":"..."} 或字符串
                ids = ""
                if isinstance(r, dict):
                    sl = r.get("sync_loop") or []
                    if sl and isinstance(sl, list) and isinstance(sl[0], dict):
                        ids = sl[0].get("sync", "")
                    if not ids:
                        ids = r.get("sync", "")
                elif isinstance(r, str):
                    ids = r
                if ids and ids != "-":
                    sync_with = [str(x) for x in str(ids).split(",") if x]
            except Exception:
                pass
        out.append({
            "id": pid,
            "name": str(p.get("name", "")),
            "model": str(p.get("model", "")),
            "ip": str(p.get("ip", "")),
            "connected": bool(p.get("connected", 0)),
            "isplaying": bool(p.get("isplaying", 0)),
            "syncWith": sync_with,
        })
    # 主控 = 组内第一个（LMS 以被同步的目标为主）
    return {"players": out, "current": str(CFG.get("np_playerid", "")),
            "masterId": str(CFG.get("np_playerid", ""))}


@_wrap
def setSync(masterId, slaveIds=None):
    """把 slaveIds 加入 masterId 的同步组，实现多端同播。
    LMS 语义：对每个 slave 发 ["sync", masterId]（slave 跟随 master）。
    先让各 slave 退出原有组，再加入新组。"""
    slaveIds = slaveIds or []
    masterId = str(masterId or "")
    slaveIds = [str(x) for x in slaveIds if str(x) and str(x) != masterId]
    if not masterId:
        return {"ok": False, "error": "未指定主控播放器"}
    results = []
    for sid in slaveIds:
        try:
            c.lms_rpc(CFG, ["sync", "-"], sid, _id=73)       # 先退出旧组
            c.lms_rpc(CFG, ["sync", masterId], sid, _id=74)  # 加入主控组
            results.append({"id": sid, "ok": True})
        except Exception as e:
            results.append({"id": sid, "ok": False, "error": str(e)[:100]})
    CFG["np_playerid"] = masterId
    try:
        c.save_config(CFG)
    except Exception:
        pass
    ok = all(x.get("ok") for x in results) if results else True
    return {"ok": ok, "masterId": masterId, "results": results,
            "message": ("已将 %d 台设备同步到主控" % len(results)) if ok else "部分设备同步失败"}


@_wrap
def unsync(playerIds=None):
    """让指定播放器退出同步组；不传则退出当前主控以外全部。"""
    ps = c.np_players(CFG)
    all_ids = [str(p.get("id", "")) for p in ps if p.get("connected")]
    targets = [str(x) for x in (playerIds or [])] if playerIds else all_ids
    results = []
    for pid in targets:
        if not pid:
            continue
        try:
            c.lms_rpc(CFG, ["sync", "-"], pid, _id=75)
            results.append({"id": pid, "ok": True})
        except Exception as e:
            results.append({"id": pid, "ok": False, "error": str(e)[:100]})
    ok = all(x.get("ok") for x in results) if results else True
    return {"ok": ok, "results": results,
            "message": "已取消 %d 台设备的同步" % len(results)}


# 导出给 webview.create_window(js_api=...) 的对象实例。
# pywebview 要求实例方法形如 method(self, *args)，这里显式转发到上面的纯函数。
# ================= 增强：下钻 / 播放列表 / 播放模式 / 音量 / 详情 =================
def _pick_pid():
    """统一选取当前播放器 ID（优先配置，其次自动挑选）。"""
    pid = str(CFG.get("np_playerid") or "")
    if pid:
        return pid
    try:
        ps = c.np_players(CFG)
        pick = c.np_pick_player(CFG, ps, "")
        return str(pick.get("id", "")) if pick else ""
    except Exception:
        return ""


def _rpc_server(cmd, _id=90):
    """播放列表管理等服务端级命令（playerid 为空）。"""
    return c.lms_rpc(CFG, list(cmd), "", _id=_id)


@_wrap
def libInfo(item):
    """右键「显示信息」：把条目字段转成「标签：值」行。"""
    if not isinstance(item, dict):
        return {"lines": [], "text": "", "source": ""}
    t = dict(item)
    tid = str(t.get("id") or t.get("track_id") or "")
    src = "库条目"
    if tid:
        try:
            r = c.lms_rpc(CFG, ["songinfo", 0, 100, "track_id:" + tid,
                                "tags:alcygtKdSuBroI"], _id=91)
            loop = r.get("songinfo_loop") or []
            if loop and isinstance(loop[0], dict):
                merged = dict(loop[0])
                for k, v in t.items():
                    if v not in (None, "", "0"):
                        merged[k] = v
                t = merged
                src = "LMS songinfo + 库"
        except Exception:
            pass
    text = c.detail_lines(t)
    return {"lines": [x for x in text.split("\n") if x], "text": text, "source": src}


def _pl_items(r):
    loop = (r.get("playlists_loop") or r.get("playlist_loop") or r.get("loop") or [])
    out = []
    for it in loop:
        if not isinstance(it, dict):
            continue
        out.append({"id": str(it.get("id") or it.get("playlist_id") or ""),
                    "name": str(it.get("name") or it.get("playlist") or ""),
                    "trackcount": it.get("trackcount", it.get("tracks", 0))})
    return out


FAV_PLAYLIST_NAME = "♥ 收藏"
FAV_LOCAL_ID = "__local_favorites__"   # 虚拟列表 id，前端据此识别收藏列表

def _fav_file():
    return os.path.join(os.path.expanduser("~/.squeezelite_gui"), "favorites.json")

def _fav_load():
    """读取本地收藏（曲目 id -> 元信息）。完全本地，不依赖 LMS 播放列表接口。"""
    try:
        with open(_fav_file(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _fav_save(d):
    try:
        path = _fav_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False

def _fav_playlist():
    """兼容旧调用：返回虚拟收藏列表 id（本地收藏，恒可用）。"""
    return FAV_LOCAL_ID


@_wrap
def getFavorites():
    """获取收藏列表：本地持久化，即时可用；不再依赖 LMS 播放列表接口。"""
    d = _fav_load()
    items = []
    for tid, meta in d.items():
        if not isinstance(meta, dict):
            meta = {}
        items.append({"id": str(tid), "title": str(meta.get("title") or ""),
                      "artist": str(meta.get("artist") or ""), "album": str(meta.get("album") or "")})
    return {"ok": True, "playlistId": FAV_LOCAL_ID,
            "ids": [x["id"] for x in items], "items": items}


@_wrap
def toggleFavorite(trackId, favorited=None, meta=None):
    """收藏/取消收藏曲目：写入本地持久化。favorited=None 表示切换。
    meta 可带 title/artist/album，便于收藏列表显示名称。"""
    tid = str(trackId or "")
    if not tid:
        return {"ok": False, "error": "缺少曲目 ID"}
    d = _fav_load()
    has = tid in d
    want = (not has) if favorited is None else bool(favorited)
    if want and not has:
        m = meta if isinstance(meta, dict) else {}
        d[tid] = {"title": str(m.get("title") or ""), "artist": str(m.get("artist") or ""),
                  "album": str(m.get("album") or "")}
    elif not want and has:
        d.pop(tid, None)
    if not _fav_save(d):
        return {"ok": False, "error": "本地收藏写入失败"}
    return {"ok": True, "favorited": want, "playlistId": FAV_LOCAL_ID, "trackId": tid}


# ---- 本地播放列表持久化（LMS playlists 接口在本环境不可用，全部本地实现）----
_PL_FILE = os.path.join(os.path.expanduser("~/.squeezelite_gui"), "playlists.json")

def _pl_load():
    """返回 {pid: {"name":..., "tracks":[{id,title,artist,album}]}}"""
    try:
        with open(_PL_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _pl_save(d):
    try:
        os.makedirs(os.path.dirname(_PL_FILE), exist_ok=True)
        tmp = _PL_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PL_FILE)
        return True
    except Exception:
        return False

def _new_pid(d):
    """生成一个不冲突的本地列表 id。"""
    n = 1
    while ("pl%d" % n) in d:
        n += 1
    return "pl%d" % n

@_wrap
def getPlaylists():
    """播放列表：本地持久化列表 + 置顶虚拟「♥ 收藏」。"""
    d = _pl_load()
    items = []
    for pid, pl in d.items():
        if not isinstance(pl, dict):
            continue
        tracks = pl.get("tracks") or []
        items.append({"id": pid, "name": str(pl.get("name") or pid),
                      "trackcount": len(tracks), "local": True})
    fav = _fav_load()
    items.insert(0, {"id": FAV_LOCAL_ID, "name": FAV_PLAYLIST_NAME,
                     "trackcount": len(fav), "locked": True, "isFav": True})
    return {"items": items}

@_wrap
def createPlaylist(name):
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "播放列表名称不能为空"}
    if name == FAV_PLAYLIST_NAME:
        return {"ok": False, "error": "该名称为系统保留，不可用于新建列表"}
    d = _pl_load()
    for pl in d.values():
        if isinstance(pl, dict) and str(pl.get("name") or "").strip() == name:
            return {"ok": False, "error": "同名播放列表已存在"}
    pid = _new_pid(d)
    d[pid] = {"name": name, "tracks": []}
    if not _pl_save(d):
        return {"ok": False, "error": "本地播放列表写入失败"}
    return {"ok": True, "id": pid, "name": name, "playlistId": pid}

@_wrap
def deletePlaylist(playlistId):
    pid = str(playlistId or "")
    if not pid:
        return {"ok": False, "error": "缺少播放列表 ID"}
    if pid == FAV_LOCAL_ID:
        return {"ok": False, "error": "「♥ 收藏」为系统列表，不可删除"}
    d = _pl_load()
    if pid not in d:
        return {"ok": False, "error": "播放列表不存在"}
    d.pop(pid, None)
    if not _pl_save(d):
        return {"ok": False, "error": "本地播放列表写入失败"}
    return {"ok": True, "id": pid}

@_wrap
def renamePlaylist(playlistId, name):
    pid, name = str(playlistId or ""), str(name or "").strip()
    if not pid or not name:
        return {"ok": False, "error": "缺少参数"}
    if name == FAV_PLAYLIST_NAME or pid == FAV_LOCAL_ID:
        return {"ok": False, "error": "「♥ 收藏」为系统列表，不可重命名"}
    d = _pl_load()
    if pid not in d:
        return {"ok": False, "error": "播放列表不存在"}
    d[pid]["name"] = name
    if not _pl_save(d):
        return {"ok": False, "error": "本地播放列表写入失败"}
    return {"ok": True, "id": pid, "name": name}

@_wrap
def playlistAdd(playlistId, trackId, meta=None):
    pid, tid = str(playlistId or ""), str(trackId or "")
    if not pid or not tid:
        return {"ok": False, "error": "缺少播放列表或曲目 ID"}
    if pid == FAV_LOCAL_ID:
        return toggleFavorite(tid, True, meta)
    d = _pl_load()
    if pid not in d:
        return {"ok": False, "error": "播放列表不存在"}
    pl = d[pid]
    tracks = pl.setdefault("tracks", [])
    if any(str(x.get("id")) == tid for x in tracks if isinstance(x, dict)):
        return {"ok": True, "duplicate": True, "count": len(tracks)}
    m = meta if isinstance(meta, dict) else {}
    tracks.append({"id": tid, "title": str(m.get("title") or ""),
                   "artist": str(m.get("artist") or ""), "album": str(m.get("album") or "")})
    if not _pl_save(d):
        return {"ok": False, "error": "本地播放列表写入失败"}
    return {"ok": True, "count": len(tracks)}

@_wrap
def playlistRemove(playlistId, index):
    pid = str(playlistId or "")
    if not pid:
        return {"ok": False, "error": "缺少播放列表 ID"}
    if pid == FAV_LOCAL_ID:
        return {"ok": False, "error": "收藏列表请用取消收藏操作"}
    d = _pl_load()
    if pid not in d:
        return {"ok": False, "error": "播放列表不存在"}
    tracks = d[pid].setdefault("tracks", [])
    try:
        i = int(index)
    except Exception:
        return {"ok": False, "error": "曲目序号无效"}
    if i < 0 or i >= len(tracks):
        return {"ok": False, "error": "曲目序号越界"}
    tracks.pop(i)
    if not _pl_save(d):
        return {"ok": False, "error": "本地播放列表写入失败"}
    return {"ok": True, "count": len(tracks)}

@_wrap
def playlistTracks(playlistId):
    pid = str(playlistId or "")
    if not pid:
        return {"items": [], "ok": False, "error": "缺少播放列表 ID"}
    if pid == FAV_LOCAL_ID:
        fav = _fav_load()
        items = []
        for tid, meta in fav.items():
            m = meta if isinstance(meta, dict) else {}
            d0 = {"id": str(tid), "title": str(m.get("title") or ""),
                  "artist": str(m.get("artist") or ""), "album": str(m.get("album") or "")}
            d0["_name"] = d0["title"] or d0["album"] or d0["id"]
            items.append(d0)
        return {"items": items, "total": len(items)}
    d = _pl_load()
    if pid not in d:
        return {"items": [], "ok": False, "error": "播放列表不存在"}
    items = []
    for x in (d[pid].get("tracks") or []):
        if not isinstance(x, dict):
            continue
        d0 = {"id": str(x.get("id") or ""), "title": str(x.get("title") or ""),
              "artist": str(x.get("artist") or ""), "album": str(x.get("album") or "")}
        d0["_name"] = d0["title"] or d0["album"] or d0["id"]
        items.append(d0)
    return {"items": items, "total": len(items)}

@_wrap
def getQueue():
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "items": [], "error": "no player"}
    r = c.lms_rpc(CFG, ["status", "0", "500", "tags:al"], pid, _id=99)
    loop = r.get("playlist_loop") or []
    items = []
    for it in loop:
        if not isinstance(it, dict):
            continue
        d = {k: ("" if v is None else str(v)) for k, v in it.items()}
        d["_name"] = d.get("title") or d.get("album") or d.get("id") or ""
        items.append(d)
    return {"items": items, "total": len(items),
            "index": int(r.get("playlist_cur_index") or 0),
            "mode": str(r.get("playlist mode") or "0 0"),
            "playerId": pid}


@_wrap
def playlistPlayAll(playlistId, startIndex=0):
    """把本地歌单整单载入 LMS 播放队列并从指定曲目开始播放。
    这样队列里有多首歌，才能验证上一曲/下一曲/播完自动切歌。"""
    pid = str(playlistId or "")
    try:
        idx = int(startIndex)
    except Exception:
        idx = 0
    if pid == FAV_LOCAL_ID:
        fav = _fav_load()
        tids = [str(x) for x in fav.keys()]
    else:
        d = _pl_load()
        if pid not in d:
            return {"ok": False, "error": "播放列表不存在"}
        tids = [str(x.get("id")) for x in (d[pid].get("tracks") or [])
                if isinstance(x, dict) and x.get("id")]
    if not tids:
        return {"ok": False, "error": "歌单为空"}
    if idx < 0 or idx >= len(tids):
        idx = 0
    player = _pick_pid()
    if not player:
        return {"ok": False, "error": "播放器不在线"}
    try:
        c.lms_rpc(CFG, ["playlist", "clear"], player, _id=110)
    except Exception:
        pass
    added = 0
    for tid in tids:
        try:
            c.lms_rpc(CFG, ["playlistcontrol", "cmd:add", "track_id:" + tid], player, _id=111)
            added += 1
        except Exception:
            continue
    if added == 0:
        return {"ok": False, "error": "曲目载入失败"}
    try:
        c.lms_rpc(CFG, ["playlist", "index", str(idx)], player, _id=112)
    except Exception:
        c.lms_rpc(CFG, ["play", str(idx)], player, _id=113)
    return {"ok": True, "added": added, "index": idx, "total": len(tids)}

@_wrap
def queueAdd(trackId, playNext=False):
    tid = str(trackId or "")
    pid = _pick_pid()
    if not tid or not pid:
        return {"ok": False, "error": "缺少曲目或播放器"}
    # 关键修复：LMS 的 "playlist add" 需要 URL，纯数字 id 会被静默忽略；
    # 必须用 playlistcontrol + track_id:N（与 libPlay 的 load 同族），才能真正加入队列。
    cmd = "insert" if playNext else "add"
    before = getQueue()
    before_ids = [str(x.get("id")) for x in (before.get("items") or [])]
    c.lms_rpc(CFG, ["playlistcontrol", "cmd:" + cmd, "track_id:" + tid], pid, _id=100)
    # 复核：真实 LMS 下有些命令会返回 count 但队列没变，必须以队列结果为准
    after = getQueue()
    after_ids = [str(x.get("id")) for x in (after.get("items") or [])]
    ok = (len(after_ids) > len(before_ids)) or (tid in after_ids and cmd == "insert")
    return {"ok": ok, "next": bool(playNext), "trackId": tid,
            "queueCount": len(after_ids),
            "error": None if ok else "命令已发送但队列未变化（播放器可能不在线）"}


@_wrap
def queueRemove(index):
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    # 关键修复：LMS 删除队列项命令是 playlist delete，非 del（del 会导致 Remote end closed）
    c.lms_rpc(CFG, ["playlist", "delete", str(index)], pid, _id=101)
    return {"ok": True}


@_wrap
def queuePlayIndex(index):
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    c.lms_rpc(CFG, ["playlist", "index", str(index)], pid, _id=102)
    return {"ok": True}


@_wrap
def queueClear():
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    c.lms_rpc(CFG, ["playlist", "clear"], pid, _id=103)
    return {"ok": True}


@_wrap
def setPlayMode(shuffle=0, repeat=0):
    """shuffle 0关/1随机/2按专辑；repeat 0关/1列表循环/2单曲循环。"""
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    c.lms_rpc(CFG, ["playlist", "shuffle", str(int(shuffle))], pid, _id=104)
    c.lms_rpc(CFG, ["playlist", "repeat", str(int(repeat))], pid, _id=105)
    return {"ok": True, "shuffle": int(shuffle), "repeat": int(repeat)}


@_wrap
def setVolume(value):
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    v = vol_to_lms(value)
    c.lms_rpc(CFG, ["mixer", "volume", str(v)], pid, _id=106)
    return {"ok": True, "volume": v, "slider": int(max(0, min(100, float(value))))}


_PREV_VOLUME = {"value": None}


@_wrap
def toggleMute():
    """一键静音/恢复：静音时记住当前音量并设为 0；恢复时还原。"""
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "没有在线播放器：请先在「播放器引擎」页启动 squeezelite 引擎，等待它注册到 LMS 后再静音。"}
    try:
        st = c.np_status(CFG, pid)
    except Exception as _e:
        return {"ok": False, "error": "读取播放器状态失败（%s）。请确认 squeezelite 引擎已启动并在线。" % str(_e)[:60]}
    cur = int(st.get("volume", 0) or 0)
    if cur > 0:
        _PREV_VOLUME["value"] = cur
        c.lms_rpc(CFG, ["mixer", "volume", "0"], pid, _id=108)
        return {"ok": True, "muted": True, "volume": 0}
    # 当前为 0：恢复
    restore = _PREV_VOLUME["value"] or 60
    c.lms_rpc(CFG, ["mixer", "volume", str(restore)], pid, _id=109)
    return {"ok": True, "muted": False, "volume": vol_from_lms(restore)}


@_wrap
def setSeek(seconds):
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    c.lms_rpc(CFG, ["seek", str(max(0, int(seconds)))], pid, _id=107)
    return {"ok": True}



# ================= squeezelite 引擎进程管理 =================
def _engine_log(line):
    txt = str(line).rstrip("\n")
    if not txt:
        return
    # 实时解析 squeezelite -d 输出：转码/直通判定依赖实际输出采样率
    try:
        _st = dict(_AUDIO_STATE)
        _parsed, _hit = c.parse_sl_output(txt, _st)
        if _hit and isinstance(_parsed, dict):
            _lines = list(_AUDIO_STATE.get("lines", []))
            _lines.append(txt)
            _parsed["lines"] = _lines[-200:]
            _AUDIO_STATE.clear()
            _AUDIO_STATE.update(_parsed)
    except Exception:
        pass
    with _ENGINE_LOCK:
        _ENGINE["logs"].append(txt)
        if len(_ENGINE["logs"]) > _LOG_MAX:
            del _ENGINE["logs"][:-_LOG_MAX]


def _engine_reader(proc):
    """守护线程：持续读引擎输出，记录日志并检测退出。
    macOS 用 posix_spawn + 日志文件（规避 fork 的 SYN_SENT bug）；
    其他平台仍用 Popen 的 stdout pipe。"""
    code = None
    log_path = _ENGINE.get("log_path", "")
    spawn_pid = _ENGINE.get("spawn_pid", 0)
    try:
        if log_path:
            # tail 日志文件模式
            import time as _t
            f = open(log_path, "r", encoding="utf-8", errors="replace")
            while True:
                line = f.readline()
                if line:
                    _engine_log(line)
                    continue
                # 检查进程是否退出
                exited = False
                if spawn_pid:
                    try:
                        os.kill(spawn_pid, 0)
                    except OSError:
                        exited = True
                elif proc is not None:
                    exited = (proc.poll() is not None)
                if exited:
                    # 读完剩余日志
                    for rest in f:
                        _engine_log(rest)
                    f.close()
                    code = 0
                    try:
                        if spawn_pid:
                            _, st = os.waitpid(spawn_pid, os.WNOHANG)
                            code = os.waitstatus_to_exitcode(st) if st is not None else 0
                        elif proc is not None:
                            code = proc.poll()
                    except Exception:
                        pass
                    break
                _t.sleep(0.2)
        else:
            for line in iter(proc.stdout.readline, ""):
                _engine_log(line)
    except Exception as e:
        _engine_log("[reader] %s" % e)
    finally:
        with _ENGINE_LOCK:
            _ENGINE["exit_code"] = code if code is not None else (proc.poll() if proc else 0)
            _ENGINE["logs"].append("[进程已退出 code=%s]" % code)
        _engine_log("[引擎进程结束 code=%s]" % code)
        # 意外退出（非手动停止）时自动重启，最多 3 次
        with _ENGINE_LOCK:
            manual = _ENGINE.get("manual_stop", False)
            restarts = _ENGINE.get("restarts", 0)
        if not manual and restarts < 3:
            _engine_log("[看门狗] 引擎意外退出，%s 秒后自动重启（%s/3）" % (2, restarts + 1))
            def _restart():
                import time as _t
                _t.sleep(2)
                try:
                    with _ENGINE_LOCK:
                        _ENGINE["restarts"] = _ENGINE.get("restarts", 0) + 1
                    startEngine()
                except Exception as e:
                    _engine_log("[看门狗] 重启失败: %s" % str(e)[:100])
            threading.Thread(target=_restart, daemon=True).start()


def _engine_alive():
    sp = _ENGINE.get("spawn_pid", 0)
    if sp:
        # 手动停止后 waitpid 回收，避免僵尸进程误判为“仍在运行”
        if _ENGINE.get("manual_stop"):
            try:
                os.waitpid(sp, os.WNOHANG)
            except Exception:
                pass
            return False
        try:
            os.kill(sp, 0)
            return True
        except OSError:
            return False
    p = _ENGINE["proc"]
    return bool(p and p.poll() is None)


@_wrap
def engineStatus():
    """返回引擎实时状态：running/pid/命令/日志/退出码。"""
    alive = _engine_alive()
    with _ENGINE_LOCK:
        logs = list(_ENGINE["logs"][-120:])
    return {"ok": True, "running": alive, "pid": _ENGINE["pid"] if alive else 0,
            "uptime": int(_time.time() - _ENGINE["start_ts"]) if alive else 0,
            "command": c.preview_cmd(_ENGINE["argv"]) if _ENGINE["argv"] else "",
            "exitCode": _ENGINE["exit_code"], "logs": logs,
            "binary": c.find_binary(CFG) or ""}


@_wrap
def startEngine():
    """真正启动 squeezelite 进程并注册到 LMS。"""
    if _engine_alive():
        return {"ok": True, "already": True, "pid": _ENGINE["pid"],
                "message": "squeezelite 已在运行"}
    values = {}
    for pdef in c.PARAMS:
        k = pdef["key"]
        values[k] = CFG.get(k, pdef.get("default", ""))
    # 用联动补全后的真实参数校验（server/name/output 来自其它设置页）
    values = c._link_values(CFG, values)
    problems = c.validate_all(values, CFG.get("extra", ""))
    if problems:
        return {"ok": False, "error": "参数校验未通过：\n" + "\n".join(problems)}
    argv = c.build_argv(CFG, values)
    # 打开 SlimProto 日志，让"是否连上 LMS"在引擎日志里可见
    if not any(a == "-d" or (isinstance(a, str) and a.startswith("all=")) for a in argv):
        # 已有参数页配置的 loglevel 时尊重它；否则用 all=info 覆盖调试输出
        if not any(str(a).startswith("output=") for a in argv):
            argv += ["-d", "all=info"]
    binary = argv[0]
    if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        return {"ok": False,
                "error": "找不到可执行的 squeezelite：%s\n\n请到「播放器引擎」页指定二进制路径，或到「升级与更新」页安装 squeezelite。" % binary}
    # macOS 上 PyInstaller/WKWebView 进程用 fork 派生子进程时，
    # 子进程的 TCP 连接会卡在 SYN_SENT（真机实测）。改用 posix_spawn 规避。
    log_path = ""
    spawn_pid = 0
    proc = None
    if sys.platform == "darwin" and hasattr(os, "posix_spawn"):
        try:
            fd, log_path = tempfile.mkstemp(prefix="sonora-sq-", suffix=".log")
            os.close(fd)
            logf = open(log_path, "ab", buffering=0)
            file_actions = [(os.POSIX_SPAWN_DUP2, logf.fileno(), 1),
                            (os.POSIX_SPAWN_DUP2, logf.fileno(), 2)]
            spawn_pid = os.posix_spawn(argv[0], argv, os.environ, file_actions=file_actions)
            logf.close()
        except Exception as e:
            return {"ok": False, "error": "启动失败(posix_spawn)：%s" % str(e)[:200]}
    else:
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    bufsize=1, creationflags=(0x08000000 if sys.platform == "win32" else 0))
        except Exception as e:
            return {"ok": False, "error": "启动失败：%s" % str(e)[:200]}
    with _ENGINE_LOCK:
        _ENGINE["manual_stop"] = False
        _ENGINE["restarts"] = 0
        _ENGINE["proc"] = proc
        _ENGINE["pid"] = spawn_pid if spawn_pid else proc.pid
        _ENGINE["log_path"] = log_path
        _ENGINE["spawn_pid"] = spawn_pid
        _ENGINE["start_ts"] = _time.time()
        _ENGINE["logs"] = ["$ %s\n" % c.preview_cmd(argv)]
        _ENGINE["exit_code"] = None
        _ENGINE["argv"] = list(argv)
        _AUDIO_STATE.clear()  # 新一轮引擎，清空上一轮的直通判定
    t = threading.Thread(target=_engine_reader, args=(proc,), daemon=True)
    t.start()
    # 延迟验证：2 秒后查 LMS 是否真的看到播放器，把结果写进日志
    def _verify():
        import time as _t
        _t.sleep(3)
        if not _engine_alive():
            _engine_log("[注册验证] 引擎进程已退出，请查看上方日志")
            return
        try:
            ps = c.np_players(CFG)
            want = ""
            try:
                want = c.make_player_name(CFG.get("host_name") or c.local_host_name(),
                                          CFG.get("device_short") or "",
                                          CFG.get("name_template") or "{host} - {short}")
            except Exception:
                pass
            hit = [x for x in ps if (want and x.get("name") == want) or
                   (x.get("name") and str(x.get("name")).lower().startswith("squeezelite"))]
            if hit:
                _engine_log("[注册验证] ✅ 播放器已在 LMS 上线: %s" % hit[0].get("name"))
            else:
                _engine_log("[注册验证] ⚠ 进程在运行，但 LMS 尚未显示播放器。检查 LMS 是否开启认证/防火墙，或等待几秒后点刷新。")
        except Exception as e:
            _engine_log("[注册验证] 查询失败: %s" % str(e)[:100])
    threading.Thread(target=_verify, daemon=True).start()
    final_pid = spawn_pid if spawn_pid else (proc.pid if proc else 0)
    return {"ok": True, "pid": final_pid, "command": c.preview_cmd(argv),
            "message": "squeezelite 已启动 (PID %s)，正在注册到 LMS…" % final_pid}


@_wrap
def stopEngine():
    """停止 squeezelite 进程。"""
    if not _engine_alive():
        return {"ok": True, "already": True, "message": "引擎未在运行"}
    sp = _ENGINE.get("spawn_pid", 0)
    p = _ENGINE["proc"]
    try:
        if sp:
            os.kill(sp, signal.SIGTERM)
        elif p:
            p.terminate()
            try:
                p.wait(timeout=4)
            except Exception:
                p.kill()
    except Exception as e:
        return {"ok": False, "error": "停止失败：%s" % str(e)[:150]}
    with _ENGINE_LOCK:
        _ENGINE["manual_stop"] = True
        _ENGINE["exit_code"] = (p.poll() if p else 0)
        _ENGINE["logs"].append("[已停止引擎]")
    return {"ok": True, "message": "squeezelite 已停止"}


def _auto_start_engine():
    """若配置了开机自启且进程未运行，则自动拉起。"""
    try:
        if CFG.get("auto_start") and not _engine_alive():
            r = startEngine()
            if r.get("ok"):
                _engine_log("[开机自启] squeezelite 已自动拉起 PID %s" % r.get("pid"))
    except Exception:
        pass


# 模块加载后延迟触发自启（等主程序窗口初始化，避免阻塞导入）
threading.Timer(2.0, _auto_start_engine).start()


class BridgeAPI:
    def engineStatus(self): return engineStatus()
    def startEngine(self): return startEngine()
    def stopEngine(self): return stopEngine()
    def getConnection(self): return getConnection()
    def applyBestParams(self): return applyBestParams()
    def toggleMute(self): return toggleMute()
    def getMeta(self): return getMeta()
    def getConfig(self): return getConfig()
    def setTheme(self, name): return setTheme(name)
    def getPlayers(self): return getPlayers()
    def getStatus(self, playerId=""): return getStatus(playerId)
    def getCover(self, track, size=420): return getCover(track, size)
    def getLyrics(self, track): return getLyrics(track)
    def getLyricSources(self, track): return getLyricSources(track)
    def setLyricChoice(self, track, source, text): return setLyricChoice(track, source, text)
    def clearLyricChoice(self, track): return clearLyricChoice(track)
    def setFocusChrome(self, on): return setFocusChrome(on)
    def getBio(self, artist, album=""): return getBio(artist, album)
    def getAudio(self, track): return getAudio(track)
    def playControl(self, cmd): return playControl(cmd)
    def libBrowse(self, mode="albums", start=0, count=50, filters=None, query=""):
        return libBrowse(mode, start, count, filters, query)
    def libPlay(self, mode, itemId): return libPlay(mode, itemId)
    def getLibrary(self, limit=120): return getLibrary(limit)
    # 阶段 2 设置子页
    def testServer(self, host="", port="9000", user="", password=""): return testServer(host, port, user, password)
    def saveServer(self, host, port="9000", user="", password="", playerId=""): return saveServer(host, port, user, password, playerId)
    def scanDevices(self): return scanDevices()
    def saveDevice(self, device="", deviceName="", deviceShort="", hostName=None, nameTemplate=None): return saveDevice(device, deviceName, deviceShort, hostName, nameTemplate)
    def getParams(self): return getParams()
    def saveParams(self, values=None, extra=""): return saveParams(values, extra)
    def getLaunchInfo(self): return getLaunchInfo()
    def setAutoStart(self, on=False): return setAutoStart(on)
    def getAutoStartStatus(self): return getAutoStartStatus()
    def upgradeSqueezelite(self): return upgradeSqueezelite()
    def checkUpdates(self): return checkUpdates()
    def getChangeLog(self, kind="sl"): return getChangeLog(kind)
    def setAutoUpgrade(self, on=False): return setAutoUpgrade(on)
    # 多端同播
    def getSyncStatus(self): return getSyncStatus()
    def setSync(self, masterId, slaveIds=None): return setSync(masterId, slaveIds)
    def unsync(self, playerIds=None): return unsync(playerIds)
    # 增强：下钻/播放列表/播放模式/音量/详情
    def libInfo(self, item): return libInfo(item)
    # 收藏
    def getFavorites(self): return getFavorites()
    def toggleFavorite(self, trackId, favorited=None, meta=None): return toggleFavorite(trackId, favorited, meta)
    def getPlaylists(self): return getPlaylists()
    def createPlaylist(self, name): return createPlaylist(name)
    def deletePlaylist(self, playlistId): return deletePlaylist(playlistId)
    def renamePlaylist(self, playlistId, name): return renamePlaylist(playlistId, name)
    def playlistAdd(self, playlistId, trackId, meta=None): return playlistAdd(playlistId, trackId, meta)
    def playlistRemove(self, playlistId, index): return playlistRemove(playlistId, index)
    def playlistTracks(self, playlistId): return playlistTracks(playlistId)
    def playlistPlayAll(self, playlistId, startIndex=0): return playlistPlayAll(playlistId, startIndex)
    def getQueue(self): return getQueue()
    def queueAdd(self, trackId, playNext=False): return queueAdd(trackId, playNext)
    def queueRemove(self, index): return queueRemove(index)
    def queuePlayIndex(self, index): return queuePlayIndex(index)
    def queueClear(self): return queueClear()
    def setPlayMode(self, shuffle=0, repeat=0): return setPlayMode(shuffle, repeat)
    def setVolume(self, value): return setVolume(value)
    def setSeek(self, seconds): return setSeek(seconds)

api = BridgeAPI()
