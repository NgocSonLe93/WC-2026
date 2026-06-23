"use strict";
const DATA_URL = "data/worldcup.json";
const CONFIG = window.WC2026_CONFIG || {};
const LIVE_API_URL = String(CONFIG.liveApiUrl || "").trim().replace(/\/$/, "");
const LIVE_INTERVAL_MS = Math.max(15000, Number(CONFIG.liveIntervalMs) || 30000);
const IDLE_INTERVAL_MS = Math.max(60000, Number(CONFIG.idleIntervalMs) || 300000);
const CACHE_KEY = "wc2026_ngocsonle_cache_v6";

const FIFA_RANKING_DATE = "11/06/2026";
const FIFA_RATINGS = Object.freeze({
  ARG:{rank:1,points:1877.27}, ESP:{rank:2,points:1874.71}, FRA:{rank:3,points:1870.70}, ENG:{rank:4,points:1828.02},
  POR:{rank:5,points:1767.85}, BRA:{rank:6,points:1765.86}, MAR:{rank:7,points:1755.10}, NED:{rank:8,points:1753.57},
  BEL:{rank:9,points:1742.24}, GER:{rank:10,points:1735.77}, CRO:{rank:11,points:1714.87}, COL:{rank:13,points:1698.35},
  MEX:{rank:14,points:1687.48}, SEN:{rank:15,points:1684.07}, URU:{rank:16,points:1673.07}, USA:{rank:17,points:1671.23},
  JPN:{rank:18,points:1661.58}, SUI:{rank:19,points:1650.06}, IRN:{rank:20,points:1619.58}, TUR:{rank:22,points:1605.73},
  ECU:{rank:23,points:1598.52}, AUT:{rank:24,points:1597.40}, KOR:{rank:25,points:1591.63}, AUS:{rank:27,points:1579.34},
  ALG:{rank:28,points:1571.03}, EGY:{rank:29,points:1562.37}, CAN:{rank:30,points:1559.48}, NOR:{rank:31,points:1557.44},
  CIV:{rank:33,points:1540.87}, PAN:{rank:34,points:1539.16}, SWE:{rank:38,points:1509.79}, CZE:{rank:40,points:1505.74},
  PAR:{rank:41,points:1505.35}, SCO:{rank:42,points:1503.34}, TUN:{rank:45,points:1476.41}, COD:{rank:46,points:1474.43},
  UZB:{rank:50,points:1458.73}, QAT:{rank:56,points:1450.31}, IRQ:{rank:57,points:1446.28}, RSA:{rank:60,points:1428.38},
  KSA:{rank:61,points:1423.88}, JOR:{rank:63,points:1387.74}, BIH:{rank:64,points:1387.22}, CPV:{rank:67,points:1371.11},
  GHA:{rank:73,points:1346.88}, CUW:{rank:82,points:1294.77}, HAI:{rank:83,points:1293.10}, NZL:{rank:85,points:1275.58}
});
const FIFA_CODE_ALIASES = Object.freeze({IRI:"IRN", DZA:"ALG", HTI:"HAI", KOR:"KOR", DRK:"COD", DRC:"COD"});

const state = { data: null, selectedDate: "", filter: "all", chartPoints: [], refreshTimer: null, countdownTimer: null, nextRefreshAt: 0, refreshing: false };
const $ = id => document.getElementById(id);
const el = {
  refreshBtn: $("refreshBtn"), importBtn: $("importBtn"), exportBtn: $("exportBtn"), statusPill: $("statusPill"), updatedAt: $("updatedAt"), liveRefreshInfo: $("liveRefreshInfo"),
  heroMatches: $("heroMatches"), dayMatches: $("dayMatches"), dayScored: $("dayScored"), dayGoals: $("dayGoals"), dayAverage: $("dayAverage"), dayShare: $("dayShare"),
  selectedDateTitle: $("selectedDateTitle"), selectedDateBadge: $("selectedDateBadge"), prevDate: $("prevDate"), nextDate: $("nextDate"), dateSelect: $("dateSelect"), statusFilter: $("statusFilter"), matchesList: $("matchesList"),
  thirdPlaceBody: $("thirdPlaceBody"), standingsGrid: $("standingsGrid"), totalPlayed: $("totalPlayed"), totalGoals: $("totalGoals"), overallAverage: $("overallAverage"), bestDayGoals: $("bestDayGoals"), bestDayLabel: $("bestDayLabel"),
  goalsChart: $("goalsChart"), dailyStatsBody: $("dailyStatsBody"), analysisList: $("analysisList"), analysisUpcoming: $("analysisUpcoming"), analysisPlayed: $("analysisPlayed"), importModal: $("importModal"), closeModal: $("closeModal"), jsonFile: $("jsonFile"), loadJsonBtn: $("loadJsonBtn"), toast: $("toast")
};
const collator = new Intl.Collator("en", { sensitivity: "base" });
function esc(v){return String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));}
function num(v, fallback=0){const n=Number(v);return Number.isFinite(n)?n:fallback;}
function showToast(msg){el.toast.textContent=msg;el.toast.classList.add("show");clearTimeout(showToast.t);showToast.t=setTimeout(()=>el.toast.classList.remove("show"),2600);}
function setStatus(type,text){el.statusPill.className=`status-pill ${type}`;el.statusPill.innerHTML=`<span></span>${esc(text)}`;}
function flagEmoji(iso2){const c=String(iso2||"").toUpperCase();if(c==="SCO")return "🏴";if(c==="ENG")return "🏴";if(!/^[A-Z]{2}$/.test(c)||c==="TBD")return "🏳️";return [...c].map(x=>String.fromCodePoint(127397+x.charCodeAt())).join("");}
function flagUrl(iso2, code=""){const c=String(iso2||"").trim().toLowerCase();const alt=String(code||iso2||"").trim().toUpperCase();if(alt==="SCO"||alt==="SCT")return "assets/flags/scotland.svg";if(alt==="ENG")return "assets/flags/england.svg";if(c && /^[a-z]{2}$/.test(c) && c!=="tbd")return `https://flagcdn.com/w80/${c}.png`;return "";}
function flagHtml(iso2, code, name){const url=flagUrl(iso2, code);const label=`Cờ ${name||"đội tuyển"}`;return url?`<span class="flag-badge"><img class="flag-img" src="${url}" alt="${esc(label)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentElement.classList.add('fallback');this.outerHTML='${flagEmoji(iso2).replace("'","&#39;")}'"></span>`:`<span class="flag-emoji">${flagEmoji(iso2)}</span>`;}
function formatDate(key,long=true){if(!key)return "—";const [y,m,d]=key.split("-").map(Number);const dt=new Date(y,m-1,d);return new Intl.DateTimeFormat("vi-VN",long?{weekday:"long",day:"2-digit",month:"2-digit",year:"numeric"}:{day:"2-digit",month:"2-digit"}).format(dt);}
function isScored(m){return ["finished","live"].includes(m.status)&&Number.isFinite(Number(m.score?.home))&&Number.isFinite(Number(m.score?.away));}
function scoredMatches(){return state.data.matches.filter(isScored);}
function allDates(){return [...new Set(state.data.matches.map(m=>m.date_vn).filter(Boolean))].sort();}
function chooseDate(dates){const today=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Ho_Chi_Minh",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());if(dates.includes(today))return today;const completed=dates.filter(d=>state.data.matches.some(m=>m.date_vn===d&&isScored(m)));if(completed.length)return completed.at(-1);return dates.find(d=>d>=today)||dates.at(-1)||"";}
function normalizeData(raw){const data=raw&&typeof raw==="object"?raw:{};data.meta=data.meta||{};data.teams=Array.isArray(data.teams)?data.teams:[];data.matches=Array.isArray(data.matches)?data.matches:[];data.matches=data.matches.map((m,i)=>({id:String(m.id??i+1),stage:m.stage||"group",group:String(m.group||"").toUpperCase(),matchday:num(m.matchday),kickoff_utc:m.kickoff_utc||"",date_vn:m.date_vn||"",time_vn:m.time_vn||"",status:["finished","live","upcoming"].includes(m.status)?m.status:"upcoming",elapsed:m.elapsed||"",home:{id:String(m.home?.id??""),name:m.home?.name||"Chưa xác định",code:m.home?.code||"",iso2:m.home?.iso2||""},away:{id:String(m.away?.id??""),name:m.away?.name||"Chưa xác định",code:m.away?.code||"",iso2:m.away?.iso2||""},score:{home:m.score?.home===null||m.score?.home===undefined?null:num(m.score.home),away:m.score?.away===null||m.score?.away===undefined?null:num(m.score.away)},venue:m.venue||""}));return data;}
function saveCache(){try{localStorage.setItem(CACHE_KEY,JSON.stringify(state.data));}catch(e){console.warn(e);}}
function loadCache(){try{const raw=localStorage.getItem(CACHE_KEY);if(!raw)return false;state.data=normalizeData(JSON.parse(raw));return state.data.matches.length>0;}catch{return false;}}
function liveConfigured(){return /^https:\/\//i.test(LIVE_API_URL)&&!LIVE_API_URL.includes("PASTE_CLOUDFLARE");}
async function fetchJson(url,timeout=15000){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeout);try{const res=await fetch(`${url}${url.includes("?")?"&":"?"}v=${Date.now()}`,{cache:"no-store",signal:controller.signal});if(!res.ok)throw new Error(`HTTP ${res.status}`);return await res.json();}finally{clearTimeout(timer);}}
function hasLiveMatch(){return !!state.data?.matches?.some(m=>m.status==="live");}
function hasNearMatch(){const now=Date.now();return !!state.data?.matches?.some(m=>{const t=Date.parse(m.kickoff_utc||"");return Number.isFinite(t)&&t-now>=-4*60*60*1000&&t-now<=30*60*1000;});}
function nextInterval(){return hasLiveMatch()||hasNearMatch()?LIVE_INTERVAL_MS:IDLE_INTERVAL_MS;}
function stopRefreshTimers(){clearTimeout(state.refreshTimer);clearInterval(state.countdownTimer);state.refreshTimer=null;state.countdownTimer=null;state.nextRefreshAt=0;}
function updateRefreshInfo(){if(!el.liveRefreshInfo)return;if(!liveConfigured()){el.liveRefreshInfo.textContent="Chế độ dự phòng: dữ liệu GitHub";return;}if(document.hidden){el.liveRefreshInfo.textContent="Tạm dừng khi tab ẩn";return;}const left=Math.max(0,Math.ceil((state.nextRefreshAt-Date.now())/1000));const mode=hasLiveMatch()||hasNearMatch()?"LIVE":"Tự động";el.liveRefreshInfo.textContent=state.refreshing?"Đang đồng bộ trực tiếp…":`${mode} · cập nhật sau ${left}s`;}
function scheduleRefresh(delay=nextInterval()){stopRefreshTimers();if(!liveConfigured()||document.hidden)return;state.nextRefreshAt=Date.now()+delay;updateRefreshInfo();state.countdownTimer=setInterval(updateRefreshInfo,1000);state.refreshTimer=setTimeout(()=>refreshLive({silent:true}),delay);}
async function loadStaticData({resetDate=true}={}){const data=normalizeData(await fetchJson(DATA_URL));if(!data.matches.length)throw new Error("File dữ liệu chưa có trận đấu");state.data=data;saveCache();renderAll(resetDate);return data;}
async function refreshLive({manual=false,silent=false}={}){if(!liveConfigured()){if(manual)showToast("Chưa cấu hình Cloudflare Worker cho chế độ trực tiếp");scheduleRefresh();return false;}if(state.refreshing)return false;state.refreshing=true;el.refreshBtn.disabled=true;if(!silent)setStatus("loading","Đang đồng bộ trực tiếp");updateRefreshInfo();try{const data=normalizeData(await fetchJson(LIVE_API_URL,15000));if(!data.matches.length)throw new Error("API trực tiếp không có trận đấu");const reset=!state.data;state.data=data;saveCache();renderAll(reset);setStatus(hasLiveMatch()?"live":"ok",hasLiveMatch()?"LIVE · tỷ số đang cập nhật":`Trực tiếp · ${data.matches.length} trận`);if(manual)showToast("Đã cập nhật dữ liệu trực tiếp");return true;}catch(err){console.error("Realtime refresh failed",err);if(state.data){setStatus("warning","Mất kết nối LIVE · đang giữ dữ liệu gần nhất");if(manual)showToast("Chưa kết nối được máy chủ trực tiếp");}else{setStatus("error","Không đọc được dữ liệu trực tiếp");renderEmpty();}return false;}finally{state.refreshing=false;el.refreshBtn.disabled=false;scheduleRefresh();}}
async function loadData({manual=false}={}){if(manual&&liveConfigured())return refreshLive({manual:true});el.refreshBtn.disabled=true;setStatus("loading","Đang mở dữ liệu");let loaded=false;try{await loadStaticData({resetDate:true});loaded=true;setStatus("ok",`Đã tải ${state.data.matches.length} trận dự phòng`);}catch(err){console.error("Static load failed",err);if(loadCache()){renderAll(true);loaded=true;setStatus("warning","Đang dùng dữ liệu đã lưu trên thiết bị");}else{renderEmpty();setStatus("error","Không đọc được dữ liệu");}}finally{el.refreshBtn.disabled=false;}if(liveConfigured()){await refreshLive({manual:false,silent:loaded});}else{if(loaded)setStatus("warning","Chưa bật chế độ cập nhật trực tiếp");updateRefreshInfo();}}
function renderAll(resetDate=false){if(!state.data)return;const dates=allDates();if(resetDate||!dates.includes(state.selectedDate))state.selectedDate=chooseDate(dates);renderDateControl(dates);renderResults();renderStandings();renderGoals();renderAnalysis();renderMeta();}
function renderMeta(){const meta=state.data.meta||{};const d=meta.updated_at?new Date(meta.updated_at):null;el.updatedAt.textContent=d&&!Number.isNaN(d.getTime())?`${meta.source||"Dữ liệu website"} • ${new Intl.DateTimeFormat("vi-VN",{dateStyle:"short",timeStyle:"medium",timeZone:"Asia/Ho_Chi_Minh"}).format(d)}`:(meta.source||"Chưa cập nhật");el.heroMatches.textContent=scoredMatches().length;updateRefreshInfo();}
function renderDateControl(dates){el.dateSelect.innerHTML=dates.map(d=>`<option value="${d}" ${d===state.selectedDate?"selected":""}>${esc(formatDate(d))}</option>`).join("");const idx=dates.indexOf(state.selectedDate);el.prevDate.disabled=idx<=0;el.nextDate.disabled=idx<0||idx>=dates.length-1;}
function dailySummary(date){const matches=state.data.matches.filter(m=>m.date_vn===date);const scored=matches.filter(isScored);const goals=scored.reduce((s,m)=>s+num(m.score.home)+num(m.score.away),0);const scoring=scored.filter(m=>num(m.score.home)+num(m.score.away)>0).length;return{date,matches,scored,goals,scoring,avg:scored.length?goals/scored.length:0};}
function overallSummary(){const scored=scoredMatches();const goals=scored.reduce((s,m)=>s+num(m.score.home)+num(m.score.away),0);return{scored,goals,avg:scored.length?goals/scored.length:0};}
function stageText(m){if(m.stage==="group")return m.group?`Bảng ${m.group}`:"Vòng bảng";const map={r32:"Vòng 32 đội",r16:"Vòng 16 đội",qf:"Tứ kết",sf:"Bán kết",third:"Tranh hạng ba",final:"Chung kết"};return map[m.stage]||m.stage||"World Cup";}
function statusText(m){if(m.status==="finished")return "Kết thúc";if(m.status==="live")return m.elapsed||"Đang đấu";return "Sắp đấu";}
function renderResults(){const sum=dailySummary(state.selectedDate);const overall=overallSummary();el.dayMatches.textContent=sum.matches.length;el.dayScored.textContent=`${sum.scored.length} trận có tỷ số`;el.dayGoals.textContent=sum.goals;el.dayAverage.textContent=sum.avg.toFixed(2);el.dayShare.textContent=`${overall.goals?(sum.goals/overall.goals*100).toFixed(1):"0.0"}%`;el.selectedDateTitle.textContent=formatDate(state.selectedDate);el.selectedDateBadge.textContent=formatDate(state.selectedDate,false);const list=sum.matches.filter(m=>state.filter==="all"||m.status===state.filter).sort((a,b)=>(a.time_vn||"99:99").localeCompare(b.time_vn||"99:99"));if(!list.length){el.matchesList.innerHTML='<div class="empty-state">Không có trận phù hợp với bộ lọc trong ngày này.</div>';return;}el.matchesList.innerHTML=list.map(m=>{const score=isScored(m)?`<div class="score">${num(m.score.home)} – ${num(m.score.away)}</div>`:`<div class="score upcoming">${esc(m.time_vn||"Chờ giờ")}</div>`;return`<article class="match-card ${m.status}"><div class="team"><span class="team-crest">${flagHtml(m.home.iso2,m.home.code,m.home.name)}</span><span class="team-name">${esc(m.home.name)}</span></div><div class="score-block">${score}<div class="match-meta">${esc(stageText(m))}${m.venue?` · ${esc(m.venue)}`:""}</div><span class="match-status ${m.status}">${esc(statusText(m))}</span></div><div class="team away"><span class="team-name">${esc(m.away.name)}</span><span class="team-crest">${flagHtml(m.away.iso2,m.away.code,m.away.name)}</span></div></article>`;}).join("");}
function teamSeed(){const groups=new Map();for(const t of state.data.teams){const g=String(t.group||"").toUpperCase();if(!/^[A-L]$/.test(g))continue;if(!groups.has(g))groups.set(g,new Map());groups.get(g).set(String(t.id),{teamId:String(t.id),name:t.name,code:t.code||"",iso2:t.iso2||"",played:0,wins:0,draws:0,losses:0,gf:0,ga:0,gd:0,points:0});}for(const m of state.data.matches){if(m.stage!=="group"||!m.group)continue;if(!groups.has(m.group))groups.set(m.group,new Map());for(const side of [m.home,m.away]){if(!groups.get(m.group).has(String(side.id)))groups.get(m.group).set(String(side.id),{teamId:String(side.id),name:side.name,code:side.code||"",iso2:side.iso2||"",played:0,wins:0,draws:0,losses:0,gf:0,ga:0,gd:0,points:0});}}return groups;}
function rankSort(a,b){return b.points-a.points||b.gd-a.gd||collator.compare(a.name,b.name);}
function computeStandings(){const groups=teamSeed();for(const m of state.data.matches){if(m.stage!=="group"||!m.group||!isScored(m))continue;const g=groups.get(m.group);const h=g?.get(String(m.home.id));const a=g?.get(String(m.away.id));if(!h||!a)continue;const hs=num(m.score.home),as=num(m.score.away);h.played++;a.played++;h.gf+=hs;h.ga+=as;a.gf+=as;a.ga+=hs;if(hs>as){h.wins++;a.losses++;h.points+=3;}else if(hs<as){a.wins++;h.losses++;a.points+=3;}else{h.draws++;a.draws++;h.points++;a.points++;}}return [...groups.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([group,map])=>({group,rows:[...map.values()].map(r=>({...r,gd:r.gf-r.ga})).sort(rankSort)}));}
function rowTeam(r){return`<div class="table-team"><span class="team-crest">${flagHtml(r.iso2,r.code,r.name)}</span><span class="table-team-name">${esc(r.name)}</span></div>`;}
function renderStandings(){const groups=computeStandings();const thirds=groups.map(g=>g.rows[2]?{...g.rows[2],group:g.group}:null).filter(Boolean).sort(rankSort);el.thirdPlaceBody.innerHTML=thirds.length?thirds.map((r,i)=>`<tr class="${i<8?"qualified":""}"><td class="rank">${i+1}</td><td class="team-cell">${rowTeam(r)}<small class="group-sub">Bảng ${esc(r.group)}</small></td><td class="points">${r.points}</td><td>${r.gd>0?"+":""}${r.gd}</td></tr>`).join(""):'<tr><td colspan="4">Chưa có dữ liệu.</td></tr>';el.standingsGrid.innerHTML=groups.map(g=>`<article class="group-card glass"><h3 class="group-title">Bảng ${g.group}</h3><div class="table-scroll"><table class="rank-table"><thead><tr><th>#</th><th>Đội</th><th>TR</th><th>T</th><th>H</th><th>B</th><th>BT</th><th>BB</th><th>HS</th><th>Đ</th></tr></thead><tbody>${g.rows.map((r,i)=>`<tr class="${i<2?"qualify":i===2?"third":""}"><td class="rank">${i+1}</td><td class="team-cell">${rowTeam(r)}</td><td>${r.played}</td><td>${r.wins}</td><td>${r.draws}</td><td>${r.losses}</td><td>${r.gf}</td><td>${r.ga}</td><td>${r.gd>0?"+":""}${r.gd}</td><td class="points">${r.points}</td></tr>`).join("")}</tbody></table></div></article>`).join("");}
function renderGoals(){const overall=overallSummary();const rows=allDates().map(d=>dailySummary(d)).filter(x=>x.scored.length);el.totalPlayed.textContent=overall.scored.length;el.totalGoals.textContent=overall.goals;el.overallAverage.textContent=overall.avg.toFixed(2);const best=rows.reduce((a,b)=>!a||b.goals>a.goals?b:a,null);el.bestDayGoals.textContent=best?.goals||0;el.bestDayLabel.textContent=best?formatDate(best.date,false):"Chưa có dữ liệu";el.dailyStatsBody.innerHTML=rows.length?rows.map(r=>`<tr><td>${esc(formatDate(r.date,false))}</td><td>${r.scored.length}</td><td class="points">${r.goals}</td><td>${r.avg.toFixed(2)}</td><td>${r.scoring}/${r.scored.length}</td><td>${overall.goals?(r.goals/overall.goals*100).toFixed(1):"0.0"}%</td></tr>`).join(""):'<tr><td colspan="6">Chưa có trận có tỷ số.</td></tr>';state.chartPoints=rows;drawChart();}
function drawChart(){const canvas=el.goalsChart;if(!canvas)return;const rect=canvas.getBoundingClientRect();const dpr=Math.max(1,Math.min(2,window.devicePixelRatio||1));canvas.width=Math.max(320,rect.width*dpr);canvas.height=Math.max(240,rect.height*dpr);const ctx=canvas.getContext("2d");ctx.scale(dpr,dpr);const w=canvas.width/dpr,h=canvas.height/dpr;ctx.clearRect(0,0,w,h);const rows=state.chartPoints;if(!rows.length){ctx.fillStyle="#9bb7aa";ctx.font="14px system-ui";ctx.textAlign="center";ctx.fillText("Chưa có dữ liệu bàn thắng",w/2,h/2);return;}const pad={l:36,r:14,t:20,b:42};const max=Math.max(1,...rows.map(r=>r.goals));const gap=8;const bw=Math.max(12,(w-pad.l-pad.r-gap*(rows.length-1))/rows.length);ctx.strokeStyle="rgba(166,255,218,.12)";ctx.fillStyle="#8fb3a4";ctx.font="11px system-ui";ctx.textAlign="right";for(let i=0;i<=4;i++){const y=pad.t+(h-pad.t-pad.b)*i/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();const val=Math.round(max*(1-i/4));ctx.fillText(String(val),pad.l-7,y+4);}rows.forEach((r,i)=>{const x=pad.l+i*(bw+gap);const bh=(h-pad.t-pad.b)*(r.goals/max);const y=h-pad.b-bh;const grad=ctx.createLinearGradient(0,y,0,h-pad.b);grad.addColorStop(0,"#63efb6");grad.addColorStop(1,"#1ebf82");ctx.fillStyle=grad;roundRect(ctx,x,y,bw,bh,6);ctx.fill();if(rows.length<=18||i%2===0){ctx.save();ctx.translate(x+bw/2,h-pad.b+12);ctx.rotate(-Math.PI/5);ctx.fillStyle="#9bb7aa";ctx.font="10px system-ui";ctx.textAlign="right";ctx.fillText(formatDate(r.date,false),0,0);ctx.restore();}ctx.fillStyle="#f4fff9";ctx.font="bold 11px system-ui";ctx.textAlign="center";ctx.fillText(String(r.goals),x+bw/2,Math.max(13,y-5));});}
function roundRect(ctx,x,y,w,h,r){const rr=Math.min(r,w/2,h/2);ctx.beginPath();ctx.moveTo(x+rr,y);ctx.arcTo(x+w,y,x+w,y+h,rr);ctx.arcTo(x+w,y+h,x,y+h,rr);ctx.arcTo(x,y+h,x,y,rr);ctx.arcTo(x,y,x+w,y,rr);ctx.closePath();}

function canonicalFifaCode(team={}){
  const raw=String(team.code||"").trim().toUpperCase();
  if(FIFA_CODE_ALIASES[raw])return FIFA_CODE_ALIASES[raw];
  if(FIFA_RATINGS[raw])return raw;
  const byName={
    "SOUTH KOREA":"KOR","KOREA REPUBLIC":"KOR","IRAN":"IRN","IR IRAN":"IRN","ALGERIA":"ALG",
    "IVORY COAST":"CIV","CÔTE D'IVOIRE":"CIV","COTE D'IVOIRE":"CIV","CAPE VERDE":"CPV","CABO VERDE":"CPV",
    "DR CONGO":"COD","CONGO DR":"COD","DEMOCRATIC REPUBLIC OF THE CONGO":"COD","NEW ZEALAND":"NZL",
    "AOTEAROA NEW ZEALAND":"NZL","CURAÇAO":"CUW","CURACAO":"CUW","UNITED STATES":"USA","TURKEY":"TUR","TÜRKIYE":"TUR",
    "CZECHIA":"CZE","BOSNIA AND HERZEGOVINA":"BIH","SCOTLAND":"SCO","ENGLAND":"ENG"
  };
  return byName[String(team.name||"").trim().toUpperCase()]||raw;
}
function fifaRating(team={}){
  const code=canonicalFifaCode(team);
  return FIFA_RATINGS[code]||{rank:null,points:1400};
}
function analysisTeamKey(team={}){
  return String(team.id||canonicalFifaCode(team)||team.name||"").trim().toUpperCase();
}
function computeTeamAnalysis(){
  const map=new Map();
  const ensure=team=>{
    const key=analysisTeamKey(team);
    if(!map.has(key))map.set(key,{team:{...team},played:0,wins:0,draws:0,losses:0,gf:0,ga:0,points:0,results:[]});
    return map.get(key);
  };
  for(const t of state.data?.teams||[])ensure(t);
  const finished=(state.data?.matches||[]).filter(m=>m.status==="finished"&&isScored(m)).sort((a,b)=>String(a.kickoff_utc).localeCompare(String(b.kickoff_utc)));
  for(const m of finished){
    const h=ensure(m.home),a=ensure(m.away),hs=num(m.score.home),as=num(m.score.away);
    h.played++;a.played++;h.gf+=hs;h.ga+=as;a.gf+=as;a.ga+=hs;
    if(hs>as){h.wins++;a.losses++;h.points+=3;h.results.push("W");a.results.push("L");}
    else if(hs<as){a.wins++;h.losses++;a.points+=3;h.results.push("L");a.results.push("W");}
    else{h.draws++;a.draws++;h.points++;a.points++;h.results.push("D");a.results.push("D");}
  }
  return map;
}
function analysisStat(stats,prop){
  if(!stats||!stats.played)return "0.00";
  if(prop==="ppg")return (stats.points/stats.played).toFixed(2);
  if(prop==="gfpg")return (stats.gf/stats.played).toFixed(2);
  if(prop==="gapg")return (stats.ga/stats.played).toFixed(2);
  return "0.00";
}
function formHtml(stats){
  const rows=(stats?.results||[]).slice(-5);
  if(!rows.length)return '<span class="form-empty">Chưa đá</span>';
  return `<span class="form-strip">${rows.map(x=>`<i class="form-${x.toLowerCase()}">${x}</i>`).join("")}</span>`;
}
function comparisonBar(homeValue,awayValue,invert=false){
  const h=Math.max(0,num(homeValue)),a=Math.max(0,num(awayValue));
  const total=h+a||1;
  let hp=h/total*100,ap=a/total*100;
  if(invert){hp=a/total*100;ap=h/total*100;}
  return `<div class="compare-track"><span class="compare-home" style="width:${hp.toFixed(1)}%"></span><span class="compare-away" style="width:${ap.toFixed(1)}%"></span></div>`;
}
function renderAnalysis(){
  if(!el.analysisList||!state.data)return;
  const stats=computeTeamAnalysis();
  const upcoming=(state.data.matches||[]).filter(m=>m.status==="upcoming").sort((a,b)=>String(a.kickoff_utc).localeCompare(String(b.kickoff_utc))).slice(0,8);
  const played=(state.data.matches||[]).filter(m=>m.status==="finished"&&isScored(m)).length;
  el.analysisUpcoming.textContent=upcoming.length;
  el.analysisPlayed.textContent=played;
  if(!upcoming.length){el.analysisList.innerHTML='<div class="empty-state">Hiện chưa có trận sắp tới trong dữ liệu.</div>';return;}
  el.analysisList.innerHTML=upcoming.map(m=>{
    const hs=stats.get(analysisTeamKey(m.home))||{played:0,wins:0,draws:0,losses:0,gf:0,ga:0,points:0,results:[]};
    const as=stats.get(analysisTeamKey(m.away))||{played:0,wins:0,draws:0,losses:0,gf:0,ga:0,points:0,results:[]};
    const hr=fifaRating(m.home),ar=fifaRating(m.away);
    const hrank=hr.rank?`#${hr.rank}`:"—",arank=ar.rank?`#${ar.rank}`:"—";
    const kickoff=`${formatDate(m.date_vn,false)} · ${esc(m.time_vn||"Chờ giờ")}`;
    return `<article class="analysis-card glass">
      <div class="analysis-card-head"><span>${esc(stageText(m))}</span><b>${kickoff}</b></div>
      <div class="analysis-teams">
        <div class="analysis-team home">${flagHtml(m.home.iso2,m.home.code,m.home.name)}<strong>${esc(m.home.name)}</strong><small>FIFA ${hrank} · ${hr.points.toFixed(2)} điểm</small>${formHtml(hs)}</div>
        <div class="analysis-vs">VS</div>
        <div class="analysis-team away">${flagHtml(m.away.iso2,m.away.code,m.away.name)}<strong>${esc(m.away.name)}</strong><small>FIFA ${arank} · ${ar.points.toFixed(2)} điểm</small>${formHtml(as)}</div>
      </div>
      <div class="comparison-table">
        <div class="comparison-row"><b>${analysisStat(hs,"ppg")}</b><span>Điểm/trận${comparisonBar(analysisStat(hs,"ppg"),analysisStat(as,"ppg"))}</span><b>${analysisStat(as,"ppg")}</b></div>
        <div class="comparison-row"><b>${analysisStat(hs,"gfpg")}</b><span>BT/trận${comparisonBar(analysisStat(hs,"gfpg"),analysisStat(as,"gfpg"))}</span><b>${analysisStat(as,"gfpg")}</b></div>
        <div class="comparison-row"><b>${analysisStat(hs,"gapg")}</b><span>BB/trận${comparisonBar(analysisStat(hs,"gapg"),analysisStat(as,"gapg"),true)}</span><b>${analysisStat(as,"gapg")}</b></div>
        <div class="comparison-row"><b>${hs.gf}-${hs.ga}</b><span>Bàn thắng – bàn thua</span><b>${as.gf}-${as.ga}</b></div>
        <div class="comparison-row"><b>${hs.wins}-${hs.draws}-${hs.losses}</b><span>Thắng – hòa – thua</span><b>${as.wins}-${as.draws}-${as.losses}</b></div>
      </div>
      <div class="analysis-source">FIFA Ranking ${FIFA_RANKING_DATE} · Dữ liệu World Cup cập nhật theo website</div>
    </article>`;
  }).join("");
}

function renderEmpty(){el.matchesList.innerHTML='<div class="empty-state">Chưa có dữ liệu. Hãy chạy workflow GitHub Actions hoặc nhập file JSON.</div>';el.standingsGrid.innerHTML="";el.thirdPlaceBody.innerHTML='<tr><td colspan="4">Chưa có dữ liệu.</td></tr>';}
function exportData(){if(!state.data)return;const blob=new Blob([JSON.stringify(state.data,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`worldcup-2026-${new Date().toISOString().slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function openModal(){el.importModal.hidden=false;}
function closeModal(){el.importModal.hidden=true;el.jsonFile.value="";}
async function importJson(){const file=el.jsonFile.files?.[0];if(!file){showToast("Hãy chọn một file JSON");return;}try{const data=normalizeData(JSON.parse(await file.text()));if(!data.matches.length)throw new Error("Không có trận đấu");state.data=data;saveCache();renderAll(true);setStatus("ok","Đang dùng dữ liệu JSON đã nhập");closeModal();showToast("Đã nạp dữ liệu thành công");}catch(e){console.error(e);showToast("File JSON không hợp lệ");}}
document.querySelectorAll(".tab").forEach(btn=>btn.addEventListener("click",()=>{document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("active",x===btn));document.querySelectorAll(".tab-panel").forEach(p=>p.classList.toggle("active",p.id===btn.dataset.tab));if(btn.dataset.tab==="goals")requestAnimationFrame(drawChart);if(btn.dataset.tab==="analysis")renderAnalysis();}));
el.refreshBtn.addEventListener("click",()=>loadData({manual:true}));el.importBtn.addEventListener("click",openModal);el.exportBtn.addEventListener("click",exportData);el.closeModal.addEventListener("click",closeModal);el.importModal.addEventListener("click",e=>{if(e.target===el.importModal)closeModal();});el.loadJsonBtn.addEventListener("click",importJson);el.dateSelect.addEventListener("change",e=>{state.selectedDate=e.target.value;renderAll();});el.statusFilter.addEventListener("change",e=>{state.filter=e.target.value;renderResults();});el.prevDate.addEventListener("click",()=>{const d=allDates(),i=d.indexOf(state.selectedDate);if(i>0){state.selectedDate=d[i-1];renderAll();}});el.nextDate.addEventListener("click",()=>{const d=allDates(),i=d.indexOf(state.selectedDate);if(i>=0&&i<d.length-1){state.selectedDate=d[i+1];renderAll();}});window.addEventListener("resize",()=>{clearTimeout(window.__chartTimer);window.__chartTimer=setTimeout(drawChart,120);});
document.addEventListener("visibilitychange",()=>{if(document.hidden){stopRefreshTimers();updateRefreshInfo();}else if(liveConfigured()){refreshLive({silent:true});}});
window.addEventListener("online",()=>{if(liveConfigured())refreshLive({silent:true});});
window.addEventListener("offline",()=>{stopRefreshTimers();setStatus("warning","Thiết bị đang ngoại tuyến");updateRefreshInfo();});
loadData();
