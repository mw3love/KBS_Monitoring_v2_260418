// 발표 화면: 쪽 하나씩 보여 주고, 창 크기에 맞춰 1920×1080을 비율 그대로 키우거나 줄인다.
const stage=document.getElementById('stage');
const pages=[...document.querySelectorAll('#deck .page.main')];
let cur=0;
function scaleStage(){ const s=Math.min(innerWidth/1920, innerHeight/1080); stage.style.transform=`scale(${s})`; }
// 안전장치: 이 PC 글꼴이 달라 글이 넘치면 그 쪽 글만 조금 줄인다(쪽 수는 그대로).
function guard(pg){
  const c=pg.querySelector('.content'); if(!c || pg.dataset.fitted) return;
  let z=1;
  for(let i=0;i<6 && c.scrollHeight>c.clientHeight+1;i++){ z*=Math.max(.85,(c.clientHeight/c.scrollHeight))*.995; c.style.zoom=z; }
  pg.dataset.fitted='1';
  if(z<1) console.warn('[deck] '+pg.id+' 글 넘침 → '+Math.round(z*100)+'%로 줄임');
}
function show(i){
  cur=Math.max(0,Math.min(pages.length-1,i));
  pages.forEach((p,k)=>p.classList.toggle('on',k===cur));
  guard(pages[cur]);
  try{ history.replaceState(null,'','#p'+(cur+1)); }catch(e){}
}
document.addEventListener('keydown',e=>{
  if(e.altKey||e.ctrlKey||e.metaKey) return;
  const k=e.key;
  if(k==='ArrowRight'||k==='PageDown'||k===' '||k==='Enter'){ e.preventDefault(); show(cur+1); }
  else if(k==='ArrowLeft'||k==='PageUp'||k==='Backspace'){ e.preventDefault(); show(cur-1); }
  else if(k==='Home'){ e.preventDefault(); show(0); }
  else if(k==='End'){ e.preventDefault(); show(pages.length-1); }
  else if(k==='f'||k==='F'){ try{ document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen(); }catch(err){} }
});
addEventListener('resize',scaleStage);
scaleStage();
const m=location.hash.match(/^#p(\d+)$/);
show(m?parseInt(m[1],10)-1:0);
// 웹 글꼴이 늦게 들어오면 현재 쪽을 다시 잰다
try{ document.fonts.ready.then(()=>{ pages.forEach(p=>{ delete p.dataset.fitted; const c=p.querySelector('.content'); if(c) c.style.zoom=''; }); guard(pages[cur]); }); }catch(e){}
pages.forEach((p,i)=>{ const n=p.querySelector('.n'); if(n) n.textContent=(i+1)+' / '+pages.length; });
pages[0].querySelector('.hint').textContent='→ 다음 · ← 이전 · F 전체화면';
