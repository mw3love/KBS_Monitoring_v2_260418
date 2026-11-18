"""발표 HTML(../KBS_발표_본쪽.html)을 만든다. 실행: python build.py → python check.py

- 도식 쪽: 도식/<이름>.html (원리·구조·Q&A 등). 그림 자리 {{FIG0}} = 그 장 원본 그림, {{IMG:저장소 상대경로}} = 저장소 그림, {{ICON:이름}} = 선 아이콘(아래 ICONS)
- 설정 탭 쪽: 아래 SETTINGS 표 + docs/screenshots/ 캡처(manual/capture_screens.py로 다시 찍음)
- 원본_스크롤판.html: 예전 장별 해설. 지금은 그림({{FIG0}})만 가져다 쓴다
2026-11-18: 발표자용 본쪽+보조쪽 파일은 없앰(사용자 결정). 발표자 공부 자료는 ../KBS_발표_학습자료.html
"""
import re, sys, base64, pathlib
from tok import top_blocks, sections

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[2]
# 2026-11-18 구성: 원리(블랙·스틸·소리·시간) → 구조 → 힙손상(격리의 실제 효과) → 덤 기능 → 설정 탭 → 검증 → Q&A.
# (장 id, [(쪽 번호, 도식 파일 이름)]) — 쪽은 모두 도식/<이름>.html. "settings"는 SETTINGS 표로 7쪽을 만든다.
# 장 id가 원본_스크롤판.html에 있으면 그 장의 그림을 {{FIG0}}…로 쓸 수 있다.
PLAN = [
 ("cover", [("01", "cover")]), ("system", [("02", "system")]),
 ("video", [("03", "black"), ("04", "still")]), ("audio", [("05", "audio")]),
 ("timing", [("06", "timing")]), ("arch", [("07", "arch")]), ("heap", [("08", "heap")]),
 ("features", [("09", "features")]),
 ("settings", [(f"{10 + i:02d}", None) for i in range(7)]),
 ("results", [("17", "results")]),
 ("qa", [("Q&amp;A", "qa")]),
]
# 설정창 7개 탭(SettingsDialog 탭 순서): (탭 이름, 캡처 파일, 이 탭에서 정하는 것, 관련 쪽)
SETTINGS = [
 ("영상설정", "09_recording_settings.png",
  ["캡처 입력 포트(또는 시험용 영상 파일)", "자동 녹화: 사고 전 · 후 몇 초를 담을지, 저장 폴더", "녹화 파일 보관 기간, 출력 해상도 · FPS"], "09 덤 기능(자동 녹화)"),
 ("비디오 영역 설정", "02_video_roi.png",
  ["화면 위에 마우스로 영상 감지영역(V)을 그리기 · 옮기기 · 복사", "표에서 이름(1TV ON-AIR 등) · 위치 · 크기를 바로 고침"], "03 블랙 · 04 스틸"),
 ("오디오 레벨미터 영역 설정", "03_audio_roi.png",
  ["멀티뷰어의 초록 소리 막대 위에 레벨미터 감지영역(A)을 그림", "비디오 영역 설정과 같은 방식"], "05 소리"),
 ("감도설정", "04_sensitivity.png",
  ["블랙 · 스틸 · 레벨미터 · 임베디드의 기준값(예: 블랙 5초, 스틸 120초, −50 dBFS)", "감지 주기 · 화면 축소 비율, 종류별 켜고 끄기", "「자동 성능 감지」: 이 PC 성능에 맞는 값을 추천"], "03 ~ 05"),
 ("정파설정", "05_signoff.png",
  ["그룹(1TV · 2TV)마다 정파 시각 · 요일", "정파 감지영역: 진입을 판단할 영역과 알림을 끌 영역", "정파 준비 · 진입 · 해제 때 울릴 소리"], "06 정파"),
 ("알림설정", "06_alerts.png",
  ["경보음 파일", "텔레그램 봇 · 채팅방, 사진 첨부, 종류별 알림 켜기", "시스템 알림 · 자동 재시작(화면 아래쪽)", "캡처의 토큰 · 채팅 ID는 가림"], "09 덤 기능"),
 ("저장/불러오기", "07_save_load.png",
  ["지금 설정 전체를 파일 하나로 저장", "다른 PC에서 불러오면 바로 적용 — 다른 국으로 옮길 때 씀", "기본값으로 초기화"], "17 확산"),
]
# 선 아이콘(24칸 격자 · 선 굵기 2, 09 덤 기능 카드 아이콘과 같은 모양). 도식에서 {{ICON:이름}}으로 쓴다
ICONS = {
 "tower": '<circle cx="12" cy="9" r="2"/><path d="M12 11v11M8.5 22L12 11l3.5 11"/><path d="M8 5.5a5 5 0 0 0 0 7M16 5.5a5 5 0 0 1 0 7M5 3a9 9 0 0 0 0 12M19 3a9 9 0 0 1 0 12"/>',
 "multiview": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8.7 3v14M15.3 3v14M2 10h20M8 21h8M12 17v4"/>',
 "capture": '<rect x="2" y="5" width="20" height="12" rx="2"/><rect x="6" y="8" width="6" height="6" rx="1"/><path d="M15 9h3M15 13h3M5 17v3M9 17v3M13 17v3M17 17v3"/>',
 "pc": '<rect x="2" y="4" width="14" height="11" rx="1.5"/><path d="M5.5 20h7M9 15v5"/><rect x="18" y="4" width="4" height="16" rx="1"/><path d="M20 7.5v.01"/>',
 "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21h4"/>',
 "screen": '<rect x="2" y="4" width="20" height="14" rx="2"/><path d="M10 8.5v5l4.5-2.5z"/><path d="M8 21h8"/>',
 "meter": '<path d="M3 21h18M6 18v-6M10 18V6M14 18v-8M18 18V9"/>',
 "wave": '<path d="M2 12h3l2-6 3 12 3-9 2 6 2-3h5"/>',
 "shield": '<path d="M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
 "monitor": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
 "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
 "speaker": '<path d="M11 5L6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
 "plane": '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
 "rec": '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="M16 10l6-3v10l-6-3"/><circle cx="7" cy="12" r="1.5" fill="currentColor"/>',
}
def icon(spec):
    """{{ICON:이름}} 또는 {{ICON:이름@x,y,크기}}(SVG 도식 안에 넣을 때 자리 지정) → 선 아이콘 svg"""
    name, _, pos = spec.partition("@")
    at = ""
    if pos:
        x, y, s = pos.split(",")
        at = f' x="{x}" y="{y}" width="{s}" height="{s}"'
    return (f'<svg class="ico"{at} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')

def strip_images(html):
    imgs = []
    def rep(m):
        imgs.append(m.group(0)); return f"@@IMG{len(imgs)-1}@@"
    return re.sub(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+", rep, html), imgs


def page(cls, sid, no, title, inner_html, style="", figh=""):
    return (f'<section class="{cls}" data-ch="{sid}"{style}>'
            f'<header class="ph"><span class="no">{no}</span><span class="ct">{title}</span></header>'
            f'<div class="pb">{figh}<div class="content">\n{inner_html}\n</div></div>'
            f'<footer class="pf"><span class="hint"></span><span class="n"></span></footer></section>')

def diagram(name, figs):
    """도식/<name>.html → (쪽 제목, 본문). 첫 줄 <!-- title: … -->, 그림 자리 {{FIG0}} = 그 장 원본 그림 0번"""
    src = (HERE / "도식" / f"{name}.html").read_text(encoding="utf-8")
    title = re.search(r"<!-- title: (.*?) -->", src).group(1)
    body = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    body = re.sub(r"\{\{FIG(\d)\}\}", lambda m: figs[int(m.group(1))], body)
    body = re.sub(r"\{\{IMG:(.*?)\}\}", lambda m: img_uri(m.group(1)), body)
    body = re.sub(r"\{\{ICON:(.*?)\}\}", lambda m: icon(m.group(1)), body)
    return title, body.strip()

def img_uri(rel):
    """저장소 상대경로 그림 → data: URI(발표 HTML은 파일 하나로 들고 다닌다)"""
    p = ROOT / rel
    kind = "png" if p.suffix.lower() == ".png" else "jpeg"
    return f"data:image/{kind};base64," + base64.b64encode(p.read_bytes()).decode()

def settings_page(no, i):
    name, fn, items, rel = SETTINGS[i]
    lis = "".join(f"<li>{x}</li>" for x in items)
    body = (f'<div class="dg"><div class="body" style="grid-template-columns:auto minmax(0,1fr);align-items:start">'
            f'<img src="{img_uri("docs/screenshots/" + fn)}" alt="설정창 {name} 탭" style="display:block;height:860px;width:auto;border:1px solid var(--line);border-radius:8px">'
            f'<div style="display:flex;flex-direction:column;gap:22px"><h4 style="margin:0">이 탭에서 정하는 것</h4>'
            f'<ul style="margin:0;font-size:27px">{lis}</ul><span class="chip" style="align-self:start">관련: {rel}</span></div></div></div>')
    return page("page main diag", "settings", no, f"설정 {i + 1}/7 — {name}", body)

def build():
    orig = (HERE / "원본_스크롤판.html").read_text(encoding="utf-8")
    s, imgs = strip_images(orig)
    secs = dict(sections(s))
    out = []
    for sid, pages in PLAN:
        if sid == "settings":
            out += [settings_page(no, i) for i, (no, _) in enumerate(pages)]
            continue
        if sid not in secs:  # 원본에 없는 새 장: 도식 쪽만
            for no, dname in pages:
                out.append(page("page main diag", sid, no, *diagram(dname, [])))
            continue
        bl = [b[3] for b in top_blocks(secs[sid])]
        figs = [re.sub(r'<figure class="[^"]*">', "<figure>", b) for b in bl if b.startswith("<figure")]
        for no, dname in pages:
            out.append(page("page main diag", sid, no, *diagram(dname, figs)))
    font = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">'
    css = (HERE / "deck.css").read_text(encoding="utf-8")
    js = (HERE / "runtime.js").read_text(encoding="utf-8")
    for name, secs, sel, bodycls in [("KBS_발표_본쪽.html", out, "#deck .page.main", "")]:
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
        print(name, "쪽", len(secs))

build()
