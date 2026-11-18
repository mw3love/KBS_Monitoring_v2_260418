import re,subprocess,sys,pathlib
H=pathlib.Path(__file__).parent; EDGE=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
src=(H.parent/'KBS_발표_본쪽.html').read_text(encoding='utf-8')
JS=r"""<script>(async()=>{await new Promise(r=>setTimeout(r,1500));try{await document.fonts.ready}catch(e){}
const ps=[...document.querySelectorAll('#deck .page.main')];const bad=[];
ps.forEach(p=>{ps.forEach(q=>q.classList.toggle('on',q===p));const c=p.querySelector('.content');let bb=c.getBoundingClientRect().top;[...c.querySelectorAll('*')].forEach(x=>bb=Math.max(bb,x.getBoundingClientRect().bottom));const d=Math.round(bb-c.getBoundingClientRect().bottom);
const imgs=[...p.querySelectorAll('.fig img')].filter(i=>{const r=i.getBoundingClientRect(),b=p.querySelector('.pb').getBoundingClientRect();return r.bottom>b.bottom+1||r.right>b.right+1});
if(d>1||imgs.length)bad.push((p.dataset.ch)+' 넘침'+d+'px'+(imgs.length?' 그림넘침':''));});
const fill=ps.map(p=>{ps.forEach(q=>q.classList.toggle('on',q===p));const c=p.querySelector('.content');let h=0;[...c.children].forEach(x=>h=Math.max(h,x.getBoundingClientRect().bottom-c.getBoundingClientRect().top));return (p.dataset.ch)+':'+Math.round(100*h/c.clientHeight)+'%'});
const pre=document.createElement('pre');pre.id='chk';pre.textContent=(bad.length?bad.join('\n'):'넘침 없음')+'\n채움 '+fill.join(' ');document.body.appendChild(pre);})()</script></body>"""
for name,html in [('웹글꼴',src),('대체글꼴',re.sub(r'<link rel="stylesheet" href="https://fonts.googleapis[^>]*>','',src))]:
    p=H/'chk.html'; p.write_text(html[:html.rfind('</body>')]+JS+html[html.rfind('</body>')+7:],encoding='utf-8')
    out=subprocess.run([EDGE,'--headless=new','--disable-gpu','--virtual-time-budget=15000','--window-size=1920,1080','--dump-dom',p.resolve().as_uri()],capture_output=True,timeout=120).stdout.decode('utf-8')
    m=re.search(r'<pre id="chk">(.*?)</pre>',out,re.S); print('==',name); print(m.group(1) if m else 'no report')
