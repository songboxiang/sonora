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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legacy_core as c

CFG = c.load_config()
_AUDIO_STATE = {}   # parse_sl_output 的增量状态（跨 getAudio 调用）


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
            "platform": sys.platform, "bridge": "pywebview-v2.0"}


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
            return {"connected": True, "state": "online",
                    "label": "已连接", "url": r.get("url", ""),
                    "version": r.get("version", "")}
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
    return st


# ---- 封面 / 歌词 / 简介 / 音频 ----
@_wrap
def getCover(track, size=420):
    if not isinstance(track, dict):
        return None
    coverid = str(track.get("coverid") or track.get("artwork_track_id") or "")
    url = str(track.get("artwork_url") or "")
    if not coverid and not url:
        return None
    full_url = c.np_cover_url(CFG, coverid, url)
    if not full_url:
        return None
    try:
        data = c.http_get(full_url, timeout=8)
    except Exception:
        return None
    if not data:
        return None
    try:
        png = c.decode_cover_png(data, max_size=int(size), square=True,
                                 pad_color=c.THEMES.get(CFG.get("theme", "light"), {})
                                            .get("cover_pad", "#0d292d"))
    except Exception:
        png = None
    if not png:
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


@_wrap
def getLyrics(track):
    if not isinstance(track, dict):
        return {"text": "", "source": "", "timed": False}
    text, src = c.np_lyrics_resolve(CFG, track, CFG.get("np_playerid", ""))
    parsed = c.parse_lrc(text or "")
    return {"text": text or "", "source": src or "",
            "timed": bool(parsed.get("timed")),
            "lines": parsed.get("lines", [])}


@_wrap
def getBio(artist, album=""):
    a, b, src = c.bio_fetch(CFG, str(artist or ""), str(album or ""))
    return {"artist": a or "", "album": b or "", "source": src or ""}


@_wrap
def getAudio(track):
    if not isinstance(track, dict):
        return {"spec": {}, "verdict": {}, "slState": {}}
    spec = c.audio_spec(track) or {}
    # 尝试从启动日志状态里找 squeezelite 输出信息（若进程在跑）
    sl_lines = getattr(c, "_SL_LOG_LINES", [])[-40:]
    st = {}
    for line in sl_lines:
        try:
            st = c.parse_sl_output(line, st) or st
        except Exception:
            pass
    verdict = c.audio_link_verdict(spec, st, st, True)
    if isinstance(verdict, (tuple, list)) and len(verdict) >= 3:
        verdict = {"level": verdict[0], "title": verdict[1], "detail": verdict[2]}
    return {"spec": spec, "verdict": verdict, "slState": st}


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
    rpc_map = {"play": "play", "pause": "pause", "stop": "stop",
               "next": "playlist jump +1", "prev": "playlist jump -1"}
    c.lms_rpc(CFG, [rpc_map[cmd]], pid, _id=60)
    return {"ok": True, "cmd": cmd}


# ---- 音乐库（阶段 1 顺手暴露，前端可选实现）----
@_wrap
def libBrowse(mode="albums", start=0, count=50, filters=None, query=""):
    items, total = c.lib_browse(CFG, str(mode), int(start), int(count),
                                str(query or ""), filters or [])
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
        if url:
            url = url.replace("cover_300x300", "cover_96x96")                      .replace("cover.jpg", "cover_96x96.jpg")
        import urllib.request
        hdr = c.lms_auth_headers(CFG)
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=4) as r:
            raw = r.read()
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
    return {"binary": binary, "command": c.preview_cmd(argv),
            "version": c.sq_local_version(binary) if binary else "",
            "autoRun": bool(CFG.get("auto_start")),
            "problems": c.validate_all(values, CFG.get("extra", ""))}


@_wrap
def setAutoStart(on=False):
    CFG["auto_start"] = bool(on)
    c.save_config(CFG)
    return {"ok": True, "autoStart": bool(on)}


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


def _fav_playlist():
    """找到（或自动创建）固定的收藏播放列表，返回其 id。"""
    r = _rpc_server(["playlists"], _id=120)
    for it in _pl_items(r):
        if it.get("name") == FAV_PLAYLIST_NAME:
            return it.get("id") or ""
    # 不存在则创建
    _rpc_server(["playlists", "new", FAV_PLAYLIST_NAME], _id=121)
    r2 = _rpc_server(["playlists"], _id=122)
    for it in _pl_items(r2):
        if it.get("name") == FAV_PLAYLIST_NAME:
            return it.get("id") or ""
    return ""


@_wrap
def getFavorites():
    """获取固定收藏列表：返回曲目 id 集合（用于心形点亮）。"""
    pid = _fav_playlist()
    if not pid:
        return {"ok": False, "items": [], "ids": [], "error": "无法获取收藏列表"}
    r = _rpc_server(["playlists", "tracks", pid, "0", "500"], _id=123)
    loop = (r.get("playlist_tracks_loop") or r.get("titles_loop")
            or r.get("playlist_loop") or [])
    ids, items = [], []
    for it in loop:
        if not isinstance(it, dict):
            continue
        tid = str(it.get("id") or it.get("track_id") or "")
        ids.append(tid)
        items.append({"id": tid, "title": str(it.get("title") or ""),
                      "artist": str(it.get("artist") or ""), "album": str(it.get("album") or "")})
    return {"ok": True, "playlistId": pid, "ids": ids, "items": items}


@_wrap
def toggleFavorite(trackId, favorited=None):
    """收藏/取消收藏曲目：自动加入或移出固定「♥ 收藏」列表。
    favorited=None 表示切换；True 强制收藏；False 强制取消。"""
    tid = str(trackId or "")
    if not tid:
        return {"ok": False, "error": "缺少曲目 ID"}
    pid = _fav_playlist()
    if not pid:
        return {"ok": False, "error": "无法获取收藏列表"}
    fav = getFavorites()
    ids = list(fav.get("ids") or [])
    has = tid in ids
    want = (not has) if favorited is None else bool(favorited)
    if want and not has:
        _rpc_server(["playlists", "add", pid, tid], _id=124)
    elif not want and has:
        # 从后往前删除所有同名曲目，避免重复收藏残留导致取消后仍在列表内
        for idx in [i for i, x in enumerate(ids) if x == tid][::-1]:
            _rpc_server(["playlists", "del", pid, str(idx)], _id=125)
    return {"ok": True, "favorited": want, "playlistId": pid, "trackId": tid}


@_wrap
def getPlaylists():
    r = _rpc_server(["playlists"], _id=92)
    items = _pl_items(r)
    favpid = _fav_playlist()
    for p in items:
        if str(p.get("id")) == str(favpid):
            p["locked"] = True
            p["isFav"] = True
    return {"items": items}


@_wrap
def createPlaylist(name):
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "播放列表名称不能为空"}
    if name == FAV_PLAYLIST_NAME:
        return {"ok": False, "error": "该名称为系统保留，不可用于新建列表"}
    _rpc_server(["playlists", "new", name], _id=93)
    return {"ok": True, "name": name}


@_wrap
def deletePlaylist(playlistId):
    pid = str(playlistId or "")
    if not pid:
        return {"ok": False, "error": "缺少播放列表 ID"}
    # 「♥ 收藏」为系统内置列表，禁止删除
    if pid == _fav_playlist():
        return {"ok": False, "error": "「♥ 收藏」为系统列表，不可删除"}
    _rpc_server(["playlists", "del", pid], _id=94)
    return {"ok": True, "id": pid}


@_wrap
def renamePlaylist(playlistId, name):
    pid, name = str(playlistId or ""), str(name or "").strip()
    if not pid or not name:
        return {"ok": False, "error": "缺少参数"}
    if name == FAV_PLAYLIST_NAME or pid == _fav_playlist():
        return {"ok": False, "error": "「♥ 收藏」为系统列表，不可重命名"}
    _rpc_server(["playlists", "rename", pid, name], _id=95)
    return {"ok": True, "id": pid, "name": name}


@_wrap
def playlistAdd(playlistId, trackId):
    pid, tid = str(playlistId or ""), str(trackId or "")
    if not pid or not tid:
        return {"ok": False, "error": "缺少播放列表或曲目 ID"}
    _rpc_server(["playlists", "add", pid, tid], _id=96)
    return {"ok": True}


@_wrap
def playlistRemove(playlistId, index):
    pid = str(playlistId or "")
    if not pid:
        return {"ok": False, "error": "缺少播放列表 ID"}
    _rpc_server(["playlists", "del", pid, str(index)], _id=97)
    return {"ok": True}


@_wrap
def playlistTracks(playlistId):
    pid = str(playlistId or "")
    if not pid:
        return {"items": [], "ok": False, "error": "缺少播放列表 ID"}
    r = _rpc_server(["playlists", "tracks", pid, "0", "500"], _id=98)
    loop = (r.get("playlist_tracks_loop") or r.get("titles_loop")
            or r.get("playlist_loop") or [])
    items = []
    for it in loop:
        if not isinstance(it, dict):
            continue
        d = {k: ("" if v is None else str(v)) for k, v in it.items()}
        d["_name"] = d.get("title") or d.get("album") or d.get("id") or ""
        items.append(d)
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
def queueAdd(trackId, playNext=False):
    tid = str(trackId or "")
    pid = _pick_pid()
    if not tid or not pid:
        return {"ok": False, "error": "缺少曲目或播放器"}
    cmd = "insert" if playNext else "add"
    c.lms_rpc(CFG, ["playlist", cmd, tid], pid, _id=100)
    return {"ok": True, "next": bool(playNext)}


@_wrap
def queueRemove(index):
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    c.lms_rpc(CFG, ["playlist", "del", str(index)], pid, _id=101)
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
    v = max(0, min(100, int(value)))
    c.lms_rpc(CFG, ["mixer", "volume", str(v)], pid, _id=106)
    return {"ok": True, "volume": v}


_PREV_VOLUME = {"value": None}


@_wrap
def toggleMute():
    """一键静音/恢复：静音时记住当前音量并设为 0；恢复时还原。"""
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    st = c.np_status(CFG, pid)
    cur = int(st.get("volume", 0) or 0)
    if cur > 0:
        _PREV_VOLUME["value"] = cur
        c.lms_rpc(CFG, ["mixer", "volume", "0"], pid, _id=108)
        return {"ok": True, "muted": True, "volume": 0}
    # 当前为 0：恢复
    restore = _PREV_VOLUME["value"] or 60
    c.lms_rpc(CFG, ["mixer", "volume", str(restore)], pid, _id=109)
    return {"ok": True, "muted": False, "volume": restore}


@_wrap
def setSeek(seconds):
    pid = _pick_pid()
    if not pid:
        return {"ok": False, "error": "no player"}
    c.lms_rpc(CFG, ["seek", str(max(0, int(seconds)))], pid, _id=107)
    return {"ok": True}


class BridgeAPI:
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
    def toggleFavorite(self, trackId, favorited=None): return toggleFavorite(trackId, favorited)
    def getPlaylists(self): return getPlaylists()
    def createPlaylist(self, name): return createPlaylist(name)
    def deletePlaylist(self, playlistId): return deletePlaylist(playlistId)
    def renamePlaylist(self, playlistId, name): return renamePlaylist(playlistId, name)
    def playlistAdd(self, playlistId, trackId): return playlistAdd(playlistId, trackId)
    def playlistRemove(self, playlistId, index): return playlistRemove(playlistId, index)
    def playlistTracks(self, playlistId): return playlistTracks(playlistId)
    def getQueue(self): return getQueue()
    def queueAdd(self, trackId, playNext=False): return queueAdd(trackId, playNext)
    def queueRemove(self, index): return queueRemove(index)
    def queuePlayIndex(self, index): return queuePlayIndex(index)
    def queueClear(self): return queueClear()
    def setPlayMode(self, shuffle=0, repeat=0): return setPlayMode(shuffle, repeat)
    def setVolume(self, value): return setVolume(value)
    def setSeek(self, seconds): return setSeek(seconds)

api = BridgeAPI()
