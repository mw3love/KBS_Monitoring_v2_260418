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
- 발표용 해설(실제 발표에 씀, 1920×1080 고정 · →/← · 마우스 휠로 넘김):
  - `docs/발표준비/KBS_발표_본쪽.html`·`.pdf` (18쪽) — 2026-11-18 구성: 표지 · 시스템 · 블랙 · 스틸 · 소리 · 시간/정파 · 구조 · 힙손상 · 덤 기능 · 설정 탭 7쪽 · 검증 · Q&A 1쪽. 모든 쪽이 도식(`쪽만들기/도식/*.html`), 설정 탭은 `docs/screenshots/` 캡처, 8 · 9쪽에 실제 텔레그램 캡처(`docs/screenshots/telegram/`) — 예비 링크 https://claude.ai/artifact/GVXaFr2pk5tS1XWpitx6zr (2026-11-18 재구성 전 13쪽 그대로)
  - 발표자용 본쪽+보조쪽 파일은 2026-11-18 없앰(사용자 결정). 발표자 공부는 `KBS_발표_학습자료.html`
  - `docs/발표준비/쪽만들기/`에서 `python build.py`로 만든다(넘침 검사 `python check.py`, PDF는 Edge `--print-to-pdf`). 도식 안 그림은 `{{IMG:저장소 경로}}`, 선 아이콘은 `{{ICON:이름}}`(`build.py`의 `ICONS`). 손으로 따로 고치지 말 것
- 2026-11-18 덱을 해설 구성(제목 아래 요지 줄 + 고른 용어만 + 방송 비유 칩)으로 다시 씀. 청중은 방송기술 엔지니어(컴퓨터 비전공)
- 옛 덱 `docs/발표덱_KBS/`(이전 계정 링크, 수정 불가)
