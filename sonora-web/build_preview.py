#!/usr/bin/env python3
"""生成自包含验证预览 preview.html（内联 tokens/app/refine CSS + 模拟 bridge）。
所有素材从 web/ 目录读取，数据快照优先读同目录 library.json。"""
from pathlib import Path
import base64, json, sys

ROOT = Path(__file__).parent
WEB = ROOT / "web"
html = (WEB / "index.html").read_text()
css = "\n".join((WEB / f).read_text() for f in ("tokens.css", "app.css", "refine.css", "refine2.css", "refine3.css", "refine4.css"))
js = (WEB / "app.js").read_text()
logo = (WEB / "assets/logo-mark.svg").read_text()
logo_uri = "data:image/svg+xml;base64," + base64.b64encode(logo.encode()).decode()

# 音乐库数据：优先用真实快照，否则用内置模拟数据
snap = Path(__file__).parent / "library.json"
if snap.exists():
    lib = json.loads(snap.read_text())
else:
    cn = [("唱游","王菲"),("初恋","宇多田光"),("范特西 [SHM-CD]","周杰伦"),("歌坛杰作·经典","王杰"),
     ("黒神话:悟空","游戏科学&8082Audio"),("吉姆餐厅","赵雷"),("酒红色的心 UPM24","玉置浩二"),("宽容","张信哲"),
     ("那有怎样 [台湾首版]","那英"),("情歌精选","张信哲"),("认了吧","陈奕迅"),("如果雲知道","许茹芸"),
     ("大海","张雨生"),("记忆","张信哲"),("爱如潮水","张信哲"),("心太软","任贤齐"),
     ("相约一九九八","那英"),("味道","辛晓琪"),("吻别","张学友"),("漫步人生路","邓丽君"),
     ("夜色","齐秦"),("朋友","周华健"),("明天会更好","群星"),("光辉岁月","Beyond"),
     ("海阔天空","Beyond"),("真的爱你","Beyond"),("情人","Beyond"),("喜欢你","Beyond"),
     ("无间道","刘德华"),("忘情水","刘德华"),("男人哭吧不是罪","刘德华"),("练习","刘德华"),
     ("红豆","王菲"),("天空","王菲"),("寓言","王菲"),("只爱陌生人","王菲"),
     ("阳光空气","王菲"),("compute","群星"),("匆匆那年","王菲"),("因为爱情","王菲/陈奕迅"),
     ("传奇","李健"),("贝加尔湖畔","李健"),("父亲写的散文诗","许飞"),("消愁","毛不易"),
     ("像我这样的人","毛不易"),("平凡的一天","毛不易"),("一荤一素","毛不易"),("胡广生","任素汐"),
     ("equilibra","群星"),("天长地久","周杰伦"),("简单爱","周杰伦"),("七里香","周杰伦"),
     ("夜曲","周杰伦"),("青花瓷","周杰伦"),("双截棍","周杰伦"),("稻香","周杰伦"),
     ("晴天","周杰伦"),("告白气球","周杰伦"),("安静","周杰伦"),("菊次郎的夏天","久石让")]
    latin = [("A Thousand Miles","Vanessa Carlton"),("Bad","Michael Jackson"),("Zebra","Unknown")]
    def cover(text, seed):
        hue=(seed*37)%360
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="hsl({hue},45%,45%)"/><stop offset="1" stop-color="hsl({(hue+55)%360},40%,22%)"/></linearGradient></defs><rect width="120" height="120" fill="url(#g)"/><text x="60" y="65" font-size="13" fill="rgba(255,255,255,.85)" text-anchor="middle" font-family="sans-serif">{text[:6]}</text></svg>'''
        return "data:image/svg+xml;base64,"+base64.b64encode(svg.encode()).decode()
    albums=[{"id":f"alb-{i}","album":a,"artist":ar,"coverid":f"c{i}","_cover":cover(a,i)} for i,(a,ar) in enumerate(cn+latin)]
    lib={
     "albums":{"items":albums,"total":len(albums)},
     "artists":{"items":[{"id":f"ar-{i}","artist":ar,"_name":ar} for i,(a,ar) in enumerate(cn+latin)],"total":len(cn+latin)},
     "titles":{"items":[{"id":f"tr-{i}","title":a,"artist":ar,"duration":200+i,"_name":a,"coverid":f"c{i}","_cover":cover(a,i)} for i,(a,ar) in enumerate(cn+latin)],"total":len(cn+latin)},
     "genres":{"items":[{"id":f"ge-{i}","genre":g,"_name":g} for i,g in enumerate(["流行","摇滚","爵士","古典","民谣","电子"])],"total":6}}

track={"id":"tr-0","title":"Mira mira mira ～ Album ver. ～","artist":"大黒摩季","album":"55 RED","coverid":"c0","duration":346}
audio={"codec":"FLAC","sampleRate":"44.1 kHz","bitDepth":"16 bit","bitrate":"911 kbps","format":"FLAC / 44.1kHz / 16bit"}
lyrics={"lines":[[0,"Mira mira mira"],[12,"〜 Album ver. 〜"],[26,"大黒摩季 · 55 RED"]]}
bio={"album":"55 RED 是 大黒摩季 的经典专辑。","artist":"大黒摩季，日本创作歌手。"}

def cov(text, seed):
    hue=(seed*37)%360
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="hsl({hue},45%,45%)"/><stop offset="1" stop-color="hsl({(hue+55)%360},40%,22%)"/></linearGradient></defs><rect width="120" height="120" fill="url(#g)"/><text x="60" y="65" font-size="13" fill="rgba(255,255,255,.85)" text-anchor="middle" font-family="sans-serif">{text[:6]}</text></svg>'''
    return "data:image/svg+xml;base64,"+base64.b64encode(svg.encode()).decode()

mock = """
window.__LIB__ = %s;
window.__TRACK__ = %s;
window.__COVER__ = %s;
window.__AUDIO__ = %s;
window.__LYRICS__ = %s;
window.__BIO__ = %s;
window.__SYNC__ = {players:[
  {id:'00:00:00:00:00:01',name:'客厅 · Sonora One',model:'squeezelite',playing:true,state:'play'},
  {id:'00:00:00:00:00:02',name:'书房 · 小唱机',model:'squeezelite',playing:false,state:'pause'},
  {id:'00:00:00:00:00:03',name:'卧室 · Bedside',model:'squeezelite',playing:false,state:'stop'},
  {id:'00:00:00:00:00:04',name:'厨房 · Kitchen',model:'squeezelite',playing:true,state:'play'},
  {id:'00:00:00:00:00:05',name:'露台 · Deck',model:'squeezelite',playing:false,state:'offline'}
],master:'',slaves:[]};
window.__PL__ = [
  {id:'99',name:'♥ 收藏',trackcount:2,isFav:true,locked:true}
];
window.__QUEUE_ITEMS__ = [
  {id:'t1',title:'Mira mira mira ～ Album ver. ～',artist:'大黒摩季',album:'55 RED'},
  {id:'t2',title:'浪潮',artist:'陈粒',album:'如也'},
  {id:'t3',title:'Yellow',artist:'Coldplay',album:'Parachutes'},
  {id:'t4',title:'玫瑰色的人生',artist:'李荣浩',album:'模特'},
  {id:'t5',title:'海边',artist:'张惠妹',album:'你在看我吗'}
];
window.__CFG__ = {theme:'dark', lms_host:'192.168.199.2', lms_port:'9000',
  host_name:'Song-Mac', device_short:'USBDAC', name_template:'{host} - {short}',
  device:'coreaudio_device', lms_user:'', np_playerid:''};
window.__DEVICES__ = {binary:'/opt/homebrew/bin/squeezelite', reasons:[], devices:[
  {id:'',name:'BuiltIn Output',raw:'BuiltIn',source:'squeezelite -l',is_default:true},
  {id:'',name:'USBDAC',raw:'USBDAC',source:'squeezelite -l',is_default:false},
  {id:'',name:'coreaudio_device',raw:'coreaudio_device',source:'system_profiler',is_default:false}
]};
window.__PARAMS__ = {binary:'/opt/homebrew/bin/squeezelite',
  preview:'squeezelite -a 100:0 -r 44100-384000 -b 8192:8192',
  problems:[], values:{'device_args':'100:0','rates':'44100-384000','buffer':'8192:8192'},
  params:[
    {key:'server',flag:'-s',name:'LMS 服务器',kind:'text',default:'',recommend:'',
     options:[['','自动发现（不传 -s）','通过 UDP 广播自动发现同网段 LMS']],
     effect:'决定播放器连接哪台 LMS。',detail:'格式 host[:port]。',range:'IP [ :端口 ]'},
    {key:'device_args',flag:'-a',name:'设备打开参数 (-a)',kind:'text',default:'',recommend:'100:0',
     options:[['','默认','交给驱动'],['100:0','★ Pro Mode 独占 + 100ms（最优音质）','绕过系统混音与 SRC，实现 bit-perfect'],['100:1','Play Nice 共享','系统会重采样，音质有损']],
     effect:'macOS 上最影响音质的参数。',detail:'Pro Mode 独占设备，DAC 收到源码流原始采样率。',range:'<延迟ms>:<0|1>'},
    {key:'rates',flag:'-r',name:'采样率 (-r)',kind:'text',default:'',recommend:'44100-384000',
     options:[['','不指定','自动探测'],['44100-384000','★ 44.1k~384k 全范围（最优音质）','避免服务端重采样'],['44100-192000','44.1k~192k','主流 USB DAC']],
     effect:'声明设备支持的采样率。',detail:'这是实现 bit-perfect 的关键参数。',range:'单值 / 范围 / 列表'},
    {key:'buffer',flag:'-b',name:'缓冲 (-b)',kind:'text',default:'',recommend:'8192:8192',
     options:[['','默认','系统决定'],['8192:8192','★ 大缓冲（最优音质）','抗网络抖动，不改音质']],
     effect:'设置输入输出缓冲大小。',detail:'大缓冲抗抖动。',range:'<stream>:<output> KB'}
  ]};
window.__LAUNCH__ = {binary:'/opt/homebrew/bin/squeezelite', command:'squeezelite -a 100:0 -r 44100-384000', version:'2.0.0', autoRun:true, problems:[]};
window.__FAV_IDS__ = ['t1','t3'];
window.__QUEUE__ = {items:window.__QUEUE_ITEMS__,index:0,mode:'0 0',ok:true};
window.__DRILL__ = {};
window.__UPDATES__ = {local:'v2.0.7', squeezelite:{arch:'m1',items:[],latest:{version:'v0.2.1'}}, lms:{}, errors:[]};
window.__CHANGELOG__ = {items:[],source:'preview'};
(function(){
  const base = {
    getMeta:()=>Promise.resolve({version:'1.6.0'}),
    getConfig:()=>Promise.resolve(window.__CFG__),
    getLibrary:()=>Promise.resolve(window.__LIB__),
    getAudio:()=>Promise.resolve(window.__AUDIO__),
    getLyrics:()=>Promise.resolve(window.__LYRICS__),
    getBio:()=>Promise.resolve(window.__BIO__),
    getStatus:()=>Promise.resolve({mode:'play',time:96,duration:346,volume:60,track:window.__TRACK__}),
    getSyncStatus:()=>Promise.resolve(window.__SYNC__),
    setTheme:()=>Promise.resolve({ok:true}),
    getPlaylists:()=>{ const f=window.__PL__.find(p=>p.isFav); if(f) f.trackcount=window.__FAV_IDS__.length; return Promise.resolve({items:window.__PL__.slice()}); },
    getFavorites:()=>Promise.resolve({ok:true,playlistId:'99',ids:window.__FAV_IDS__,items:[]}),
    toggleFavorite:(tid,force)=>{
      const has=window.__FAV_IDS__.includes(tid);
      const want = force===null||force===undefined ? !has : !!force;
      if(want&&!has) window.__FAV_IDS__.push(tid);
      if(!want&&has) window.__FAV_IDS__=window.__FAV_IDS__.filter(x=>x!==tid);
      return Promise.resolve({ok:true,favorited:want,trackId:tid});
    },
    getQueue:()=>Promise.resolve(window.__QUEUE__),
    playlistTracks:(pid)=>{
      if(String(pid)==='99'){
        const items=window.__QUEUE_ITEMS__.filter(t=>window.__FAV_IDS__.includes(t.id)).map(t=>({...t,_name:t.title}));
        return Promise.resolve({items:items});
      }
      return Promise.resolve({items:window.__QUEUE_ITEMS__.slice(0,3)});
    },
    libInfo:(it)=>Promise.resolve({lines:['标题：\t'+(it.title||it.album||it.artist||'—'),'艺术家：\t'+(it.artist||'未知'),'专辑：\t'+(it.album||'未知'),'流派：\t流行','年份：\t2020','格式：\tFLAC','采样率：\t44.1 kHz','位深：\t16 bit','码率：\t911 kbps'],text:'',source:'预览'}),
    libBrowse:(mode,start,count,filters)=>{
      // 下钻：返回几首模拟曲目
      const f=String((filters&&filters[0])||'');
      const name=(window.__LIB__[S_cat()]||{});
      const items=window.__QUEUE_ITEMS__.concat([
        {id:'t6',title:'晴天',artist:'周杰伦',album:'叶惠美'},
        {id:'t7',title:'海底',artist:'一支榴莲',album:'海底'}
      ]).map((t,i)=>({...t,id:'d'+i,coverid:'c'+i,_cover:null}));
      return Promise.resolve({items:items,total:items.length});
    },
    createPlaylist:(n)=>{
      if(n==='♥ 收藏') return Promise.resolve({ok:false,error:'该名称为系统保留'});
      if(window.__PL__.some(p=>p.name===n)) return Promise.resolve({ok:false,error:'列表名称已存在'});
      const id=String(Date.now());
      window.__PL__.push({id:id,name:n,trackcount:0});
      return Promise.resolve({ok:true,name:n,id:id});
    },
    deletePlaylist:(pid)=>{
      const p=window.__PL__.find(x=>String(x.id)===String(pid));
      if(p&&(p.isFav||p.locked)) return Promise.resolve({ok:false,error:'「♥ 收藏」为系统列表，不可删除'});
      window.__PL__=window.__PL__.filter(x=>String(x.id)!==String(pid));
      return Promise.resolve({ok:true});
    },
    playlistAdd:(pid,tid)=>{ const p=window.__PL__.find(x=>String(x.id)===String(pid)); if(p) p.trackcount=(p.trackcount||0)+1; return Promise.resolve({ok:true}); },
    playlistRemove:(pid,i)=>{ const p=window.__PL__.find(x=>String(x.id)===String(pid)); if(p) p.trackcount=Math.max(0,(p.trackcount||0)-1); return Promise.resolve({ok:true}); },
    queueAdd:()=>Promise.resolve({ok:true}),
    queueRemove:()=>Promise.resolve({ok:true}),
    queuePlayIndex:()=>Promise.resolve({ok:true}),
    setPlayMode:(sh,rp)=>Promise.resolve({ok:true}),
    getConnection:()=>Promise.resolve(window.__ENGINE_ON__?{connected:true,state:'online',label:'已连接',url:'http://192.168.199.2:9000',version:'9.1.1',playerCount:1}:{connected:true,state:'noplayer',label:'已连服务器·播放器未启动',url:'http://192.168.199.2:9000',version:'9.1.1',playerCount:0,error:'请在「播放器引擎」页启动引擎'}),
    engineStatus:()=>Promise.resolve({ok:true,running:!!window.__ENGINE_ON__,pid:window.__ENGINE_ON__?12345:0,uptime:window.__ENGINE_ON__?42:0,command:window.__LAUNCH__&&window.__LAUNCH__.command||'squeezelite',exitCode:null,logs:window.__ENGINE_LOGS__||['暂无日志'],binary:window.__LAUNCH__&&window.__LAUNCH__.binary||''}),
    startEngine:()=>{ window.__ENGINE_ON__=true; window.__ENGINE_LOGS__=['$ squeezelite -n Sonora -o default','[12:00:01] 正在连接 LMS 192.168.199.2:9000...','[12:00:02] 已注册播放器，playerid=aa:bb:cc:dd:ee:ff','[12:00:03] 引擎运行中']; return Promise.resolve({ok:true,pid:12345,message:'squeezelite 已启动 (PID 12345)，正在注册到 LMS…'}); },
    stopEngine:()=>{ window.__ENGINE_ON__=false; window.__ENGINE_LOGS__=['[已停止引擎]']; return Promise.resolve({ok:true,message:'squeezelite 已停止'}); },
    scanDevices:()=>Promise.resolve(window.__DEVICES__),
    saveDevice:(dev,host,short)=>{ window.__CFG__.device=dev; window.__CFG__.host_name=host; window.__CFG__.device_short=short; return Promise.resolve({ok:true,playerName:(host||'Mac')+' - '+(short||'')}); },
    getParams:()=>Promise.resolve(window.__PARAMS__),
    applyBestParams:()=>{ window.__PARAMS__.values={'device_args':'100:0','rates':'44100-384000','buffer':'8192:8192'}; return Promise.resolve({ok:true,applied:window.__PARAMS__.values,preview:window.__PARAMS__.preview}); },
    toggleMute:()=>{ window.__MUTED__=!window.__MUTED__; return Promise.resolve({ok:true,muted:window.__MUTED__,volume:window.__MUTED__?0:60}); },
    setAutoStart:(on)=>{ window.__AUTOSTART__=!!on; return Promise.resolve({ok:true,autoStart:!!on,message:on?'已设置开机自启（已立即生效）':'已关闭开机自启'}); },
    getAutoStartStatus:()=>Promise.resolve({ok:true,enabled:!!window.__AUTOSTART__,installed:!!window.__AUTOSTART__,loaded:!!window.__AUTOSTART__,plist:'~/Library/LaunchAgents/com.squeezelite.gui.plist',isMac:true}),
    upgradeSqueezelite:()=>{ return Promise.resolve({ok:true,version:'2.0.0.1465',message:'已升级为 2.0.0.1465',logs:['→ 查询最新版本...','✓ 命中源 SourceForge','已下载 squeezelite-2.0.0.1465-osx-m1.tar.gz (8.42 MB)','已备份旧版 → ~/.squeezelite_gui/backups/squeezelite.20261122-224500.bak','已升级为 2.0.0.1465','升级后已自动重启引擎']}); },
    getLaunchInfo:()=>Promise.resolve(window.__LAUNCH__),
    setVolume:(v)=>Promise.resolve({ok:true}),
    getCover:()=>Promise.resolve(window.__COVER__)
  };
  function S_cat(){return 'albums';}
  // getStatus 返回动态时间，驱动进度条
  base.getStatus=()=>Promise.resolve({mode:'play',time:96+(Math.floor(Date.now()/1000)%%40),duration:346,volume:60,playlist_mode:'0 0',track:window.__TRACK__});
  
  window.pywebview = {api:new Proxy(base,{get:(t,k)=> k in t ? t[k] : (()=>Promise.resolve({ok:true}))})};
})();
""" % (json.dumps(lib,ensure_ascii=False), json.dumps(track,ensure_ascii=False),
       json.dumps(cov("Mira",0),ensure_ascii=False), json.dumps(audio,ensure_ascii=False),
       json.dumps(lyrics,ensure_ascii=False), json.dumps(bio,ensure_ascii=False))

html = html.replace('<link rel="stylesheet" href="tokens.css">\n<link rel="stylesheet" href="app.css">\n<link rel="stylesheet" href="refine.css">\n<link rel="stylesheet" href="refine2.css">\n<link rel="stylesheet" href="refine3.css">\n<link rel="stylesheet" href="refine4.css">', '<style>\n'+css+'\n</style>')
html = html.replace('src="assets/logo-mark.svg"', 'src="'+logo_uri+'"')
html = html.replace('<script src="app.js"></script>', '<script>\n'+mock+'\n</script>\n<script>\n'+js+'\n</script>')
out = ROOT / "preview.html"
out.write_text(html)
print("preview built:", len(html), "bytes ->", out)
