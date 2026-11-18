import re, sys, json
VOID={'img','br','meta','link','hr','input'}
TAG=re.compile(r'<(/?)([a-zA-Z0-9]+)\b[^>]*?(/?)>')
def top_blocks(s):
    """s 안의 최상위 요소들의 (start,end,tag,html) 목록"""
    out=[];depth=0;start=None;tag0=None
    for m in TAG.finditer(s):
        close,tag,selfc=m.group(1),m.group(2).lower(),m.group(3)
        if tag in VOID or selfc:
            if depth==0: out.append((m.start(),m.end(),tag,s[m.start():m.end()]))
            continue
        if not close:
            if depth==0: start=m.start();tag0=tag
            depth+=1
        else:
            depth-=1
            if depth==0: out.append((start,m.end(),tag0,s[start:m.end()]))
    return out
def text(h): return re.sub(r'\s+','',re.sub(r'<[^>]+>','',h))
def sections(html):
    return [(m.group(1),m.group(2)) for m in re.finditer(r'<section class="slide" id="([^"]+)">(.*?)</section>',html,re.S)]
if __name__=='__main__':
    html=open(sys.argv[1],encoding='utf-8').read()
    for sid,body in sections(html):
        print('==',sid)
        for i,(a,b,t,h) in enumerate(top_blocks(body)):
            cls=re.match(r'<[a-z0-9]+(?:\s+class="([^"]*)")?',h).group(1) or ''
            print(f'  {i:2} {t:7} {cls:14} {len(text(h)):5}  {text(h)[:40]}')
