/* Sonora 颂诺 Web v0.2 — 交互逻辑 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  let api = (window.pywebview && window.pywebview.api) || window.api || {};
  const S = {
    cat: "albums", view: "grid", sortAsc: true, query: "",
    library: null, items: [], anchors: {},
    playerOpen: false, focus: false,
    fpanel: "", panels: { playlist:true, lyrics:true, albumBio:false, artistBio:false },
    track: null, time: 96, duration: 346, playing: true,
    crumbs: [],            // 下钻面包屑栈 [{label, cat, filters}]
    browseItems: null,     // 下钻结果（非空时替代 S.items 渲染）
    ctxItem: null,         // 右键目标条目
    playMode: "seq",       // seq | loop | one | shuffle
    volume: 60,
    plSource: "",          // 播放列表面板当前来源：""=当前队列 或播放列表ID
    playlists: [],
    queue: [],
    favorites: [],       // 已收藏曲目 id 列表
    lpdPid: "",          // 音乐库抽屉当前查看的列表 id（""=当前队列）
    miniFolded: false,   // mini 播放器是否溃缩为小图标
    modePendingUntil: 0, // 播放模式乐观锁：此时间前轮询不回写，避免点击后弹回
    trackExtras: {},     // 曲目附属信息缓存（封面/音频/歌词/简介）by track id
  };
  const COLLATE = "a-zA-Z0-9";
  function fmt(sec){ sec=Math.max(0,Number(sec)||0); const m=Math.floor(sec/60),s=Math.floor(sec%60);
    return m+":"+String(s).padStart(2,"0"); }
  function esc(s){ return String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  // 歌词行兼容两种格式：[秒, 文本]（parse_lrc 元组）与 {time, text}
  function lyricTime(ln){ return Array.isArray(ln)?Number(ln[0]):Number(ln.time)||0; }
  function lyricText(ln){ return Array.isArray(ln)?ln[1]:ln.text; }
  function toast(msg){ const t=$("toast"); t.textContent=msg; t.classList.add("show");
    clearTimeout(toast._t); toast._t=setTimeout(()=>t.classList.remove("show"),2400); }

  /* ---------- 主题 ---------- */
  function applyTheme(name){
    let real=name;
    if(name==="system") real=(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light";
    document.documentElement.setAttribute("data-theme",real);
    document.querySelectorAll("#themeSeg button").forEach(b=>b.classList.toggle("on",b.dataset.theme===name));
  }
  $("themeSeg").addEventListener("click",async e=>{
    const b=e.target.closest("button"); if(!b)return;
    applyTheme(b.dataset.theme); try{ await api.setTheme(b.dataset.theme);}catch(e){}
  });

  /* ---------- 设置下拉 ---------- */
  const menu=$("settingsMenu");
  $("settingsBtn").addEventListener("click",e=>{
    e.stopPropagation(); const show=menu.hidden; menu.hidden=!show;
    $("settingsBtn").classList.toggle("on",show);
  });
  document.addEventListener("click",e=>{ if(!menu.hidden && !menu.contains(e.target)){
    menu.hidden=true; $("settingsBtn").classList.remove("on"); }});
  menu.addEventListener("click",e=>{
    const b=e.target.closest("button[data-nav]"); if(!b)return;
    menu.hidden=true; $("settingsBtn").classList.remove("on");
    goto(b.dataset.nav);
  });

  /* ---------- 页面导航 ---------- */
  const HOME_PAGES=["home"];
  function goto(page){
    document.querySelectorAll(".page").forEach(p=>p.classList.remove("on"));
    const el=$("page-"+page); if(el) el.classList.add("on");
    $("backBar").hidden = (page==="home");
    if(page==="lib"){ renderLibrary(); }
    if(page==="server") loadServerPage();
    if(page==="launch") loadLaunchPage();
    if(page==="params") loadParamsPage();
    if(page==="update") loadUpdatePage();
    const main=$("main"); if(main) main.scrollTop=0;
    window.scrollTo(0,0);
  }
  $("backBar").addEventListener("click",()=>goto("home"));
  document.querySelector(".brand").addEventListener("click",()=>goto("home"));
  document.querySelectorAll(".home-card").forEach(c=>c.addEventListener("click",()=>goto(c.dataset.nav)));
  $("addLibBtn").addEventListener("click",()=>goto("server"));
  $("gotoServerBtn").addEventListener("click",()=>goto("server"));

  /* ---------- 音乐库 ---------- */
  $("libCats").addEventListener("click",e=>{
    const b=e.target.closest("button"); if(!b)return;
    // 切换分类先清空下钻状态，否则 filtered() 仍返回上次下钻结果导致内容错乱
    S.crumbs=[]; S.browseItems=null; S.lastBrowse=null;
    S.cat=b.dataset.cat; S.query=""; $("libSearch").value="";
    document.querySelectorAll("#libCats button").forEach(x=>x.classList.toggle("on",x===b));
    renderLibrary();
  });
  $("viewBtn").addEventListener("click",()=>{
    S.view = S.view==="grid" ? "list" : "grid";
    $("viewBtn").textContent = S.view==="grid" ? "▦" : "☰";
    renderLibrary();
  });
  $("sortBtn").addEventListener("click",()=>{
    S.sortAsc=!S.sortAsc; $("sortBtn").textContent=S.sortAsc?"A↓Z":"Z↓A"; renderLibrary();
  });
  $("libSearch").addEventListener("input",e=>{ S.query=e.target.value.trim().toLowerCase(); renderLibrary(); });

  function itemName(it,cat){
    return it.album || it.artist || it.title || it.genre || it._name || it.id || "";
  }
  function firstLetter(name){
    const s=(name||"").trim(); if(!s)return "#";
    const c=s[0].toUpperCase();
    return /[A-Z]/.test(c)?c : /[0-9]/.test(c)?"#":"#";
  }
  function filtered(){
    if(!S.library) return [];
    let arr=(S.library[S.cat]||{}).items||[];
    if(S.query) arr=arr.filter(it=>itemName(it,S.cat).toLowerCase().includes(S.query)
      || (it.artist||"").toLowerCase().includes(S.query)
      || (it.album||"").toLowerCase().includes(S.query));
    arr=arr.slice().sort((a,b)=>{
      const na=itemName(a,S.cat), nb=itemName(b,S.cat);
      const c=na.localeCompare(nb,"zh-CN",{numeric:true});
      return S.sortAsc?c:-c;
    });
    return arr;
  }
  function thumbHtml(it,idx){
    const cov=it._cover;
    const cid=it.artwork_track_id||it.coverid||"";
    const inner=cov?`<img src="${cov}" alt="">`
      : cid?`<img class="lazy-cover" data-cid="${esc(cid)}" src="" alt="" style="opacity:0">`:`<span class="ph">♪</span>`;
    const idxHtml = S.view==="grid"?`<span class="idx">${String(idx).padStart(2,"0")}</span>`:"";
    return `<div class="thumb">${inner}${idxHtml}</div>`;
  }
  // 异步补齐音乐库里没有 _cover 但有 coverid 的缩略图
  async function fillLazyCovers(){
    const els=Array.from(document.querySelectorAll("#libItems img.lazy-cover")).slice(0,120);
    if(!els.length || !api.getCover) return;
    for(const el of els){
      const cid=el.dataset.cid; if(!cid) continue;
      try{
        const data=await api.getCover({coverid:cid},96);
        if(data){ el.src=data; el.style.opacity="1"; el.classList.remove("lazy-cover"); }
        else { el.outerHTML=`<span class="ph">♪</span>`; }
      }catch(e){ el.outerHTML=`<span class="ph">♪</span>`; }
    }
  }
  function renderLibrary(){
    const wrap=$("libWrap"), setup=$("libSetup");
    const hasCfg = !!(S.library && (S.library.albums||{}).items && S.library.albums.items.length);
    // 预览数据总是有；真实环境可据此显示未配置引导
    setup.hidden = true; wrap.hidden = !hasCfg;
    if(!hasCfg) return;
    S.items=filtered();
    $("libCount").textContent = `${S.cat==="titles"?"曲目":S.cat==="albums"?"专辑":S.cat==="artists"?"艺术家":"流派"} ${S.items.length} 项`;
    $("libHint").textContent = S.query?`搜索“${S.query}”`:(S.sortAsc?"按名称 A→Z":"按名称 Z→A");
    const grid=$("libItems"); grid.className="lib-items "+S.view;
    // 下钻展示的是曲目，必须用 titles 语义取名，否则每首都显示专辑名
    const dispCat = S.browseItems ? "titles" : S.cat;
    grid.innerHTML = S.items.map((it,i)=>{
      const name=dispCat==="titles" ? (it.title||it._name||it.album||it.id||"") : itemName(it,S.cat);
      let sub="",extra="";
      if(dispCat==="titles"){ sub=it.artist||""; extra=fmt(it.duration); }
      else if(dispCat==="albums") sub=it.artist||"";
      else if(dispCat==="artists") sub="艺术家";
      else sub="流派";
      const mainCls = S.view==="list"?"it-main":"";
      const titleBlock = `<div class="it-title" title="${esc(name)}">${esc(name)}</div>`+
        (S.view==="list"?`<div class="it-sub">${esc(sub)}</div>`:"");
      const subBlock = S.view==="grid"?`<div class="it-sub">${esc(sub)}</div>`:"";
      const isTrack = dispCat==="titles";
      const favBtn = isTrack ? `<button class="fav-mini ${isFav(it)?"on":""}" data-fav="${esc(it.id)}" title="收藏">${isFav(it)?"♥":"♡"}</button>` : "";
      return `<div class="lib-item ${S.view}" data-id="${esc(it.id)}">
        ${thumbHtml(it,i)}${favBtn}
        <div class="${mainCls}">${titleBlock}${subBlock}</div>
        ${extra?`<div class="it-extra">${extra}</div>`:""}
      </div>`;
    }).join("");
    grid.querySelectorAll(".lib-item").forEach(el=>{
      el.addEventListener("click",()=>{
        const it=S.items.find(x=>String(x.id)===el.dataset.id);
        if(!it) return;
        if(dispCat==="titles") playItem(it);
        else drillInto(it);
      });
      el.addEventListener("contextmenu",e=>{ e.preventDefault();
        const it=S.items.find(x=>String(x.id)===el.dataset.id);
        if(it) openCtxMenu(e, it);
      });
      const fb=el.querySelector(".fav-mini");
      if(fb) fb.addEventListener("click",async e=>{
        e.stopPropagation();
        const it=S.items.find(x=>String(x.id)===el.dataset.id);
        if(it) await toggleFav(it);
      });
    });
    buildAlpha();
    if(typeof crumbRender==="function") crumbRender();
    if(S.browseItems && $("libHint")) $("libHint").textContent="已展开曲目 · "+S.items.length+" 首";
    fillLazyCovers();
  }
  function setAlphaActive(L){
    const bar=$("alphaBar"); if(!bar)return;
    bar.querySelectorAll("button").forEach(b=>b.classList.toggle("on",b.dataset.l===L));
  }
  // 按「各字母首项」与当前滚动位置的距离判定高亮，避免网格一行跨字母时误判。
  function letterAtTop(){
    const body=$("libBody"), grid=$("libItems");
    if(!body||!grid||!grid.children.length||!S.items.length)return "";
    const st=body.scrollTop;
    let best="", bestD=Infinity;
    for(const L of Object.keys(S.anchors||{})){
      const idx=S.anchors[L], el=grid.children[idx];
      if(!el) continue;
      const d=Math.abs(el.offsetTop-st);
      if(d<bestD){ bestD=d; best=L; }
    }
    return best || firstLetter(itemName(S.items[0],S.cat)) || "#";
  }
  function syncAlphaOnScroll(){ const L=letterAtTop(); if(L) setAlphaActive(L); }
  function buildAlpha(){
    const letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").concat(["#"]);
    const groups={}; S.anchors={};
    S.items.forEach((it,i)=>{ const L=firstLetter(itemName(it,S.cat));
      (groups[L]=groups[L]||[]).push(it);
      if(S.anchors[L]==null) S.anchors[L]=i;
    });
    const bar=$("alphaBar");
    bar.innerHTML=letters.map(L=>`<button data-l="${L}" class="${groups[L]?"":"disabled"}">${L}</button>`).join("");
    bar.querySelectorAll("button:not(.disabled)").forEach(b=>{
      b.addEventListener("click",()=>{
        const L=b.dataset.l, body=$("libBody");
        const idx=S.items.findIndex(it=>firstLetter(itemName(it,S.cat))===L);
        if(idx>=0){
          const el=$("libItems").children[idx];
          if(el&&body) body.scrollTop=Math.max(0,el.offsetTop-2); // 滚到该字母首项，行顶对齐
          else if(el) el.scrollIntoView({block:"start"});
        }
        // 点击即硬高亮所点字母，并用时间窗锁定 550ms 覆盖滚动动画期；
        // 网格视图一行跨多字母，顶行字母≠所点字母，故不能用 letterAtTop 覆盖。
        setAlphaActive(L);
        S.alphaPinned=L;
        S.alphaTargetTop=(body?body.scrollTop:0);
        S.alphaPinUntil=Date.now()+550;
        const tip=$("alphaTip"); tip.textContent=L; tip.classList.add("show");
        clearTimeout(tip._t); tip._t=setTimeout(()=>tip.classList.remove("show"),600);
      });
    });
    const body=$("libBody");
    if(body && !body._alphaBound){
      body._alphaBound=true;
      body.addEventListener("scroll",()=>{
        if(Date.now()<(S.alphaPinUntil||0))return; // 点击跳转动画期内不联动
        // 点击跳转产生的那一次 scroll 事件不算用户滚动，否则高亮会被网格顶行字母抢走
        if(S.alphaPinned && Math.abs(body.scrollTop-(S.alphaTargetTop||0))<2)return;
        S.alphaPinned=null;
        if(S.alphaScrollT)return;
        S.alphaScrollT=setTimeout(()=>{ S.alphaScrollT=null; syncAlphaOnScroll(); },40);
      },{passive:true});
    }
    setAlphaActive(letterAtTop() || firstLetter(itemName(S.items[0],S.cat)) || "A");
  }

  /* ---------- 曲目 / 播放器数据 ---------- */
  function trackFromItem(it){
    if(it.title!==undefined || it._kind==="titles"){
      return { id:it.id||it.track_id, title:it.title||it._name, artist:it.artist||"",
        album:it.album||"", coverid:it.coverid||it.artwork_track_id||"",
        duration:Number(it.duration)||0 };
    }
    return { id:it.id||it.track_id, title:it.album||it.artist||it.genre||it._name||"未知",
      artist:it.artist||"", album:it.album||"",
      coverid:it.artwork_track_id||it.coverid||"", duration:Number(it.duration)||346 };
  }
  async function playItem(it){
    S.track=trackFromItem(it);
    // 保留完整字段供音频/歌词解析
    for(const k of ("url","type","samplerate","samplesize","bitrate","filesize")){
      if(it[k]!==undefined) S.track[k]=it[k];
    }
    // 列表缩略图仅用于列表显示；主封面交给 getCover 抓高清大图，
    // 否则 96px 缩略图被拉伸到 440px 会明显发虚。
    S.cover = null; S.coverTrackId = "";
    S.time=0; S.duration=S.track.duration||346; S.playing=true;
    applyTrackToAll();
    refreshPlaylistPanel();     // 切歌后只刷新一次，避免双重写 DOM 跳闪
    setMiniFolded(false);
    loadTrackExtras(S.track);
    // 真实下发：以 titles 模式按 track_id 载入并播放
    try{
      const mode = (it._kind==="titles" || it.title!==undefined) ? "titles" : (S.cat||"titles");
      const r = await apiCall("libPlay", {ok:true}, mode, String(it.id||it.track_id||""));
      if(r && r.ok===false) toast("播放下发失败："+(r.error||"播放器不在线"));
      else toast(`正在播放：${S.track.title}`);
    }catch(e){ toast(`正在播放：${S.track.title}`); }
  }
  // 切歌时刷新附属信息（音频规格 / 歌词 / 简介），按 id 缓存，避免轮询重复请求
  async function loadTrackExtras(track){
    if(!track) return;
    const id=String(track.id||track.track_id||"");
    if(!id) return;
    const seq=(S._extrasSeq=(S._extrasSeq||0)+1); // 请求序号：只接受最后一次切歌的结果
    const isCurrent=()=>seq===S._extrasSeq && String(S.track&&S.track.id||"")===id;
    const cache=(S.trackExtras[id]=S.trackExtras[id]||{});
    if(!isCurrent())return;
    const RAF=window.requestAnimationFrame||((f)=>setTimeout(f,16));
    let raf=0;
    const flush=()=>{ if(raf)return; raf=RAF(()=>{ raf=0; applyTrackToAll(); }); };
    const put=(key,val)=>{
      if(!val||!isCurrent())return;
      cache[key]=val;
      if(key==="cover"){ S.cover=val; S.coverTrackId=id; }
      else S[key]=val;
      flush(); // 单项到位即刷新，不等最慢的封面/简介（修复歌词/信息延后）
    };
    // 命中缓存的立刻显示；未缓存的清空旧数据，避免上一首歌词滞留
    S.audio=cache.audio||null; S.lyrics=cache.lyrics||null; S.bio=cache.bio||null;
    if(cache.cover){ S.cover=cache.cover; S.coverTrackId=id; }
    else { S.cover=null; S.coverTrackId=""; }
    applyTrackToAll();
    const jobs=[
      ["audio", api.getAudio && api.getAudio(track)],
      ["lyrics",api.getLyrics && api.getLyrics(track)],
      ["bio",   api.getBio && api.getBio(track.artist||"",track.album||"")],
      ["cover", api.getCover && api.getCover(track,800)],   // 高清大图
    ];
    jobs.forEach(([key,p])=>{
      if(!p||cache[key])return;
      Promise.resolve(p).catch(()=>null).then(v=>put(key,v));
    });
  }
  function coverOf(track){
    const id=String(track&&(track.id||track.track_id)||"");
    // 全局封面必须属于当前曲目才使用，防止切歌竞态串封面
    if(S.cover && String(S.coverTrackId||"")===id) return S.cover;
    const c=S.trackExtras&&S.trackExtras[id];
    if(c&&c.cover) return c.cover;
    if(S.library && S.library.titles){
      const t=S.library.titles.items.find(x=>String(x.id)===id);
      if(t&&t._cover) return t._cover;
    }
    return null;
  }
  function setHTML(el,html){ if(el && el.innerHTML!==html) el.innerHTML=html; }
  function coverHtml(el,track){
    const cov=coverOf(track);
    setHTML(el, cov?`<img src="${cov}" alt="cover">`:`<span class="ph">♪</span>`);
    return cov?cov:"";
  }

  function applyTrackToAll(){
    const t=S.track||{}; const title=t.title||"—", artist=t.artist||"", album=t.album||"";
    // mini
    $("miniTitle").textContent=title; $("miniArtist").textContent=artist+(album?" · "+album:"");
    coverHtml($("miniCover"),t);
    // player
    $("playerTitle").textContent=title; $("playerArtist").textContent=artist; $("playerAlbum").textContent=album;
    const bg=coverHtml($("playerCover"),t); if(bg) $("playerBg").style.backgroundImage=`url("${bg}")`;
    // focus
    $("focusTitle").textContent=title; $("focusArtist").textContent=artist?("By "+artist):"";
    $("focusAlbum").textContent=album?("From "+album):"";
    const bg2=coverHtml($("focusCover"),t); if(bg2) $("focusBg").style.backgroundImage=`url("${bg2}")`;
    // LED
    const sp=(S.audio&&S.audio.spec)||{};
    $("ledFmt").textContent=sp.format||"—"; $("ledRate").textContent=sp.rate||"—";
    $("ledBits").textContent=sp.bits||"—"; $("ledBitrate").textContent=sp.bitrate||"—";
    const v=(S.audio&&S.audio.verdict)||{};
    $("ledStatus").textContent=v.title||v.short||"NO SIGNAL";
    $("ledStatus").title=v.detail||v.title||"";
    $("ledStatus").classList.toggle("ok",v.level==="ok");
    $("ledStatus").classList.toggle("warn",v.level==="warn");
    // lyrics
    const lines=(S.lyrics&&S.lyrics.lines)||[];
    setHTML($("lyricsBox"), lines.length? lines.map((ln,i)=>`<div class="lyric-line" data-i="${i}">${esc(lyricText(ln))}</div>`).join("") : "暂无歌词");
    setHTML($("focusLyrics"), lines.length? lines.map((ln,i)=>`<div class="flyric" data-i="${i}">${esc(lyricText(ln))}</div>`).join("") : "");
    // bio
    const bio=S.bio||{};
    setHTML($("albumBioBox"), bio.album? `<span class="src-badge">${esc(bio.source||"")}</span><br>${esc(bio.album)}`:"暂无专辑简介");
    setHTML($("artistBioBox"), bio.artist? `<span class="src-badge">${esc(bio.source||"")}</span><br>${esc(bio.artist)}`:"暂无歌手简介");
    updateTimeUI();
  }
  function refreshPlaylistPanel(){
    if(S.plSource) renderPlTracks(S.plSource); else loadQueue();
  }
  function buildPlaylist(){
    const items=(S.library&&S.library.titles&&S.library.titles.items)||[];
    const html=items.slice(0,60).map((it,i)=>{
      const cur=String(it.id)===String(S.track&&S.track.id);
      const th=it._cover?`<img class="fa-thumb" src="${it._cover}" alt="">`:`<div class="fa-thumb"></div>`;
      return `<div class="pl-row ${cur?"cur":""}" data-id="${esc(it.id)}">
        ${th}<span class="pl-n">${cur?'<b class="now-playing">▶</b>':String(i+1).padStart(2,"0")}</span>
        <span class="pl-t">${esc(it.title||it._name)}</span></div>`;
    }).join("");
    $("playlistBox").innerHTML=html||"暂无播放列表";
    $("playlistBox").querySelectorAll(".pl-row").forEach(el=>el.addEventListener("click",()=>{
      const it=items.find(x=>String(x.id)===el.dataset.id); if(it) playItem(it);
    }));
  }
  function updateTimeUI(){
    const pct=S.duration>0?Math.min(100,S.time/S.duration*100):0;
    $("miniFill").style.width=pct+"%"; $("playerFill").style.width=pct+"%"; $("focusFill").style.width=pct+"%";
    $("miniTime").textContent=fmt(S.time)+" / "+fmt(S.duration);
    $("playerCur").textContent=fmt(S.time); $("playerDur").textContent=fmt(S.duration);
    $("focusCur").textContent=fmt(S.time); $("focusDur").textContent=fmt(S.duration);
    const symbol=S.playing?"❚❚":"▶";
    $("miniPlay").textContent=symbol; $("pPlay").textContent=symbol; $("fPlay").textContent=symbol;
    // 歌词高亮
    const lines=(S.lyrics&&S.lyrics.lines)||[];
    let idx=-1; for(let i=0;i<lines.length;i++){ if(lyricTime(lines[i])<=S.time) idx=i; else break; }
    document.querySelectorAll(".lyric-line,.flyric").forEach(el=>el.classList.toggle("cur",Number(el.dataset.i)===idx));
    const cur=document.querySelector(".focus-lyrics .flyric.cur");
    if(cur&&S.focus) cur.scrollIntoView({block:"center",behavior:"smooth"});
  }

  /* ---------- mini 播放器 ---------- */
  // ---- 进度条拖拽/点击 seek（mini / 播放器 / 专注）----
  function bindSeekBar(barEl, fillId){
    if(!barEl) return;
    let dragging=false;
    const seekFromEvent=(ev)=>{
      if(!(S.duration>0)) return;
      const r=barEl.getBoundingClientRect();
      let x=(ev.clientX!=null)?ev.clientX:(ev.touches&&ev.touches[0]&&ev.touches[0].clientX);
      if(x==null) return;
      let ratio=(x-r.left)/r.width;
      ratio=Math.max(0,Math.min(1,ratio));
      const sec=Math.round(ratio*S.duration);
      // 立即更新视觉与本地时间，给出即时反馈
      S.time=sec; updateTimeUI();
      // 抑制轮询覆盖：LMS seek 生效有延迟，1.5s 内不让 pollStatus 用旧 time 弹回
      S.seekingUntil = Date.now() + 1500;
      try{ if(api.setSeek) api.setSeek(sec).catch(function(){}); }catch(e){}
    };
    barEl.style.cursor="pointer";
    barEl.addEventListener("pointerdown",ev=>{ dragging=true; seekFromEvent(ev);
      try{ barEl.setPointerCapture(ev.pointerId); }catch(e){} });
    barEl.addEventListener("pointermove",ev=>{ if(dragging) seekFromEvent(ev); });
    barEl.addEventListener("pointerup",ev=>{ dragging=false;
      try{ barEl.releasePointerCapture(ev.pointerId); }catch(e){} });
    barEl.addEventListener("pointercancel",()=>{ dragging=false; });
  }
  function initSeekBars(){
    const miniFill=$("miniFill"), playerFill=$("playerFill"), focusFill=$("focusFill");
    // 给 fill 包一层可点击热区（fill 本身宽度随进度变化，点击空白无法触发，故绑在父容器）
    if(miniFill && miniFill.parentElement) bindSeekBar(miniFill.parentElement,"miniFill");
    if(playerFill && playerFill.parentElement) bindSeekBar(playerFill.parentElement,"playerFill");
    if(focusFill && focusFill.parentElement) bindSeekBar(focusFill.parentElement,"focusFill");
  }

  function setMiniFolded(folded){
    S.miniFolded=!!folded;
    const el=$("miniPlayer"); if(!el)return;
    el.hidden=false;
    el.classList.toggle("folded",S.miniFolded);
    if(el.dataset) el.dataset.folded=S.miniFolded?"1":"0";
  }
  $("miniCover").addEventListener("click",()=>{
    if(S.miniFolded){ setMiniFolded(false); toast("已展开迷你播放器"); }
    else openPlayer();
  });
  if($("miniClose")) $("miniClose").addEventListener("click",e=>{
    e.stopPropagation(); setMiniFolded(true);
    toast("已收起为小图标 · 点击封面恢复");
  });
  async function doMute(){
    const r=await apiCall("toggleMute",{ok:true,muted:false,volume:S.volume});
    if(r&&r.ok===false){ toast("静音操作失败"); return; }
    if(r&&typeof r.volume==="number"){
      S.volume=r.volume;
      document.querySelectorAll('#volSlider,#pVolSlider').forEach(x=>x.value=r.volume);
    }
    document.querySelectorAll('#miniMute,#pMute').forEach(b=>b.classList.toggle("muted", !!(r&&r.muted)));
    toast(r&&r.muted?"已静音":"已恢复音量");
  }
  if($("miniMute")) $("miniMute").addEventListener("click",e=>{e.stopPropagation();doMute();});
  if($("pMute")) $("pMute").addEventListener("click",e=>{e.stopPropagation();doMute();});
  async function doPlayControl(cmd){
    const r=await apiCall("playControl",{ok:true},cmd);
    if(r&&r.ok===false){ toast("控制失败："+(r.error||"播放器不在线")); return; }
    if(cmd==="play")S.playing=true; else if(cmd==="pause")S.playing=false;
    updateTimeUI();
  }
  ["miniPrev","pPrev","fPrev"].forEach(id=>$(id).addEventListener("click",()=>doPlayControl("prev")));
  ["miniNext","pNext","fNext"].forEach(id=>$(id).addEventListener("click",()=>doPlayControl("next")));
  ["miniPlay","pPlay","fPlay"].forEach(id=>$(id).addEventListener("click",()=>doPlayControl(S.playing?"pause":"play")));
  $("collapsePlayer").addEventListener("click",()=>{ $("playerScreen").hidden=true; S.playerOpen=false; });
  function openPlayer(){ $("playerScreen").hidden=false; S.playerOpen=true; }
  $("focusBtn").addEventListener("click",openFocus);
  $("focusExit").addEventListener("click",closeFocus);
  function openFocus(){
    S.focus=true; $("focusScreen").hidden=false;
    $("focusLyrics").hidden=false;                 // 歌词默认常驻中间大屏
    $("focusAside").hidden=true; S.fpanel="";
    document.querySelectorAll("#focusToggles button").forEach(b=>b.classList.toggle("on",b.dataset.fpanel==="lyricsOn"));
    updateTimeUI();
  }
  function closeFocus(){ S.focus=false; $("focusScreen").hidden=true; }

  /* ---------- 常规播放器面板开关 ---------- */
  $("panelToggles").addEventListener("click",e=>{
    const b=e.target.closest("button[data-panel]"); if(!b)return;
    const k=b.dataset.panel; S.panels[k]=!S.panels[k];
    b.classList.toggle("on",S.panels[k]);
    const panel=document.querySelector(`.ppanel[data-panel="${k}"]`); if(panel) panel.hidden=!S.panels[k];
  });
  document.querySelectorAll(".ppanel-x").forEach(x=>x.addEventListener("click",()=>{
    const k=x.dataset.close; S.panels[k]=false;
    const btn=document.querySelector(`#panelToggles button[data-panel="${k}"]`); if(btn)btn.classList.remove("on");
    const panel=document.querySelector(`.ppanel[data-panel="${k}"]`); if(panel)panel.hidden=true;
  }));

  /* ---------- 专注模式面板开关 ---------- */
  function showFPanel(k){
    if(k==="lyricsOn"){                            // 歌词显隐开关（中间区）
      const show=$("focusLyrics").hidden;
      $("focusLyrics").hidden=!show;
      const btn=document.querySelector('#focusToggles button[data-fpanel="lyricsOn"]');
      if(btn) btn.classList.toggle("on",show);
      return;
    }
    S.fpanel = (S.fpanel===k)?"":k;
    $("focusAside").hidden = !S.fpanel;
    document.querySelectorAll("#focusToggles button:not([data-fpanel='lyricsOn'])")
      .forEach(b=>b.classList.toggle("on",b.dataset.fpanel===S.fpanel));
    if(!S.fpanel) return;
    const titleMap={playlist:"播放列表",info:"曲目信息",artistBio:"歌手简介"};
    $("faTitle").textContent=titleMap[k]||"";
    const body=$("faBody");
    const t=S.track||{};
    if(k==="playlist"){
      const items=(S.library&&S.library.titles&&S.library.titles.items)||[];
      body.innerHTML=items.slice(0,80).map((it,i)=>{
        const cur=String(it.id)===String(t.id);
        const th=it._cover?`<img class="fa-thumb" src="${it._cover}" alt="">`:`<div class="fa-thumb"></div>`;
        return `<div class="fa-row ${cur?"cur":""}" data-id="${esc(it.id)}"><span class="fa-n">${cur?'<b class="now-playing">▶</b>':String(i+1).padStart(2,"0")}</span>${th}<div class="fa-tx"><div class="fa-t">${esc(it.title||it._name)}</div><div class="fa-a">${esc(it.artist||"")}</div></div></div>`;
      }).join("");
      body.querySelectorAll(".fa-row").forEach(el=>el.addEventListener("click",()=>{
        const it=items.find(x=>String(x.id)===el.dataset.id); if(it) playItem(it);
      }));
    } else if(k==="info"){
      const sp=(S.audio&&S.audio.spec)||{};
      const vd=(S.audio&&S.audio.verdict)||{};
      const rows=[["标题",t.title],["歌手",t.artist],["专辑",t.album],["格式",sp.format],["采样率",sp.rate],["位深",sp.bits],["码率",sp.bitrate]];
      if(vd.title) rows.push(["音频链路",vd.title]);
      if(vd.detail) rows.push(["判定依据",vd.detail]);
      body.innerHTML=rows.filter(r=>r[1]).map(r=>`<div class="fa-info-row"><span>${r[0]}</span><b>${esc(r[1])}</b></div>`).join("");
    } else if(k==="artistBio"){
      body.innerHTML=`<div class="fa-bio">${esc((S.bio&&S.bio.artist)||"暂无歌手简介")}</div>`;
    }
  }
  $("focusToggles").addEventListener("click",e=>{
    const b=e.target.closest("button[data-fpanel]"); if(!b)return; showFPanel(b.dataset.fpanel);
  });
  $("faClose").addEventListener("click",()=>{
    S.fpanel=""; $("focusAside").hidden=true;
    document.querySelectorAll("#focusToggles button:not([data-fpanel='lyricsOn'])").forEach(b=>b.classList.remove("on"));
  });
  document.addEventListener("keydown",e=>{ if(e.key==="Escape"){ if(S.focus)closeFocus(); else if(S.playerOpen){$("playerScreen").hidden=true;S.playerOpen=false;} }});

  /* ================= 阶段 2：设置子页 ================= */
  const CFG2 = window.__CFG__ || {};   // 预览注入的配置快照
  function apiCall(name, fallback){
    const fn = api && api[name];
    if(typeof fn === "function"){
      const args=Array.prototype.slice.call(arguments,2);
      return Promise.resolve(fn.apply(api, args)).catch(err=>{
        // 不再静默吞异常：桥接参数不匹配等错误必须可见，避免"假成功"
        console.error("[apiCall] "+name+" 调用失败:", err);
        if(window.pywebview && window.pywebview.api){ try{ console.error("[apiCall] args:",JSON.stringify(args)); }catch(e){} }
        return fallback;
      });
    }
    console.warn("[apiCall] 桥接未就绪或方法不存在:",name);
    return Promise.resolve(fallback);
  }
  function setTest(el, msg, ok){ if(!el)return; el.textContent=msg; el.className="test-result "+(ok?"ok":"fail"); }

  // ---- 服务器设置 ----
  let serverLoaded=false;
  async function loadServerPage(){
    const cfg = await apiCall("getConfig", CFG2);
    if(cfg && typeof cfg==="object"){
      if($("svHost")) $("svHost").value = cfg.lms_host||"";
      if($("svPort")) $("svPort").value = cfg.lms_port||"9000";
      if($("svUser")) $("svUser").value = cfg.lms_user||"";
      if($("svPass")) $("svPass").value = (cfg.lms_pass==="******"?"":(cfg.lms_pass||""));
      // 播放器下拉
      const ps = await apiCall("getPlayers", (window.__PLAYERS__||[]));
      if($("svPlayer") && Array.isArray(ps)){
        $("svPlayer").innerHTML = '<option value="">自动选择</option>' + ps.map(p=>
          `<option value="${esc(p.id)}" ${String(p.id)===String(cfg.np_playerid)?"selected":""}>${esc(p.name)}</option>`).join("");
      }
    }
    serverLoaded=true;
  }
  if($("svTest")) $("svTest").addEventListener("click",async()=>{
    const r=await apiCall("testServer", window.__TESTSRV__||{ok:true,version:"9.x"},
      $("svHost").value,$("svPort").value,$("svUser").value,$("svPass").value);
    if(r&&r.ok!==false) setTest($("svResult"),`✓ 连接成功 · LMS ${r.version||""}`,true);
    else setTest($("svResult"),`✗ ${(r&&r.error)||"连接失败"}`,false);
  });
  if($("svSave")) $("svSave").addEventListener("click",async()=>{
    const r=await apiCall("saveServer",{ok:true},
      $("svHost").value,$("svPort").value,$("svUser").value,$("svPass").value,$("svPlayer").value);
    toast(r&&r.ok!==false?"服务器设置已保存":"保存失败");
  });

  // ---- 播放器引擎 ----
  let selectedDevice="";
  async function loadLaunchPage(){
    // 引擎实时状态
    try{
      const es=await apiCall("engineStatus",null);
      if(es){
        const on=!!es.running;
        if($("engineState")) $("engineState").textContent=on?"引擎运行中 (PID "+es.pid+")":"引擎未运行";
        if($("engineDot")) $("engineDot").classList.toggle("on",on);
        if($("engineToggle")) $("engineToggle").textContent=on?"停止引擎":"启动引擎";
        if($("engineLog") && Array.isArray(es.logs)) $("engineLog").textContent=es.logs.join("\n")||"暂无日志";
      }
    }catch(e){}
    const info=await apiCall("getLaunchInfo", window.__LAUNCH__||{binary:"",command:"squeezelite",version:"",autoRun:false,problems:[]});
    if(info){
      if($("engineVer")) $("engineVer").textContent = info.version?("squeezelite "+info.version):(info.binary||"未找到 squeezelite 可执行文件");
      if($("engineCmd")) $("engineCmd").textContent = info.command||"—";
      // 系统级开机自启真实状态（LaunchAgent）
      try{
        const ast=await apiCall("getAutoStartStatus",null);
        if(ast){
          if($("autoStart")) $("autoStart").checked=!!(ast.enabled&&ast.installed);
          if($("autoStartHint")) $("autoStartHint").textContent=
            !ast.isMac?"（仅 macOS 支持）":
            (ast.installed?(ast.loaded?"已安装并生效":"已安装，下次登录生效"):"未安装");
        }
      }catch(e){}
    }
    const scan=await apiCall("scanDevices", window.__DEVICES__||{devices:[],reasons:[],binary:""});
    renderDevices(scan);
    // 填入命名现值
    const cfg=await apiCall("getConfig",CFG2);
    if(cfg){
      if($("devHostName")) $("devHostName").value=cfg.host_name||"";
      if($("devShort")) $("devShort").value=cfg.device_short||"";
      if($("devTemplate")) $("devTemplate").value=cfg.name_template||"{host} - {short}";
      refreshDevNamePreview();
    }
    loadSync();
  }
  function renderDevices(scan){
    const box=$("deviceList"); if(!box)return;
    const devs=(scan&&scan.devices)||[];
    if(!devs.length){
      const why=(scan&&scan.reasons&&scan.reasons[0])||"未检测到输出设备";
      box.innerHTML=`<div class="empty-mini">${esc(why)}<br><span class="hint">在 macOS 真机上可扫描到内置输出与耳机</span></div>`;
      return;
    }
    if(!selectedDevice) selectedDevice=devs[0].id||devs[0].name||"";
    box.innerHTML=devs.map(d=>{
      const id=d.id||d.name;
      return `<div class="device-row ${String(id)===String(selectedDevice)?"sel":""}" data-id="${esc(id)}">
        <span class="dev-ico">🔊</span><span class="dev-name">${esc(d.name)}</span>
        ${d.is_default?'<span class="dev-tag">默认</span>':''}</div>`;
    }).join("");
    box.querySelectorAll(".device-row").forEach(el=>el.addEventListener("click",()=>{
      selectedDevice=el.dataset.id;
      box.querySelectorAll(".device-row").forEach(x=>x.classList.toggle("sel",x===el));
    }));
  }
  if($("devScan")) $("devScan").addEventListener("click",async()=>{
    $("deviceList").innerHTML='<div class="empty-mini">扫描中…</div>';
    const scan=await apiCall("scanDevices", window.__DEVICES__||{devices:[],reasons:[],binary:""});
    renderDevices(scan); toast("设备扫描完成");
  });
  // 设备命名：填入现值 + 预览 + 保存
  function refreshDevNamePreview(){
    const host=($("devHostName")&&$("devHostName").value.trim())||"本机";
    const short=($("devShort")&&$("devShort").value.trim())||"";
    const tpl=($("devTemplate")&&$("devTemplate").value.trim())||"{host} - {short}";
    let name=tpl.replace(/\{host\}/g,host).replace(/\{short\}/g,short);
    if(!short) name=name.replace(/\s*-\s*$/,"");
    if($("devNamePreview")) $("devNamePreview").textContent=name||"—";
  }
  ["devHostName","devShort","devTemplate"].forEach(id=>{
    const el=$(id); if(el) el.addEventListener("input",refreshDevNamePreview);
  });
  if($("devNameSave")) $("devNameSave").addEventListener("click",async()=>{
    const host=($("devHostName")&&$("devHostName").value.trim())||"";
    const short=($("devShort")&&$("devShort").value.trim())||"";
    const tpl=($("devTemplate")&&$("devTemplate").value.trim())||"{host} - {short}";
    const sel=$("deviceList")&&$("deviceList").querySelector(".device-row.sel");
    const devId=sel?sel.dataset.id:"";
    const r=await apiCall("saveDevice",{ok:true},devId,host,short,host,tpl);
    // 名称模板/本机名也写入配置（若后端支持）
    if(r&&r.ok!==false) toast("播放器命名已保存");
    else toast("保存失败");
  });

  let engineBusy=false;
  if($("engineToggle")) $("engineToggle").addEventListener("click",async()=>{
    if(engineBusy) return;
    engineBusy=true;
    const btn=$("engineToggle");
    const oldTxt=btn.textContent;
    btn.textContent="处理中…"; btn.disabled=true;
    try{
      const running=$("engineState").textContent.indexOf("运行中")>=0;
      const r=running
        ? await apiCall("stopEngine",{ok:false,error:"后端未连接"})
        : await apiCall("startEngine",{ok:false,error:"后端未连接"});
      if(r&&r.ok===false){ toast("操作失败："+(r.error||"未知错误").split("\n")[0]); }
      else{
        toast(r&&r.message||(running?"引擎已停止":"引擎已启动"));
        // 等 LMS 注册，稍后刷新状态与连接徽标
        setTimeout(async()=>{ await loadLaunchPage(); if(typeof updateConnBadge==="function") updateConnBadge(); }, running?400:1800);
        return;
      }
    }catch(e){ toast("引擎操作异常："+String(e).slice(0,60)); }
    finally{ btn.textContent=oldTxt; btn.disabled=false; engineBusy=false; }
  });
  if($("autoStart")) $("autoStart").addEventListener("change",async e=>{
    const want=e.target.checked;
    const r=await apiCall("setAutoStart",{ok:false,error:"后端未连接"},want);
    if(r&&r.ok===false){
      e.target.checked=!want;
      toast("设置失败："+(r.error||"").split("\n")[0]); return;
    }
    toast(r&&r.message||(want?"已设置开机自启":"已关闭开机自启"));
    if($("autoStartHint")) $("autoStartHint").textContent=want?"已安装并生效":"未安装";
  });

  // ---- 多端同播 ----
  let syncPlayers=[], syncSel=new Set(), syncMaster="";
  async function loadSync(){
    const data=await apiCall("getSyncStatus", window.__SYNC__||{players:[],current:"",masterId:""});
    syncPlayers=(data&&data.players)||[];
    syncMaster=(data&&(data.masterId||data.current))||"";
    // 默认勾选已连接设备
    syncSel=new Set(syncPlayers.filter(p=>p.connected).map(p=>p.id));
    renderSync();
  }
  function renderSync(){
    const box=$("syncList"); if(!box)return;
    if(!syncPlayers.length){
      box.innerHTML='<div class="empty-mini">未发现在线播放器<br><span style="font-size:11px">在 LMS 中连接 squeezelite / 手机 App 后会显示在这里</span></div>';
    } else {
      box.innerHTML=syncPlayers.map(p=>{
        const sync=(p.syncWith&&p.syncWith.length)?`同步中 · ${p.syncWith.length} 台`: "";
        const badge = !p.connected?'<span class="sync-badge off">离线</span>'
          : p.isplaying?'<span class="sync-badge playing">播放中</span>'
          : sync?'<span class="sync-badge synced">'+esc(sync)+'</span>':'';
        return `<div class="sync-row ${syncSel.has(p.id)?"sel":""} ${syncMaster===p.id?"master":""} ${p.connected?"":"off"}" data-id="${esc(p.id)}">
          <span class="sync-chk">✓</span>
          <span class="sync-ico">🔊</span>
          <div class="sync-meta"><div class="sync-name">${esc(p.name||p.id)}</div>
            <div class="sync-sub">${esc(p.model||"")}${p.ip?" · "+esc(p.ip):""}</div></div>
          ${badge}
          <span class="sync-master-radio" title="设为主控"></span>
        </div>`;
      }).join("");
      box.querySelectorAll(".sync-row").forEach(row=>{
        const id=row.dataset.id;
        row.addEventListener("click",e=>{
          const p=syncPlayers.find(x=>x.id===id); if(!p||!p.connected)return;
          if(e.target.classList.contains("sync-master-radio")){
            syncMaster=id; syncSel.add(id); renderSync(); return;
          }
          if(syncSel.has(id)){ if(id!==syncMaster) syncSel.delete(id); }
          else syncSel.add(id);
          if(!syncSel.has(syncMaster)&&syncSel.size) syncMaster=syncSel.values().next().value;
          renderSync();
        });
      });
    }
    const m=syncPlayers.find(x=>x.id===syncMaster);
    if($("syncMasterName")) $("syncMasterName").textContent=m?(m.name||m.id):"—";
  }
  if($("syncRefresh")) $("syncRefresh").addEventListener("click",async()=>{
    $("syncResult").textContent=""; await loadSync(); toast("播放器列表已刷新");
  });
  if($("syncApply")) $("syncApply").addEventListener("click",async()=>{
    if(!syncMaster){ $("syncResult").className="sync-result fail"; $("syncResult").textContent="请先选择一台主控播放器"; return; }
    const slaves=[...syncSel].filter(id=>id!==syncMaster);
    if(!slaves.length){ $("syncResult").className="sync-result fail"; $("syncResult").textContent="请至少勾选一台从端设备"; return; }
    $("syncResult").className="sync-result"; $("syncResult").textContent="正在建立同步组…";
    const r=await apiCall("setSync",{ok:true,message:"已建立同步组"},syncMaster,slaves);
    if(r&&r.ok!==false){
      $("syncResult").className="sync-result ok";
      $("syncResult").textContent="✓ "+(r.message||"已建立同步组")+`（主控：${(syncPlayers.find(x=>x.id===syncMaster)||{}).name||syncMaster}，从端 ${slaves.length} 台）`;
      await loadSync(); toast("多端同播已开启");
    } else {
      $("syncResult").className="sync-result fail";
      $("syncResult").textContent="✗ "+(r&&r.error||r&&r.message||"同步失败");
    }
  });
  if($("syncStop")) $("syncStop").addEventListener("click",async()=>{
    const targets=[...syncSel];
    $("syncResult").className="sync-result"; $("syncResult").textContent="正在取消同步…";
    const r=await apiCall("unsync",{ok:true,message:"已取消同步"},targets);
    if(r&&r.ok!==false){
      $("syncResult").className="sync-result ok";
      $("syncResult").textContent="✓ "+(r.message||"已取消同步");
      await loadSync(); toast("已取消同播");
    } else {
      $("syncResult").className="sync-result fail";
      $("syncResult").textContent="✗ "+(r&&r.error||"取消失败");
    }
  });

  // ---- 参数配置 ----
  const PARAM_GROUPS=[{k:"all",name:"全部"},{k:"core",name:"核心"},{k:"audio",name:"音频"},{k:"net",name:"网络"},{k:"other",name:"其他"}];
  let paramData=null, paramCat="all", paramValues={};
  async function loadParamsPage(){
    paramData=await apiCall("getParams", window.__PARAMS__||{params:[],values:{},preview:"squeezelite",problems:[],binary:""});
    renderParamCats(); renderParams();
  }
  function renderParamCats(){
    const box=$("paramCats"); if(!box||!paramData)return;
    box.innerHTML=PARAM_GROUPS.map(g=>`<button data-k="${g.k}" class="${paramCat===g.k?"on":""}">${g.name}</button>`).join("");
    box.querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{paramCat=b.dataset.k;renderParamCats();renderParams();}));
  }
  function renderParams(){
    const box=$("paramList"); if(!box||!paramData)return;
    let defs=paramData.params||[];
    if(paramCat!=="all") defs=defs.filter(p=>paramGroup(p)===paramCat);
    paramValues=Object.assign({},paramData.values||{});
    box.innerHTML=defs.length? defs.map(p=>{
      const k=p.key, v=paramValues[k]!=null?paramValues[k]:(p.default||"");
      // 后端 PARAMS 用 options=[(值,显示名,效果),...]；兼容 choices
      const opts=p.options||p.choices||[];
      let ctrl="";
      if(opts.length && typeof opts[0]==="string"){
        ctrl=`<select data-k="${esc(k)}">${opts.map(c=>`<option value="${esc(c)}" ${String(c)===String(v)?"selected":""}>${esc(c)}</option>`).join("")}</select>`;
      } else if(opts.length && Array.isArray(opts[0])){
        ctrl=`<select data-k="${esc(k)}">${opts.map(o=>{
          const val=o[0], label=o[1]||o[0];
          return `<option value="${esc(val)}" ${String(val)===String(v)?"selected":""}>${esc(label)}</option>`;
        }).join("")}</select>`;
      } else if(p.kind==="bool"){
        ctrl=`<select data-k="${esc(k)}"><option value="" ${!v?"selected":""}>关闭</option><option value="1" ${v?"selected":""}>启用</option></select>`;
      } else {
        ctrl=`<input type="text" data-k="${esc(k)}" value="${esc(v)}" placeholder="${esc(p.default||"")}">`;
      }
      // 选中项的「具体效果」说明
      let eff="";
      if(opts.length && Array.isArray(opts[0])){
        const hit=opts.find(o=>String(o[0])===String(v));
        if(hit && hit[2]) eff=String(hit[2]);
      }
      if(!eff && p.effect) eff=p.effect;
      const rec=p.recommend!=null&&p.recommend!==""?String(p.recommend):"";
      const recTag=rec?`<span class="param-rec" title="最优音质推荐值">★ 推荐 ${esc(rec||"留空")}</span>`:"";
      const detail=p.detail?`<div class="param-detail">${esc(p.detail)}</div>`:"";
      const effect=eff?`<div class="param-effect">${esc(eff)}</div>`:"";
      const range=p.range?`<div class="param-range">取值范围：${esc(p.range)}</div>`:"";
      const help=(effect||detail||range)?`<div class="param-help">${effect}${detail}${range}</div>`:"";
      return `<div class="param-item">
        <div class="param-head"><label>${esc(p.name)} <em>${esc(p.flag)}</em></label>${recTag}</div>
        <div class="param-ctrl">${ctrl}</div>
        ${help}
      </div>`;
    }).join(""):'<div class="empty-mini">该分类暂无参数</div>';
    box.querySelectorAll("input,select").forEach(el=>el.addEventListener("change",()=>{
      paramValues[el.dataset.k]=el.value; updateParamPreview();
      // 切换选项后刷新该项的说明文字
      const item=el.closest(".param-item");
      const def=defs.find(x=>x.key===el.dataset.k);
      if(item&&def){
        const opts=def.options||def.choices||[];
        if(opts.length&&Array.isArray(opts[0])){
          const hit=opts.find(o=>String(o[0])===String(el.value));
          const eff=item.querySelector(".param-effect");
          if(eff&&hit&&hit[2]) eff.textContent=String(hit[2]);
        }
      }
    }));
    if($("paramPreview")) $("paramPreview").textContent=paramData.preview||"—";
    const probs=paramData.problems||[];
    if($("paramProblems")) $("paramProblems").innerHTML=probs.length?probs.map(esc).join("<br>"):"";
  }
  function paramGroup(p){
    const f=(p.flag||"")+" "+(p.key||"");
    if(/name|mac|server|model|codec|buffer|priority|daemon|logfile|pidfile/.test(f))return "core";
    if(/rate|resample|dsd|bits|output|device|visual|wave|format/.test(f))return "audio";
    if(/server|host|port|name|model/.test(f))return "net";
    return "other";
  }
  function updateParamPreview(){
    if(!paramData)return;
    // 预览：用桥接重算；预览环境用简化拼接
    if(api.saveParams){ api.saveParams(paramValues, "").then(r=>{ if(r&&r.preview&&$("paramPreview"))$("paramPreview").textContent=r.preview; }).catch(()=>{}); }
    else if($("paramPreview")) $("paramPreview").textContent="squeezelite " + Object.entries(paramValues).filter(([,v])=>v).map(([k,v])=>k+"="+v).join(" ");
  }
  if($("paramSave")) $("paramSave").addEventListener("click",async()=>{
    const r=await apiCall("saveParams",{ok:true,preview:"squeezelite"},paramValues,"");
    toast(r&&r.ok!==false?"参数已保存":"参数校验未通过");
  });
  if($("paramBest")) $("paramBest").addEventListener("click",async()=>{
    if(!confirm("应用最优音质方案（bit-perfect）？\n将把各参数设为推荐值，并保留你已选的输出设备、播放器名称与 LMS 服务器。"))return;
    const r=await apiCall("applyBestParams",{ok:true,applied:{},preview:"squeezelite"});
    if(r&&r.ok===false){ toast("应用失败："+(r.error||"")); return; }
    toast("已应用最优音质方案 ★");
    await loadParamsPage();
  });

  // ---- 升级与更新 ----
  async function loadUpdatePage(){
    const info=await apiCall("checkUpdates", window.__UPDATES__||{local:"",squeezelite:{arch:"m1",items:[],latest:{}},lms:{},errors:[]});
    if(info){
      if($("verLocal")) $("verLocal").textContent=info.local||"未安装";
      if($("verLatest")) $("verLatest").textContent=(info.squeezelite&&info.squeezelite.latest&&info.squeezelite.latest.version)||"—";
      if($("verArch")) $("verArch").textContent=(info.squeezelite&&info.squeezelite.arch)||"—";
    }
    renderChangelog(await apiCall("getChangeLog", window.__CHANGELOG__||{items:[],source:""},"sl"));
  }
  function renderChangelog(data){
    const box=$("changeLog"); if(!box)return;
    const items=(data&&data.items)||[];
    box.innerHTML=items.length?items.map(it=>`<div class="change-row"><b>${esc(it.title||it.version||"")}</b><p>${esc(it.body||it.detail||"")}</p></div>`).join(""):'<div class="empty-mini">暂无更新日志</div>';
  }
  if($("checkUpdates")) $("checkUpdates").addEventListener("click",async()=>{
    $("verLatest").textContent="检查中…";
    const info=await apiCall("checkUpdates", window.__UPDATES__||{local:"",squeezelite:{arch:"m1",items:[],latest:{version:"v2.0.0"}},lms:{},errors:[]});
    if($("verLatest")) $("verLatest").textContent=(info.squeezelite&&info.squeezelite.latest&&info.squeezelite.latest.version)||"—";
    renderChangelog(await apiCall("getChangeLog", window.__CHANGELOG__||{items:[]},"sl"));
    toast("更新检查完成");
  });
  if($("logRefresh")) $("logRefresh").addEventListener("click",async()=>{
    renderChangelog(await apiCall("getChangeLog", window.__CHANGELOG__||{items:[]},"sl"));
  });
  if($("autoUpgrade")) $("autoUpgrade").addEventListener("change",async e=>{
    await apiCall("setAutoUpgrade",{ok:true},e.target.checked); toast("已更新自动检查设置");
  });
  // 立即更新 squeezelite：下载并就地替换内置/本机二进制
  let upgrading=false;
  if($("doUpgrade")) $("doUpgrade").addEventListener("click",async()=>{
    if(upgrading) return;
    const btn=$("doUpgrade"); const oldTxt=btn.textContent;
    upgrading=true; btn.textContent="更新中…"; btn.disabled=true;
    if($("upgradeLog")) $("upgradeLog").textContent="正在查询最新版本并下载，请稍候（可能需要 1-3 分钟）…";
    try{
      const r=await apiCall("upgradeSqueezelite",{ok:false,error:"后端未连接"});
      if($("upgradeLog")) $("upgradeLog").textContent=(r&&r.logs&&r.logs.length)?r.logs.join("\n"):(r&&r.message)||(r&&r.error)||"无日志";
      if(r&&r.ok===false){ toast("更新失败："+(r.error||"").split("\n")[0]); }
      else{ toast("squeezelite 更新成功"+(r&&r.version?(" · "+r.version):"")); await loadUpdatePage(); }
    }catch(e){ toast("更新异常："+String(e).slice(0,60)); }
    finally{ btn.textContent=oldTxt; btn.disabled=false; upgrading=false; }
  });

  /* ================= 收藏体系 / 面板缩放 ================= */

  // ---- 收藏：状态查询与切换 ----
  function isFav(it){
    if(!it) return false;
    const id=String(it.id||it.track_id||"");
    return !!id && S.favorites.map(String).includes(id);
  }
  async function loadFavorites(){
    const r=await apiCall("getFavorites",null);
    if(r && r.ids){ S.favorites=r.ids.map(String); refreshFavUI(); }
  }
  async function toggleFav(it, force){
    const id=String(it.id||it.track_id||"");
    if(!id){ toast("该条目没有可收藏的 ID"); return; }
    const before=S.favorites.includes(id);
    const meta={title:it.title||it._name||"",artist:it.artist||"",album:it.album||""};
    const r=await apiCall("toggleFavorite",{ok:true,favorited:!before},id,force===undefined?null:force,meta);
    if(r && r.ok===false){ toast("收藏失败："+(r.error||"")); return; }
    const now = (r && typeof r.favorited==="boolean") ? r.favorited : !before;
    if(now && !S.favorites.includes(id)) S.favorites.push(id);
    if(!now) S.favorites=S.favorites.filter(x=>x!==id);
    refreshFavUI();
    toast(now?("♥ 已收藏："+itemName(it,S.cat)):("已取消收藏："+itemName(it,S.cat)));
    // 收藏会增减「♥ 收藏」列表曲目，刷新两处播放列表下拉以联动数量
    loadPlaylists().then(()=>{
      const lpd=$("lpdSelect");
      if(lpd && $("libPlDrawer") && !$("libPlDrawer").hidden){ lpd.innerHTML=plOptions(S.playlists,true); lpd.value=S.lpdPid||""; }
    });
  }
  function refreshFavUI(){
    // 音乐库条目
    document.querySelectorAll(".lib-item .fav-mini").forEach(b=>{
      const on=S.favorites.includes(String(b.dataset.fav));
      b.classList.toggle("on",on); b.textContent=on?"♥":"♡";
    });
    // 播放器顶部
    const pf=$("pFav");
    if(pf && S.track){
      const on=S.favorites.includes(String(S.track.id||""));
      pf.classList.toggle("on",on); pf.textContent=on?"♥":"♡";
    }
    // 播放列表行
    document.querySelectorAll(".pl-fav").forEach(b=>{
      const on=S.favorites.includes(String(b.dataset.fav));
      b.classList.toggle("on",on); b.textContent=on?"♥":"♡";
    });
    // 右键菜单当前目标
    const ctx=$("ctxMenu");
    if(ctx && S.ctxItem){
      const on=isFav(S.ctxItem);
      const lbl=ctx.querySelector('[data-act="fav"] .fav-label');
      if(lbl) lbl.textContent=on?"取消收藏":"收藏";
    }
  }
  if($("pFav")) $("pFav").addEventListener("click",()=>{ if(S.track) toggleFav(S.track); });
  // ---- 音乐库内播放列表抽屉（就地查看，不跳转播放器）----
  function renderLpd(list, curIdx, emptyMsg, curId){
    const body=$("lpdBody"); if(!body)return;
    const sig="l:"+(S.lpdPid||"q")+":"+list.map(x=>String(x.id||x.track_id||x._name||"")).join("|")+"#"+curIdx+"#"+(curId||"");
    if(body.dataset.lpdSig===sig) return;
    body.dataset.lpdSig=sig;
    if(!list || !list.length){ body.innerHTML=`<div class="empty-mini">${emptyMsg||"当前队列为空 · 右键曲目可加入"}</div>`;
      $("lpdFoot").textContent="— 首"; return; }
    body.innerHTML=list.map((it,i)=>{
      const cur=(i===curIdx) || (!!curId && String(it.id||it.track_id||"")===curId);
      const name=it.title||it._name||it.album||it.artist||it.id||"";
      return `<div class="pl-row ${cur?"cur":""}" data-index="${i}">
        <span class="pl-n">${cur?'<b class="now-playing">▶</b>':String(i+1).padStart(2,"0")}</span>
        <span class="pl-t" title="${esc(name)}">${esc(name)}</span>
        <button class="pl-fav ${isFav(it)?"on":""}" data-fav="${esc(it.id||it.track_id||"")}" title="收藏">${isFav(it)?"♥":"♡"}</button>
        <button class="pl-remove" data-remove="${i}" title="移除">×</button></div>`;
    }).join("");
    $("lpdFoot").textContent=list.length+" 首"+(curIdx!=null&&curIdx>=0?` · 第 ${curIdx+1} 首播放中`:"");
    body.querySelectorAll(".pl-row").forEach(el=>el.addEventListener("click",e=>{
      if(e.target.closest(".pl-remove")||e.target.closest(".pl-fav"))return;
      if(S.lpdPid){ loadNamedThenPlay(S.lpdPid, Number(el.dataset.index)); }
      else apiCall("queuePlayIndex",{ok:true},Number(el.dataset.index)).then(()=>loadQueue());
    }));
    body.querySelectorAll(".pl-remove").forEach(b=>b.addEventListener("click",async e=>{
      e.stopPropagation(); const i=Number(b.dataset.remove);
      if(S.lpdPid && isFavPlaylist(S.lpdPid)){
        // 收藏列表内移除 = 取消收藏，走 toggleFav 以同步心形状态
        const it=list[i]; if(it){ await toggleFav(it,false); }
      } else if(S.lpdPid) await apiCall("playlistRemove",{ok:true},S.lpdPid,i);
      else await apiCall("queueRemove",{ok:true},i);
      refreshLpd();
    }));
  }
  async function loadNamedThenPlay(pid, index){
    const r=await apiCall("playlistTracks",{items:[]},pid);
    const items=(r&&r.items)||[];
    if(!items.length){ toast("列表为空"); return; }
    // 本地歌单：整单载入 LMS 队列并从此曲开始，队列有多首才能测试切歌
    const pl=(S.playlists||[]).find(x=>String(x.id)===String(pid));
    if(pl && pl.local){
      const res=await apiCall("playlistPlayAll",{ok:false},pid,index);
      if(res&&res.ok){ toast(`已载入歌单 ${res.added} 首，正在播放第 ${index+1} 首`); loadQueue(); return; }
      toast("载入歌单失败："+((res&&res.error)||""));
    }
    const tid=String(items[index]&&(items[index].id||items[index].track_id)||"");
    if(tid){ await apiCall("libPlay","titles",tid); toast("已开始播放"); }
  }
  async function refreshLpd(q){
    const pid=S.lpdPid||"";
    if(!pid){
      const r=q||await apiCall("getQueue",window.__QUEUE__||{items:window.__QUEUE_ITEMS__||[],index:0,mode:"0 0"});
      S.queue=(r&&r.items)||[]; renderLpd(S.queue,(r&&r.index)||0);
    } else {
      const r=await apiCall("playlistTracks",{items:[]},pid);
      renderLpd((r&&r.items)||[], -1, "该播放列表暂无曲目", String(S.track&&S.track.id||""));
    }
  }
  // 统一的播放列表 <option> 渲染：收藏列表置顶并标注 ♥，便于识别与保护
  function plOptions(list, includeQueue){
    const favs = list.filter(p=>p.isFav||p.locked);
    const rest = list.filter(p=>!(p.isFav||p.locked));
    const ordered = favs.concat(rest);
    const head = includeQueue ? '<option value="">当前队列</option>' : '';
    return head + ordered.map(p=>{
      const mark = '';   // 列表名已含 ♥，避免显示两个心
      return `<option value="${esc(p.id)}">${mark}${esc(p.name)} (${p.trackcount||0})</option>`;
    }).join("");
  }
  function isFavPlaylist(pid){
    const p=(S.playlists||[]).find(x=>String(x.id)===String(pid));
    return !!(p && (p.isFav||p.locked));
  }
  async function openLibPlDrawer(){
    $("libPlDrawer").hidden=false; $("libPlMask").hidden=false;
    S.lpdPid="";
    const sel=$("lpdSelect");
    await loadPlaylists();
    if(sel){ sel.innerHTML=plOptions(S.playlists, true); sel.value=""; }
    refreshLpd();
  }
  function closeLibPlDrawer(){ $("libPlDrawer").hidden=true; $("libPlMask").hidden=true; }
  $("libPlBtn").addEventListener("click",()=>{
    const d=$("libPlDrawer");
    if(d && !d.hidden) closeLibPlDrawer(); else openLibPlDrawer();
  });
  $("libPlClose").addEventListener("click",closeLibPlDrawer);
  $("libPlMask").addEventListener("click",closeLibPlDrawer);
  if($("lpdSelect")) $("lpdSelect").addEventListener("change",e=>{
    S.lpdPid=e.target.value; refreshLpd();
  });
  if($("lpdRefresh")) $("lpdRefresh").addEventListener("click",async()=>{
    await loadPlaylists(); refreshLpd(); toast("已刷新");
  });
  if($("lpdNew")) $("lpdNew").addEventListener("click",async()=>{
    const n=prompt("新建播放列表名称：","我的播放列表");
    if(!n || !n.trim())return;
    const r=await apiCall("createPlaylist",{ok:true},n.trim());
    if(r&&r.ok===false){ toast("创建失败："+(r.error||"")); return; }
    toast("已创建："+n.trim());
    await loadPlaylists();
    const sel=$("lpdSelect");
    if(sel){ sel.innerHTML=plOptions(S.playlists,true); const found=S.playlists.find(x=>x.name===n.trim()); if(found)sel.value=String(found.id); }
    S.lpdPid = sel ? sel.value : "";
    refreshLpd();
  });
  if($("lpdDel")) $("lpdDel").addEventListener("click",async()=>{
    const sel=$("lpdSelect"); const pid=sel?sel.value:"";
    if(!pid){ toast("请先选择一个播放列表（当前队列不可删除）"); return; }
    if(isFavPlaylist(pid)){ toast("「♥ 收藏」为系统列表，不可删除"); return; }
    const p=S.playlists.find(x=>String(x.id)===String(pid));
    if(!confirm(`确定删除播放列表「${p?p.name:pid}」？`))return;
    const r=await apiCall("deletePlaylist",{ok:true},pid);
    if(r&&r.ok===false){ toast("删除失败："+(r.error||"")); return; }
    toast("已删除"); S.lpdPid="";
    await loadPlaylists();
    if(sel){ sel.innerHTML=plOptions(S.playlists,true); sel.value=""; }
    refreshLpd();
  });
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape" && $("libPlDrawer") && !$("libPlDrawer").hidden) closeLibPlDrawer();
  });

  // ---- 面板拖拽缩放（双击复位）----
  (function initPanelResize(){
    document.querySelectorAll(".ppanel").forEach(panel=>{
      const body=panel.querySelector(".ppanel-body");
      const handle=panel.querySelector(".ppanel-resize");
      if(!body||!handle) return;
      handle.addEventListener("dblclick",e=>{
        e.preventDefault();
        body.style.height="";
        body.style.maxHeight="";
        toast("面板高度已复位");
      });
      handle.addEventListener("mousedown",e=>{
        e.preventDefault();
        const startY=e.clientY;
        const startH=body.getBoundingClientRect().height;
        document.body.classList.add("ppanel-resizing");
        const move=ev=>{
          let h=startH+(ev.clientY-startY);
          h=Math.max(140,Math.min(720,h));
          body.style.height=h+"px";
          body.style.maxHeight=h+"px";
        };
        const up=()=>{
          document.removeEventListener("mousemove",move);
          document.removeEventListener("mouseup",up);
          document.body.classList.remove("ppanel-resizing");
        };
        document.addEventListener("mousemove",move);
        document.addEventListener("mouseup",up);
      });
    });
  })();

  /* ================= 增强交互：下钻 / 右键 / 播放列表 / 模式 / 状态 ================= */

  // ---- 下钻浏览 ----
  const DRILL_LABEL={albums:"专辑",artists:"艺术家",genres:"流派",titles:"曲目"};
  const DRILL_FILTER={albums:"album_id",artists:"artist_id",genres:"genre_id"};
  function crumbRender(){
    const bar=$("crumbBar"); if(!bar)return;
    bar.hidden = S.crumbs.length===0;
    if(!S.crumbs.length){ bar.innerHTML=""; return; }
    const parts=[`<button data-crumb="-1">音乐库</button>`];
    S.crumbs.forEach((c,i)=>parts.push(`<span class="cx-crumb-sep">›</span><button data-crumb="${i}">${esc(c.label)}</button>`));
    bar.innerHTML=parts.join("");
    bar.querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{
      const i=Number(b.dataset.crumb);
      if(i<0){ S.crumbs=[]; S.browseItems=null; S.cat="albums"; syncCatButtons(); }
      else { S.crumbs=S.crumbs.slice(0,i+1); S.browseItems = i===S.crumbs.length-1 ? S.lastBrowse : null; }
      renderLibrary();
    }));
  }
  function syncCatButtons(){
    document.querySelectorAll("#libCats button").forEach(x=>x.classList.toggle("on",x.dataset.cat===S.cat));
  }
  async function drillInto(it){
    const cat=S.cat;
    const name=itemName(it,cat);
    const fkey=DRILL_FILTER[cat];
    const id=String(it.id||"");
    if(!fkey||!id){ toast("该条目不支持查看曲目"); return; }
    const filters=[fkey+":"+id];
    const r=await apiCall("libBrowse",{items:[],total:0},"titles",0,500,filters);
    const items=(r&&r.items)||[];
    if(!items.length){ toast("该"+DRILL_LABEL[cat]+"下暂无曲目"); return; }
    S.crumbs.push({label:name,cat:cat,filters:filters});
    S.lastBrowse=items; S.browseItems=items;
    $("libSearch").value=""; S.query="";
    renderLibrary();
    toast(`已展开 ${name} · ${items.length} 首`);
  }
  // filtered() 支持下钻结果
  const _origFiltered=filtered;
  filtered=function(){
    if(S.browseItems){
      let arr=S.browseItems.slice();
      if(S.query) arr=arr.filter(it=>itemName(it,"titles").toLowerCase().includes(S.query)
        ||(it.artist||"").toLowerCase().includes(S.query));
      arr.sort((a,b)=>{ const c=itemName(a,"titles").localeCompare(itemName(b,"titles"),"zh-CN",{numeric:true});
        return S.sortAsc?c:-c; });
      return arr;
    }
    return _origFiltered();
  };
  // renderLibrary 内调用面包屑渲染
  const _origBuildAlpha=buildAlpha;
  // 在 renderLibrary 末尾（buildAlpha 后）补面包屑 —— 用包装函数
  // 采用直接 hook：在 buildAlpha 定义之后的函数体内无法插入，故在 renderLibrary 调用后统一刷新
  function refreshLibraryExtras(){ crumbRender(); }

  // ---- 右键上下文菜单 ----
  function openCtxMenu(e,it){
    S.ctxItem=it;
    const m=$("ctxMenu"); if(!m)return;
    const isDrill = S.cat!=="titles" && !S.browseItems;
    m.querySelector('[data-act="drill"]').hidden=!isDrill;
    m.style.left=Math.min(e.clientX, window.innerWidth-200)+"px";
    m.style.top=Math.min(e.clientY, window.innerHeight-260)+"px";
    m.hidden=false;
    refreshFavUI();
  }
  function closeCtxMenu(){ const m=$("ctxMenu"); if(m)m.hidden=true; }
  document.addEventListener("click",()=>closeCtxMenu());
  document.addEventListener("scroll",()=>closeCtxMenu(),true);
  if($("ctxMenu")) $("ctxMenu").addEventListener("click",async e=>{
    const b=e.target.closest("button[data-act]"); if(!b)return;
    const act=b.dataset.act, it=S.ctxItem; closeCtxMenu();
    if(!it)return;
    const tid=String(it.id||it.track_id||"");
    switch(act){
      case "play": playItem(it); break;
      case "next": {
        const r=await apiCall("queueAdd",{ok:false},tid,true);
        toast(r&&r.ok===false?("加入失败："+(r&&r.error||"")):`已设为下一首：${itemName(it,S.cat)}`);
        break;
      }
      case "queue": {
        const r=await apiCall("queueAdd",{ok:false},tid,false);
        if(r&&r.ok===false){ toast("加入失败："+(r&&r.error||"")); break; }
        toast(`已加入当前队列：${itemName(it,S.cat)}`);
        // 强制切回"当前队列"视图并刷新，否则面板停在命名列表看不到新加的歌
        S.plSource=""; const sel=$("plSelect"); if(sel) sel.value="";
        await loadQueue();
        const pp=document.querySelector('.ppanel[data-panel="playlist"]');
        if(pp && pp.hidden){ pp.hidden=false; }  // 自动展开播放列表面板
        break;
      }
      case "pl": openPlModal(it); break;
      case "fav": toggleFav(it); break;
      case "drill": drillInto(it); break;
      case "info": await showInfo(it); break;
    }
  });

  // ---- 显示信息弹窗 ----
  async function showInfo(it){
    const name=itemName(it,S.cat);
    const data=await apiCall("libInfo",{lines:[],text:"",source:""},it);
    const lines=(data&&data.lines)||[];
    const body=$("infoBody");
    body.innerHTML = lines.length
      ? lines.map(l=>{ const i=l.indexOf("："); const k=i>=0?l.slice(0,i):""; const v=i>=0?l.slice(i+1):l;
          return `<div class="info-row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`; }).join("")
      : `<div class="empty-mini">暂无更多信息</div>`;
    $("infoTitle").textContent="曲目信息 · "+name;
    $("infoModal").hidden=false;
  }
  if($("infoClose")) $("infoClose").addEventListener("click",()=>$("infoModal").hidden=true);
  if($("infoModal")) $("infoModal").addEventListener("click",e=>{ if(e.target.id==="infoModal")e.currentTarget.hidden=true; });

  // ---- 加入播放列表弹窗 ----
  async function openPlModal(it){
    const pls=await loadPlaylists();
    const plMeta={title:it.title||it._name||"",artist:it.artist||"",album:it.album||""};
    const body=$("plModalBody");
    const name=esc(itemName(it,S.cat));
    if(!pls.length){
      body.innerHTML=`<div class="empty-mini">还没有播放列表，请先新建一个</div>
        <div class="pl-new-row"><input id="plNewNameInline" placeholder="新播放列表名称"><button class="btn primary" id="plCreateInline">创建并加入</button></div>`;
      $("plCreateInline").addEventListener("click",async()=>{
        const n=$("plNewNameInline").value.trim(); if(!n)return;
        const r=await apiCall("createPlaylist",{ok:true},n);
        if(r&&r.ok!==false){ const list=await loadPlaylists(); const found=list.find(x=>x.name===n);
          if(found){ await apiCall("playlistAdd",{ok:true},found.id,String(it.id||it.track_id||""),plMeta); }
          $("plModal").hidden=true; toast(`已创建并加入：${n}`); loadPlaylists();
        } else toast("创建失败");
      });
    } else {
      body.innerHTML=`<div class="pl-pick-hint">将「${name}」加入：</div>`+
        pls.map(p=>`<button class="pl-pick" data-id="${esc(p.id)}">▤ ${esc(p.name)} <small>${p.trackcount||0} 首</small></button>`).join("")+
        `<div class="pl-new-row"><input id="plNewNameInline" placeholder="或新建播放列表…"><button class="btn" id="plCreateInline">新建</button></div>`;
      body.querySelectorAll(".pl-pick").forEach(b=>b.addEventListener("click",async()=>{
        const r=await apiCall("playlistAdd",{ok:true},b.dataset.id,String(it.id||it.track_id||""),plMeta);
        toast(r&&r.ok===false?"加入失败":"已加入播放列表"); $("plModal").hidden=true;
      }));
      $("plCreateInline").addEventListener("click",async()=>{
        const n=$("plNewNameInline").value.trim(); if(!n)return;
        const r=await apiCall("createPlaylist",{ok:true},n);
        if(r&&r.ok!==false){ const list=await loadPlaylists(); const found=list.find(x=>x.name===n);
          if(found) await apiCall("playlistAdd",{ok:true},found.id,String(it.id||it.track_id||""),plMeta);
          $("plModal").hidden=true; toast(`已创建并加入：${n}`); loadPlaylists();
        } else toast("创建失败");
      });
    }
    $("plModal").hidden=false;
  }
  if($("plModalClose")) $("plModalClose").addEventListener("click",()=>$("plModal").hidden=true);
  if($("plModal")) $("plModal").addEventListener("click",e=>{ if(e.target.id==="plModal")e.currentTarget.hidden=true; });

  // ---- 播放列表管理 ----
  async function loadPlaylists(){
    const r=await apiCall("getPlaylists",{items:window.__PL__||[]});
    const items=(r&&r.items)||[]; S.playlists=items;
    const sel=$("plSelect");
    if(sel){
      const cur=sel.value;
      sel.innerHTML=plOptions(items, true);
      if(cur)sel.value=cur;
    }
    return items;
  }
  async function loadQueue(){
    const r=await apiCall("getQueue",window.__QUEUE__||{items:window.__QUEUE_ITEMS__||[],index:0,mode:"0 0"});
    S.queue=(r&&r.items)||[];
    if(!S.plSource) renderQueuePanel(r);
    // 音乐库播放列表抽屉打开时同步当前曲目（顶层队列模式）
    if($("libPlDrawer") && !$("libPlDrawer").hidden && !S.lpdPid) refreshLpd(r);
  }
  function renderQueuePanel(q){
    const box=$("playlistBox"); if(!box)return;
    const items=S.queue;
    const curIdx=(q&&q.index)||0;
    const sig="q:"+items.map(x=>String(x.id||x.track_id||x._name||"")).join("|")+"#"+curIdx;
    if(box.dataset.plSig===sig) return;  // 内容未变不重绘，消除每秒刷新造成的闪动
    box.dataset.plSig=sig;
    if(!items.length){ box.innerHTML='<div class="empty-mini">当前队列为空 · 右键曲目可加入</div>'; return; }
    box.innerHTML=items.map((it,i)=>{
      const cur=i===curIdx;
      const name=it.title||it._name||it.album||it.id||"";
      return `<div class="pl-row ${cur?"cur":""}" data-index="${i}">
        <span class="pl-n">${cur?'<b class="now-playing">▶</b>':String(i+1).padStart(2,"0")}</span>
        <span class="pl-t">${esc(name)}</span>
        <button class="pl-fav ${isFav(it)?"on":""}" data-fav="${esc(it.id||"")}" title="收藏">${isFav(it)?"♥":"♡"}</button>
        <button class="pl-remove" data-remove="${i}" title="移除">×</button></div>`;
    }).join("");
    box.querySelectorAll(".pl-row").forEach(el=>el.addEventListener("click",e=>{
      if(e.target.closest(".pl-remove"))return;
      apiCall("queuePlayIndex",{ok:true},Number(el.dataset.index));
    }));
    box.querySelectorAll(".pl-remove").forEach(b=>b.addEventListener("click",async e=>{
      e.stopPropagation();
      await apiCall("queueRemove",{ok:true},Number(b.dataset.remove)); loadQueue();
    }));
  }
  // 播放列表心形点击委托（覆盖队列与命名列表两种渲染）
  document.addEventListener("click",async e=>{
    const fb=e.target.closest(".pl-fav");
    if(!fb)return;
    e.stopPropagation(); e.preventDefault();
    const id=String(fb.dataset.fav||"");
    if(!id)return;
    const row=fb.closest(".pl-row");
    const title=row?row.querySelector(".pl-t"):null;
    const it = S.queue.find(x=>String(x.id)===id) || {id:id,title:title?title.textContent:""};
    await toggleFav(it);
  });

  async function renderPlTracks(pid){
    const box=$("playlistBox"); if(!box)return;
    const r=await apiCall("playlistTracks",{items:[]},pid);
    if(S.plSource!==pid) return;               // 期间已切换来源，丢弃旧结果
    const items=(r&&r.items)||[];
    const curId=String(S.track&&S.track.id||"");
    const sig="p:"+pid+":"+items.map(x=>String(x.id||x.track_id||x._name||"")).join("|")+"#"+curId;
    if(box.dataset.plSig===sig) return;
    box.dataset.plSig=sig;
    if(!items.length){ box.innerHTML='<div class="empty-mini">该播放列表暂无曲目 · 右键曲目加入</div>'; return; }
    box.innerHTML=items.map((it,i)=>{
      const cur=!!curId && String(it.id||it.track_id||"")===curId;
      return `<div class="pl-row ${cur?"cur":""}" data-index="${i}">
      <span class="pl-n">${cur?'<b class="now-playing">▶</b>':String(i+1).padStart(2,"0")}</span>
      <span class="pl-t">${esc(it.title||it._name||it.album||it.id||"")}</span>
      <button class="pl-fav ${isFav(it)?"on":""}" data-fav="${esc(it.id||"")}" title="收藏">${isFav(it)?"♥":"♡"}</button>
      <button class="pl-remove" data-remove="${i}" title="移除">×</button></div>`; }).join("");
    box.querySelectorAll(".pl-row").forEach(el=>el.addEventListener("click",e=>{
      if(e.target.closest(".pl-remove")||e.target.closest(".pl-fav"))return;
      const idx=Number(el.dataset.index);
      if(S.plSource) { loadNamedThenPlay(S.plSource, idx); return; }
      const it=items[idx]; if(it) playItem(it);
    }));
    box.querySelectorAll(".pl-remove").forEach(b=>b.addEventListener("click",async e=>{
      e.stopPropagation(); const i=Number(b.dataset.remove);
      if(isFavPlaylist(pid)){
        const it=items[i]; if(it){ await toggleFav(it,false); }
      } else await apiCall("playlistRemove",{ok:true},pid,i);
      renderPlTracks(pid); loadPlaylists();
    }));
  }
  if($("plRefresh")) $("plRefresh").addEventListener("click",async()=>{
    await loadPlaylists(); S.plSource=$("plSelect").value;
    if(S.plSource) renderPlTracks(S.plSource); else loadQueue();
    toast("播放列表已刷新");
  });
  if($("plSelect")) $("plSelect").addEventListener("change",async e=>{
    S.plSource=e.target.value;
    if(S.plSource) renderPlTracks(S.plSource); else loadQueue();
  });
  if($("plNew")) $("plNew").addEventListener("click",async()=>{
    const n=prompt("新建播放列表名称：","我的播放列表");
    if(!n)return;
    const r=await apiCall("createPlaylist",{ok:true},n);
    if(r&&r.ok===false){ toast("创建失败："+(r.error||"")); return; }
    toast(`已创建：${n}`);
    await loadPlaylists();
    const sel=$("plSelect"); if(sel && r&&r.id){ sel.value=String(r.id); S.plSource=String(r.id); renderPlTracks(r.id); }
  });
  if($("plDel")) $("plDel").addEventListener("click",async()=>{
    const pid=$("plSelect").value;
    if(!pid){ toast("请先选择一个播放列表（当前队列不可删除）"); return; }
    if(isFavPlaylist(pid)){ toast("「♥ 收藏」为系统列表，不可删除"); return; }
    const p=S.playlists.find(x=>String(x.id)===pid);
    if(!confirm(`确定删除播放列表「${p?p.name:pid}」？`))return;
    const r=await apiCall("deletePlaylist",{ok:true},pid);
    toast(r&&r.ok===false?"删除失败":"已删除");
    S.plSource=""; await loadPlaylists(); loadQueue();
  });

  // ---- 播放模式 ----
  const MODE_MAP={seq:[0,0],loop:[0,1],one:[0,2],shuffle:[1,0]};
  function setPlayMode(mode){
    S.playMode=mode;
    S.modePendingUntil=Date.now()+6000; // 6 秒内轮询不回写，防止点击后弹回顺序
    document.querySelectorAll(".mode-ctrls").forEach(box=>{
      box.querySelectorAll("button").forEach(b=>b.classList.toggle("on",b.dataset.mode===mode));
    });
    const [sh,re]=MODE_MAP[mode]||MODE_MAP.seq;
    apiCall("setPlayMode",{ok:true},sh,re);
    const label={seq:"顺序播放",loop:"列表循环",one:"单曲循环",shuffle:"随机播放"}[mode]||mode;
    toast("播放模式："+label);
  }
  document.querySelectorAll(".mode-ctrls").forEach(box=>box.addEventListener("click",e=>{
    const b=e.target.closest("button[data-mode]"); if(b)setPlayMode(b.dataset.mode);
  }));

  // ---- 音量 ----
  function bindVol(id){
    const el=$(id); if(!el)return;
    el.addEventListener("input",e=>{ S.volume=Number(e.target.value);
      document.querySelectorAll('input[type="range"][id$="VolSlider"],#volSlider').forEach(x=>x.value=S.volume); });
    el.addEventListener("change",e=>apiCall("setVolume",{ok:true},Number(e.target.value)));
  }
  bindVol("volSlider"); bindVol("pVolSlider");

  // ---- LMS 连接状态徽标（顶部实时显示）----
  async function updateConnBadge(){
    const el=$("connText"); if(!el)return;
    const r=await apiCall("getConnection",{connected:true,state:"online",label:"已连接"});
    if(!r)return;
    el.textContent=r.label||"未连接";
    el.className="brand-sub conn-badge "+(r.state||"offline");
    el.title=r.error||r.url||"";
  }

  // ---- 真实状态轮询 ----
  async function pollStatus(){
    const st=await apiCall("getStatus",null);
    if(!st || st.ok===false || !st.track) return;
    const t=st.track;
    const curId=String(t.id||t.track_id||"");
    if(curId && String(S.track&&S.track.id)!==curId){
      S.track={ id:curId, title:t.title||"", artist:t.artist||"", album:t.album||"",
        coverid:t.artwork_track_id||t.coverid||"", duration:Number(t.duration)||0 };
      for(const k of ("url","type","samplerate","samplesize","bitrate","filesize")){
        if(t[k]!==undefined) S.track[k]=t[k];
      }
      S.cover=window.__COVER__||null;
      S.coverTrackId = S.cover ? curId : "";
      S.duration=S.track.duration||346;
      applyTrackToAll();
      refreshPlaylistPanel();     // 切歌后只刷新一次，避免双重写 DOM 跳闪
      setMiniFolded(S.miniFolded); // 换曲保持当前溃缩/展开状态
      loadTrackExtras(S.track);   // 主动刷新封面/音频/歌词，不再依赖 init 那一次
      if($("libPlDrawer") && !$("libPlDrawer").hidden && S.lpdPid) refreshLpd();
    }
    S.playing = (st.mode==="play");
    if(Number(st.time)>0 && Date.now()>=(S.seekingUntil||0)) S.time=Number(st.time);
    if(Number(st.duration)>0) S.duration=Number(st.duration);
    S.volume=Number(st.volume!==undefined?st.volume:S.volume);
    document.querySelectorAll('#volSlider,#pVolSlider').forEach(x=>x.value=S.volume);
    // 播放模式回显：LMS "playlist mode" = "shuffle repeat"
    // 播放模式回显：用户刚点过（乐观锁窗口内）时跳过，避免弹回顺序播放
    if(Date.now()>=S.modePendingUntil){
      const pm=String(st.playlist_mode||"0 0").trim().split(/\s+/);
      const sh=Number(pm[0]||0), rp=Number(pm[1]||0);
      let mode="seq";
      if(rp===2)mode="one"; else if(rp===1)mode="loop"; else if(sh>=1)mode="shuffle";
      if(mode!==S.playMode){ S.playMode=mode;
        document.querySelectorAll(".mode-ctrls").forEach(box=>box.querySelectorAll("button").forEach(b=>b.classList.toggle("on",b.dataset.mode===mode))); }
    }
    updateTimeUI();
    loadQueue();
    pollStatus._n=(pollStatus._n||0)+1;
    if(pollStatus._n%5===1) updateConnBadge();
  }

  /* ---------- 初始化 ---------- */
  async function init(){
    for(let i=0;i<30 && !api.getMeta;i++){ await new Promise(r=>setTimeout(r,100));
      api=(window.pywebview&&window.pywebview.api)||window.api||{}; }
    if(api.getMeta){
      try{ const meta=await api.getMeta(); $("footVer").textContent="Sonora 颂诺 · Web v2.0.0 / Core v"+meta.version;
        $("helpMeta").textContent="Sonora 颂诺 · 核心逻辑 v"+meta.version+" · pywebview 渲染层 v0.2.0"; }catch(e){}
    }
    // 载入数据：优先 bridge，其次注入的快照
    try{
      if(api.getLibrary) S.library=await api.getLibrary();
      else if(window.__LIB__) S.library=window.__LIB__;
    }catch(e){ S.library=window.__LIB__||null; }
    if(!S.library && window.__LIB__) S.library=window.__LIB__;
    if(window.__AUDIO__) S.audio=window.__AUDIO__;
    if(window.__LYRICS__) S.lyrics=window.__LYRICS__;
    // 真实环境：先确定当前曲目（getStatus），再取音频/歌词，避免用空 track 取到"未知格式/暂无歌词"
    if(api.getStatus){
      try{ const st=await api.getStatus();
        if(st&&st.track&&st.track.id){
          S.track=st.track;
          S.duration=Number(st.track.duration)||346;
        }
      }catch(e){}
    }
    if(api.getBio){ try{ S.bio=await api.getBio("大黒摩季","55 RED");}catch(e){} }
    if(window.__BIO__) S.bio=window.__BIO__;

    applyTheme((api.getConfig&&await api.getConfig().then(c=>c.theme).catch(()=>"dark"))||"dark");
    // 默认曲目（验证数据）
    if(window.__TRACK__){ S.track=window.__TRACK__; S.cover=window.__COVER__||null; S.coverTrackId=S.cover?String(S.track.id||""):"";
      S.duration=S.track.duration||346; }
    applyTrackToAll();
    if(S.track && (S.track.id||S.track.title)) loadTrackExtras(S.track);
    // 主页打开后默认进入音乐库；已有曲目在播放 → 显示 mini 播放器
    renderLibrary();
    goto("lib");
    $("miniPlayer").hidden = false;
    setInterval(()=>{ if(S.playing){ S.time+=1; if(S.time>S.duration)S.time=0; updateTimeUI(); } },1000);
    // 增强功能初始化
    loadPlaylists(); loadQueue(); loadFavorites();
    setTimeout(pollStatus, 300);
    setTimeout(updateConnBadge, 500);
    setInterval(pollStatus, 1000);
    initSeekBars();
  }
  window.addEventListener("DOMContentLoaded",init);
})();
