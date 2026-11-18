# KBS 발표덱 (2026 미디어창의기술전, 2026-11-19)

- 게시본: https://claude.ai/artifact/YHKrFEC7JcrQqstRccQrY4 (Slides 아티팩트, 밝은 단일 테마 — 출력 고려)
- 이 폴더는 게시본의 원본 사본이다. `deck.json`·`deck.css`·`slides/*.html`을 고쳐 같은 url로 다시 게시한다.
- 슬라이드 안 `/_blob/<id>`는 아티팩트에 올린 그림이다. 대응:
  - `f4d442b6…` = `docs/소개서/main.jpg` · `714ff9b4…` = `docs/소개서/set_video_roi.jpg` · `7ae21b03…` = `docs/소개서/set_signoff.jpg`
  - `ac629f02…` = `fig/fig_hsv.png` · `f97935fc…` = `fig/fig_hsv_ctx.png` · `b6f4bac2…` = `fig/fig_grid.png`
  - `6bc84812…` = `fig/fig_log.png` · `9311f0f9…` = `fig/fig_boot.png`
- 그림 생성 스크립트: `fig/figs.py`, `fig/still_fig.py` (원본 녹화 경로는 스크립트 안 — 재실행 시 확인 필요)
- 발표자 학습자료: `docs/발표준비/KBS_발표_학습자료.html`·`.pdf`
- 슬라이드 해설(장별 요지·낱말·질문): https://claude.ai/artifact/Y9vrEzBrdNKCBidneEezk4 — 원본 `docs/발표준비/KBS_슬라이드_해설.src.html`(그림 자리 `{{IMG:…}}`)
- 용어 고르기(설명/이름만/뺌, 2026-11-18 추천값 그대로 확정): https://claude.ai/artifact/5o53s7Q2CvfVvrBm46FQ7G — 원본 `docs/발표준비/KBS_발표_용어고르기.html`
- 발표용 해설(실제 발표에 씀, 1920×1080 고정 · →/← 넘김):
  - 제출·발표용 `docs/발표준비/KBS_발표_본쪽.html`·`.pdf` — 장마다 본 쪽 1장(13쪽), 보조 내용 없음 — 예비 링크 https://claude.ai/artifact/GVXaFr2pk5tS1XWpitx6zr
  - 발표자용 `docs/발표준비/KBS_발표_본쪽+보조쪽.html`·`.pdf` — 본 쪽 뒤에 말로 풀 순서·자세한 설명·낱말·비유·질문
  - 두 파일은 `docs/발표준비/쪽만들기/`에서 `python build.py`로 함께 만든다(원본 `원본_스크롤판.html`, 넘침 검사 `python check.py`). 손으로 따로 고치지 말 것
- 2026-11-18 덱을 해설 구성(제목 아래 요지 줄 + 고른 용어만 + 방송 비유 칩)으로 다시 씀. 청중은 방송기술 엔지니어(컴퓨터 비전공)
- 옛 덱 `docs/발표덱_KBS/`(이전 계정 링크, 수정 불가)
