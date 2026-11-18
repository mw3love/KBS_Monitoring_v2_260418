"""발표 HTML 두 개를 원본 하나에서 만든다.

- ../KBS_발표_본쪽.html        제출·발표용. 장마다 본 쪽 1장(보조 쪽 없음)
- ../KBS_발표_본쪽+보조쪽.html  발표자용. 본 쪽 바로 뒤에 그 장의 보조 쪽(말로 풀 순서·자세한 설명·낱말·비유·질문)
원본: 원본_스크롤판.html(장마다 스크롤로 읽던 해설). 실행: python build.py → python check.py
"""
import re, sys, pathlib
from tok import top_blocks, sections

HERE = pathlib.Path(__file__).parent
FIG = {"cover": ("side", "40%"), "system": ("side", "40%"), "video": ("side", "29%"),
       "audio": ("side", "20%"), "timing": ("top", None), "heap": ("top", None),
       "bk-main": ("side", "56%"), "bk-set": ("side", "38%")}
# 본 쪽에 둘 덩어리 번호(장 안 최상위 순서, 0=머리). "5:0-2" = 목록 5의 0~1번 항목. 문자열 "<h3…" = 새 소제목
MAIN = {
 "cover": [1, 2, 5, "<h3>v1 → v2, 세 가지 차이</h3>", 10],
 "system": [2, 5, 6],
 "pipeline": [1, 3, 4, 5, 6],
 "video": [2, "<h3>블랙 — 5초 이어지면 경보, 정상 2초면 복구</h3>", 5, "<h3>스틸 — 120초 이어지면 경보</h3>", 8],
 "audio": [2, 3, 4, 6, 7],
 "timing": [2, "<h3>블랙 예시 — 켜기 5초, 끄기 정상 2초 연속 (히스테리시스: 켜고 끄는 조건을 다르게 둠)</h3>", 5, 7, 9],
 "arch": [1, 2, 3, 4, "5:0-2"],
 "incidents": [1, 2, 3, 5, 6, 7, 9, 10, 11, 13],
 "heap": [2, 4, 6],
 "results": [1, 3],
 "ap-rec": [1, 2, 3, 4],
 "bk-main": "all", "bk-set": "all",
}
# 본 쪽 핵심 용어에 붙이는 한 마디 뜻(본 쪽에만 적용)
GLOSS = {
 "cover": [("세 프로그램(UI·Detection·Watchdog)", "세 프로그램(UI 화면·Detection 감시·Watchdog 감시견)")],
 "system": [("SDI 케이블", "SDI 케이블(방송용 영상 케이블)"),
            ("<b>V1</b>은", "<b>V1</b>(영상 감지영역)은"), ("<b>A1</b>은", "<b>A1</b>(레벨미터 감지영역)은")],
 "pipeline": [("공유 메모리에 쓴다", "공유 메모리(두 프로그램이 함께 보는 메모리 칸)에 쓴다")],
 "video": [],
 "audio": [("BGR에서 HSV로", "BGR에서 HSV(색을 색상·채도·밝기로 나눈 표현)로"),
           ("RMS로 크기를", "RMS(소리 크기의 평균값)로 크기를"),
           ("로 dBFS로 바꾼다", "로 dBFS(디지털 소리 크기 단위, 0이 최대)로 바꾼다")],
 "timing": [("상태기계로 다룬다", "상태기계(정해진 상태 사이를 조건에 따라 오가는 규칙)로 다룬다")],
 "arch": [("스택 덤프도", "스택 덤프(멈춘 위치 기록)도")],
 "incidents": [("(비멱등)", "(비멱등: 할 때마다 결과가 쌓이는 요청)")],
 "heap": [("UI 프로세스에서", "UI 프로세스(화면 프로그램)에서"),
          ("만들 수 없게</b> 됐다", "만들 수 없게</b>(힙손상: 객체를 만드는 메모리 공간의 장부가 망가짐) 됐다")],
 "results": [("가동률 하한.", "가동률 하한(적어도 이만큼은 돌았다는 최솟값)."),
             ("HEALTH 줄", "HEALTH 줄(10분마다 남기는 상태 기록)")],
 "ap-rec": [("링버퍼에", "링버퍼(최근 것만 돌려 담는 저장소)에")],
}
# 보조 쪽 맨 위: 말로 풀 순서
ORDER = {
 "cover": ["v1은 한 프로그램이라 오래 켜 두면 감시가 조용히 멈췄다(freeze).",
           "v2는 셋으로 나눠 서로 살아 있는지 확인한다.",
           "세 가지 차이: 구조 · 장기 운영 · 장애 통보."],
 "system": ["채널마다 장비를 달지 않고, 멀티뷰어 화면 한 장을 입력으로 쓴다.",
            "신호 흐름 다섯 단계: 방송 신호 → 멀티뷰어 → 캡처보드 → 감시PC → 알림.",
            "그림의 V1·A1 사각형 하나하나가 센서다."],
 "pipeline": ["일꾼을 나눠 느린 일(발송·녹화)이 검사를 막지 않게 했다.",
              "메인 루프는 0.2초마다 한 바퀴, 여섯 단계.",
              "화면은 공유 메모리로 넘기고, 잠금 없이(seqlock) 읽는다."],
 "video": ["평균만 보면 로고·작은 움직임이 묻힌다 → 25칸으로 나눈다.",
           "블랙: 세 관문을 모두 통과하고 5초.",
           "스틸: 25칸이 모두 멈추고 120초."],
 "audio": ["소리는 두 가지로 본다: 보는 레벨미터, 듣는 임베디드.",
           "레벨미터: 초록 픽셀 5% 미만이 60초 → 경보. 임베디드: −50 dBFS 이하 60초.",
           "10-27 마이크 권한 사고와 지금의 대응."],
 "timing": ["0.2초 판정은 흔들린다 → 「얼마나 오래」로 정한다(히스테리시스).",
            "정파 상태기계: 평상시 → 정파 준비 → 정파 중.",
            "진입은 화면을 보고, 해제는 시간 상한 — 오진입이 더 비싸서(오류 비대칭)."],
 "arch": ["세 프로그램의 역할: UI · Watchdog · Detection.",
          "고장마다 누가 무엇을 보고 몇 초 안에 알아채나.",
          "heartbeat 두 겹 — v1의 freeze를 잡는 장치."],
 "incidents": ["공통점: 에러가 아니라 「정상처럼 보이는 값」이 문제였다.",
               "① 캡처 무신호 · ② 시계 점프 — 내용을 보고, 스톱워치로 잰다.",
               "③ 텔레그램 3번 — 상대가 받았는지를 기준으로 재시도."],
 "heap": ["증상: 4~5일마다 UI만 조용히 고장, 재현 불가.",
          "관측 장치부터 달고, 용의자를 하나씩 뺐다.",
          "3.13 고정 뒤 85일 무재발. 원인 메커니즘은 모른다고 솔직히."],
 "results": ["숫자는 실제 로그에서, 가동률은 일부러 불리하게.",
             "알린 이상 41건과 자동 복구.",
             "확산: 같은 장비에 실행.bat 한 번."],
 "ap-rec": ["링버퍼라 사고 전 10초도 남는다.",
            "영상·소리의 시작점과 속도를 맞췄다."],
}

def strip_images(html):
    imgs = []
    def rep(m):
        imgs.append(m.group(0)); return f"@@IMG{len(imgs)-1}@@"
    return re.sub(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+", rep, html), imgs

def txt(h): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()
def inner(h): return h[h.index(">") + 1: h.rindex("</")]

def build():
    orig = (HERE / "원본_스크롤판.html").read_text(encoding="utf-8")
    s, imgs = strip_images(orig)
    out, total = [], 0
    for sid, body in sections(s):
        bl = [b[3] for b in top_blocks(body)]
        m = re.search(r'<span class="no">(.*?)</span><h2>(.*?)</h2>', bl[0])
        no, title = m.group(1), m.group(2)
        figs = [re.sub(r'<figure class="[^"]*">', "<figure>", b) for b in bl if b.startswith("<figure")]
        spec = MAIN[sid]
        if spec == "all":
            spec = [i for i, b in enumerate(bl) if i and not b.startswith("<figure")]
        used, main = set(), []
        for it in spec:
            if isinstance(it, str) and it.startswith("<"):
                main.append(it); continue
            if isinstance(it, str):
                i, rng = it.split(":"); i = int(i); a, b = map(int, rng.split("-"))
                lis = [x[3] for x in top_blocks(inner(bl[i]))]
                wrap = bl[i][: bl[i].index(">") + 1]; tag = re.match(r"<(\w+)", wrap).group(1)
                main.append(wrap + "".join(lis[a:b]) + f"</{tag}>")
                used.add(("li", i, a, b)); continue
            main.append(bl[it]); used.add(it)
        mh = "\n".join(main)
        for a, b in GLOSS.get(sid, []):
            assert a in mh, f"{sid}: 뜻 붙일 글 없음 {a}"
            mh = mh.replace(a, b, 1)
        # 보조: 본 쪽에 안 쓴 나머지(원래 순서)
        rest = []
        for i, b in enumerate(bl):
            if i == 0 or b.startswith("<figure") or i in used or not txt(b): continue
            part = [u for u in used if isinstance(u, tuple) and u[1] == i]
            if part:
                _, _, a, e = part[0]
                lis = [x[3] for x in top_blocks(inner(b))]
                wrap = b[: b.index(">") + 1]; tag = re.match(r"<(\w+)", wrap).group(1)
                left = lis[:a] + lis[e:]
                if not left: continue
                wrap2 = wrap if e >= len(lis) or a else wrap.replace(">", f' start="{e+1}">', 1)
                b = wrap2 + "".join(lis[e:] if a == 0 else left) + f"</{tag}>"
            rest.append(b)
        # 뒤에 내용 없는 소제목 제거
        clean = []
        for k, b in enumerate(rest):
            if b.startswith("<h3") and (k + 1 == len(rest) or rest[k + 1].startswith("<h3")): continue
            clean.append(b)
        mode, w = FIG.get(sid, (None, None))
        cls = f"page main{' fig-'+mode+' f-'+sid if figs and mode else ''}"
        style = f' style="--figw:{w}"' if figs and w else ""
        figh = f'<div class="fig">{"".join(figs)}</div>' if figs and mode else ""
        out.append(f'<section class="{cls}" data-ch="{sid}"{style}>'
                   f'<header class="ph"><span class="no">{no}</span><span class="ct">{title}</span></header>'
                   f'<div class="pb">{figh}<div class="content">\n{mh}\n</div></div>'
                   f'<footer class="pf"><span class="hint"></span><span class="n"></span></footer></section>')
        if clean:
            order = "".join(f"<li>{x}</li>" for x in ORDER[sid])
            out.append(f'<section class="page sup" data-ch="{sid}">'
                       f'<header class="ph"><span class="no">{no}</span><span class="ct">{title}</span><span class="pp">보조 쪽</span></header>'
                       f'<div class="order"><h3>말로 풀 순서</h3><ol>{order}</ol></div>'
                       f'<div class="sbody">\n' + "\n".join(clean) + '\n</div></section>')
    font = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">'
    css = (HERE / "deck.css").read_text(encoding="utf-8")
    js = (HERE / "runtime.js").read_text(encoding="utf-8")
    for name, secs, sel, bodycls in [
        ("KBS_발표_본쪽.html", [x for x in out if 'class="page sup' not in x], "#deck .page.main", ""),
        ("KBS_발표_본쪽+보조쪽.html", out, "#deck .page", ' class="with-sup"'),
    ]:
        deck = '<main id="deck">\n' + "\n".join(secs) + "\n</main>"
        deck = re.sub(r"@@IMG(\d+)@@", lambda x: imgs[int(x.group(1))], deck)
        html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KBS Monitoring v2 발표</title>
<meta name="claude:viewport-fit-sides" content="cover">
{font}
<style>
{css}
</style></head><body{bodycls}>
<div id="stage">{deck}</div>
<script>
{js.replace("#deck .page.main", sel)}
</script>
</body></html>
"""
        (HERE.parent / name).write_text(html, encoding="utf-8")
        print(name, "쪽", len(secs), "보조 포함" if bodycls else "보조 없음:", 'page sup' not in html if not bodycls else "")

build()
