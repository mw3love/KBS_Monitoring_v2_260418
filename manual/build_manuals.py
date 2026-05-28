#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KBS On-Air Monitoring v2.1.0 매뉴얼 PDF 생성 스크립트
  1. KBS_Monitoring_빠른참조.pdf  — 가로 A4, 2페이지
  2. KBS_Monitoring_사용자매뉴얼.pdf — 세로 A4, 전체 매뉴얼
"""
import os
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, PageBreak, HRFlowable, KeepTogether,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas as rl_canvas

# ── 경로 ──────────────────────────────────────────────────────────────────────
BASE    = r"G:\내 드라이브\A1. 개인 자료\A1. AI 연습\260418 KBS_Monitoring_v2"
IMG_DIR = os.path.join(BASE, "images")
OUT_DIR = os.path.join(BASE, "manual")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 폰트 등록 ─────────────────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('Malgun',     r'C:\Windows\Fonts\malgun.ttf'))
try:
    pdfmetrics.registerFont(TTFont('MalgunBold', r'C:\Windows\Fonts\malgunbd.ttf'))
except Exception:
    pdfmetrics.registerFont(TTFont('MalgunBold', r'C:\Windows\Fonts\malgun.ttf'))

# ── 색상 ──────────────────────────────────────────────────────────────────────
ORANGE      = colors.HexColor('#D97757')
DARK        = colors.HexColor('#1A1A2E')
SECTION_BG  = colors.HexColor('#FFF5F0')
BORDER      = colors.HexColor('#E0E0E0')
GRAY_TEXT   = colors.HexColor('#555555')
TABLE_ALT   = colors.HexColor('#FAF0EC')
WHITE       = colors.white

# ── 이미지 ────────────────────────────────────────────────────────────────────
IMGS = {
    'main':           'Snipaste_2026-05-03_20-36-23.png',
    'video_settings': 'Snipaste_2026-05-03_20-36-54.png',
    'video_roi':      'Snipaste_2026-05-03_20-36-57.png',
    'audio_roi':      'Snipaste_2026-05-03_20-36-59.png',
    'sensitivity':    'Snipaste_2026-05-03_20-37-01.png',
    'signoff':        'Snipaste_2026-05-03_20-37-03.png',
    'alarm':          'Snipaste_2026-05-03_20-37-06.png',
    'save':           'Snipaste_2026-05-03_20-37-09.png',
}

def ipath(key):
    return os.path.join(IMG_DIR, IMGS[key])

def rl_img(key, max_w, max_h):
    """비율 유지 RLImage."""
    p = ipath(key)
    with PILImage.open(p) as im:
        w, h = im.size
    r = min(max_w / w, max_h / h)
    return RLImage(p, width=w * r, height=h * r)

# ── 스타일 헬퍼 ───────────────────────────────────────────────────────────────
def ps(name='', **kw):
    defaults = dict(fontName='Malgun', fontSize=10, textColor=DARK,
                    spaceAfter=3, leading=14)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

TITLE_S  = ps('title',  fontName='MalgunBold', fontSize=28, textColor=ORANGE,
              spaceAfter=6, alignment=TA_CENTER)
SUBT_S   = ps('subt',   fontSize=13, textColor=GRAY_TEXT, spaceAfter=4, alignment=TA_CENTER)
H1_S     = ps('h1',     fontName='MalgunBold', fontSize=16, textColor=ORANGE,
              spaceBefore=12, spaceAfter=5, leading=20)
H2_S     = ps('h2',     fontName='MalgunBold', fontSize=12, textColor=DARK,
              spaceBefore=8, spaceAfter=3, leading=16)
BODY_S   = ps('body',   fontSize=9.5, leading=15, spaceAfter=3)
CAPTION_S= ps('cap',    fontSize=8,  textColor=GRAY_TEXT, alignment=TA_CENTER,
              spaceAfter=5, leading=11)
TOC_S    = ps('toc',    fontSize=11, leading=16, spaceAfter=3)
TOC_I_S  = ps('toci',   fontSize=9.5, textColor=GRAY_TEXT, leading=14,
              spaceAfter=2, leftIndent=20)

def th_para(text):
    return Paragraph(text, ps('th', fontName='MalgunBold', fontSize=9.5,
                               textColor=WHITE, leading=13))
def td_bold(text):
    return Paragraph(text, ps('tdb', fontName='MalgunBold', fontSize=9,
                               textColor=DARK, leading=13))
def td_para(text, size=9):
    return Paragraph(text, ps('td', fontSize=size, textColor=DARK, leading=13))
def td_gray(text):
    return Paragraph(text, ps('tdg', fontSize=8.5, textColor=GRAY_TEXT, leading=12))

def mk_table(rows, col_w, alt=True):
    tbl = Table(rows, colWidths=col_w)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), ORANGE),
        ('GRID',       (0, 0), (-1, -1), 0.4, BORDER),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING',    (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]
    if alt:
        style.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, TABLE_ALT]))
    tbl.setStyle(TableStyle(style))
    return tbl

def hr(avail_w, thick=1, sp=4):
    return HRFlowable(width=avail_w, thickness=thick, color=ORANGE,
                      spaceBefore=0, spaceAfter=sp*mm)

def orange_label(text):
    return Paragraph(text, ps('ol', fontName='MalgunBold', fontSize=10,
                               textColor=ORANGE, spaceBefore=5, spaceAfter=2))

# =============================================================================
# 1. 빠른 참조 (Landscape A4, 2-page)
# =============================================================================
def build_quick_ref():
    PAGE = landscape(A4)
    W, H = PAGE
    MRG  = 18 * mm
    path = os.path.join(OUT_DIR, "KBS_Monitoring_빠른참조.pdf")
    c = rl_canvas.Canvas(path, pagesize=PAGE)

    def header_bar(subtitle):
        c.setFillColor(ORANGE)
        c.rect(0, H - 28*mm, W, 28*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont('MalgunBold', 16)
        c.drawString(MRG, H - 18*mm, "KBS On-Air Monitoring  v2.1.0")
        c.setFont('Malgun', 10)
        c.drawRightString(W - MRG, H - 18*mm, subtitle)

    # ── Page 1: 메인 화면 + 콜아웃 ──────────────────────────────────────────────
    header_bar("빠른 참조 가이드 — 화면 구성")

    avail_h = H - 28*mm - MRG - 12*mm   # below header, above bottom
    img_w   = W * 0.63
    img_h   = avail_h

    with PILImage.open(ipath('main')) as im:
        iw, ih = im.size
    r       = min(img_w / iw, img_h / ih)
    dw, dh  = iw * r, ih * r

    img_x = MRG
    img_y = H - 28*mm - 6*mm - dh
    c.drawImage(ipath('main'), img_x, img_y, width=dw, height=dh,
                preserveAspectRatio=True)
    c.setFillColor(GRAY_TEXT)
    c.setFont('Malgun', 7)
    c.drawString(img_x, img_y - 9, "▲ 메인 화면")

    # 콜아웃 패널
    px = img_x + dw + 8*mm
    pw = W - px - MRG
    py = img_y
    ph = dh

    c.setFillColor(SECTION_BG)
    c.roundRect(px - 4, py - 4, pw + 8, ph + 8, 5, fill=1, stroke=0)

    c.setFillColor(ORANGE)
    c.setFont('MalgunBold', 10)
    c.drawString(px, py + ph - 14, "화면 구성 요소")
    c.setStrokeColor(ORANGE)
    c.setLineWidth(0.8)
    c.line(px, py + ph - 18, px + pw - 4, py + ph - 18)

    callouts = [
        ("① 시스템 성능",     "CPU / RAM / GPU 사용률"),
        ("② 현재시간",        "시스템 현재 시각"),
        ("③ Embedded Audio", "L/R 오디오 레벨 세그먼트 미터"),
        ("④ 감지 현황",       "V A EA 누적 알람 카운터"),
        ("⑤ 감지 ON",        "감지 시작/중지 토글"),
        ("⑥ 영역 표시",       "감지 영역 오버레이 ON/OFF"),
        ("⑦ Mute",           "알림음 소리 끄기/켜기"),
        ("⑧ 알람 확인 ACK",  "발생 알람 일괄 확인 처리"),
        ("⑨ 정파 버튼",       "1TV/2TV 정파 상태 표시"),
        ("⑩ 설정 아이콘",     "설정(⚙) / 다크모드 / 창 모드"),
        ("⑪ 영상 뷰",         "캡쳐카드 입력 영상"),
        ("⑫ SYSTEM LOG",     "실시간 감지·시스템 로그"),
    ]

    row_h = (ph - 24) / len(callouts)
    for i, (lbl, desc) in enumerate(callouts):
        y0 = py + ph - 24 - i * row_h
        c.setFillColor(ORANGE)
        c.setFont('MalgunBold', 8.5)
        c.drawString(px + 2, y0, lbl)
        c.setFillColor(DARK)
        c.setFont('Malgun', 7.5)
        c.drawString(px + 4, y0 - 10, desc)
        if i < len(callouts) - 1:
            c.setStrokeColor(BORDER)
            c.setLineWidth(0.3)
            c.line(px, y0 - 14, px + pw - 4, y0 - 14)

    c.showPage()

    # ── Page 2: 설정 탭 요약 ─────────────────────────────────────────────────────
    header_bar("설정 다이얼로그 탭 요약")

    avail_w = W - 2 * MRG
    cw = [avail_w * 0.16, avail_w * 0.28, avail_w * 0.56]

    rows = [
        [th_para("탭"), th_para("주요 기능"), th_para("주요 설정 항목")],
        [td_bold("영상설정"),
         td_para("캡쳐 소스 및 자동 녹화"),
         td_gray("캡쳐 포트 번호 / 파일 입력(테스트용) / 자동 녹화 폴더·버퍼·보관기간 / 녹화 해상도·FPS")],
        [td_bold("비디오\n영역 설정"),
         td_para("블랙·스틸 감지 영역 지정"),
         td_gray("드래그로 영역 추가 / 라벨(V1, V2...) / 편집 단축키(화살표·Ctrl+D·Delete)")],
        [td_bold("오디오 레벨미터\n영역 설정"),
         td_para("오디오 미터 감지 위치 지정"),
         td_gray("드래그로 영역 추가 / 라벨(A1~A5) / 방송 오디오 레벨 바 위치에 맞게 설정")],
        [td_bold("감도설정"),
         td_para("감지 민감도 조정"),
         td_gray("블랙(밝기·픽셀비율) / 스틸(픽셀차이·블록변화율) / 오디오HSV(H/S/V 범위) / 임베디드(무음 dB)")],
        [td_bold("정파설정"),
         td_para("1TV/2TV 자동 정파 스케줄"),
         td_gray("정파 시간 구간 / 정파준비·해제준비 시각 / 적용 요일 / 정파 감지영역 / 정파 알림음")],
        [td_bold("알림설정"),
         td_para("알림음 및 텔레그램 봇"),
         td_gray("알림음 파일 / Bot Token·Chat ID / 이벤트별 알림 ON/OFF / 자동 재시작")],
        [td_bold("저장/불러오기"),
         td_para("설정 파일 관리"),
         td_gray("현재 설정 JSON 저장 / 저장된 설정 불러오기 / 공장 초기화(되돌릴 수 없음)")],
    ]

    tbl = mk_table(rows, cw)
    tbl_w, tbl_h = tbl.wrapOn(c, avail_w, H)
    tbl_y = H - 28*mm - 10*mm - tbl_h
    tbl.drawOn(c, MRG, tbl_y)

    # TIP 박스
    tip_y = tbl_y - 10*mm
    c.setFillColor(SECTION_BG)
    c.roundRect(MRG, tip_y - 15*mm, avail_w, 13*mm, 4, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.setFont('MalgunBold', 9)
    c.drawString(MRG + 8, tip_y - 4.5*mm, "TIP")
    c.setFillColor(DARK)
    c.setFont('Malgun', 8.5)
    c.drawString(MRG + 24, tip_y - 4.5*mm,
                 "감지영역 편집: 설정 → 비디오/오디오 탭 → [감지영역 편집] 버튼 클릭 후 영상 위 드래그")
    c.drawString(MRG + 24, tip_y - 10*mm,
                 "정파 상태 확인: 상단 정파 버튼 색상 (기본=대기 / 주황=정파준비 / 빨강=정파중)")

    c.showPage()
    c.save()
    print(f"  ✓ 빠른 참조: {path}")


# =============================================================================
# 2. 전체 사용자 매뉴얼 (Portrait A4)
# =============================================================================
def build_full_manual():
    W, H   = A4
    MRG    = 20 * mm
    AW     = W - 2 * MRG
    path   = os.path.join(OUT_DIR, "KBS_Monitoring_사용자매뉴얼.pdf")
    story  = []

    def img(key, max_h=110*mm):
        return rl_img(key, AW, max_h)

    def add_img(key, caption, max_h=110*mm):
        story.append(img(key, max_h))
        story.append(Paragraph(f"▲ {caption}", CAPTION_S))
        story.append(Spacer(1, 2*mm))

    def section_table(rows, col_ratios):
        cw = [AW * r for r in col_ratios]
        return mk_table(rows, cw)

    # ── 표지 ─────────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 55*mm))
    story.append(Paragraph("KBS On-Air Monitoring", TITLE_S))
    story.append(Paragraph("v2.1.0", ps('cv', fontName='MalgunBold', fontSize=34,
                                         textColor=DARK, spaceAfter=8, alignment=TA_CENTER, leading=42)))
    story.append(HRFlowable(width=AW * 0.4, thickness=2.5, color=ORANGE,
                             spaceAfter=8*mm, spaceBefore=0, hAlign='CENTER'))
    story.append(Paragraph("사 용 자  매 뉴 얼", SUBT_S))
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("작성일: 2026-05-03  |  제작: minwoo@kbs.co.kr",
                            ps('cv2', fontSize=9.5, textColor=GRAY_TEXT,
                               spaceAfter=4, alignment=TA_CENTER)))
    story.append(PageBreak())

    # ── 목차 ─────────────────────────────────────────────────────────────────────
    story.append(Paragraph("목   차", H1_S))
    story.append(hr(AW, 1.5))

    toc = [
        ("1장", "개요", True),
        ("2장", "메인 화면", True),
        ("3장", "설정 다이얼로그", True),
        ("  3.1", "영상설정", False),
        ("  3.2", "비디오 영역 설정", False),
        ("  3.3", "오디오 레벨미터 영역 설정", False),
        ("  3.4", "감도설정", False),
        ("  3.5", "정파설정", False),
        ("  3.6", "알림설정", False),
        ("  3.7", "저장/불러오기", False),
        ("4장", "감지 유형 설명", True),
        ("5장", "정파 기능", True),
        ("부록", "자주 묻는 질문 (FAQ)", True),
    ]
    for num, title, main in toc:
        sty = TOC_S if main else TOC_I_S
        story.append(Paragraph(f"<b>{num}</b>  {title}", sty))
    story.append(PageBreak())

    # ── 1장 개요 ──────────────────────────────────────────────────────────────────
    story.append(Paragraph("1장  개요", H1_S))
    story.append(hr(AW))
    story.append(Paragraph(
        "KBS On-Air Monitoring은 KBS 방송 송출 영상의 이상을 실시간으로 감지하고 "
        "담당자에게 즉시 알려주는 모니터링 시스템입니다.",
        BODY_S))
    story.append(Spacer(1, 3*mm))

    ov_rows = [
        [th_para("감지 유형"), th_para("설명")],
        [td_bold("블랙 감지"),          td_para("영상이 설정 시간 이상 어두운 상태(블랙 화면)가 지속될 때 알림")],
        [td_bold("스틸 감지"),          td_para("화면이 설정 시간 이상 정지 상태로 지속될 때 알림")],
        [td_bold("오디오 레벨미터 감지"), td_para("VU 미터 색상이 사라져 오디오 이상이 감지될 때 알림")],
        [td_bold("임베디드 오디오 감지"), td_para("HDMI 임베디드 오디오가 설정 시간 이상 무음 상태일 때 알림")],
    ]
    story.append(section_table(ov_rows, [0.28, 0.72]))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("<b>실행 방법</b>", H2_S))
    story.append(Paragraph(
        "• 배포 파일: <b>KBS_Monitoring.exe</b> 더블클릭<br/>"
        "• 소스 실행: <b>python main.py</b><br/>"
        "• 종료: 창 닫기 (현재 설정 자동 저장)",
        BODY_S))
    story.append(PageBreak())

    # ── 2장 메인 화면 ──────────────────────────────────────────────────────────────
    story.append(Paragraph("2장  메인 화면", H1_S))
    story.append(hr(AW))
    add_img('main', "메인 화면", max_h=95*mm)

    story.append(Paragraph("2.1  상단바", H2_S))
    tb_rows = [
        [th_para("영역"),                th_para("설명")],
        [td_bold("시스템 성능"),         td_para("CPU / RAM / GPU 사용률 실시간 표시")],
        [td_bold("현재시간"),            td_para("시스템 현재 시각")],
        [td_bold("Embedded Audio"),      td_para("L/R 채널 오디오 레벨 세그먼트 미터")],
        [td_bold("감지 현황 V/A/EA"),    td_para("각 감지 유형의 누적 알람 카운터 (V=영상 A=오디오 EA=임베디드)")],
        [td_bold("감지 ON"),             td_para("클릭 시 감지 시작/중지 토글. 활성 시 주황색 표시")],
        [td_bold("영역 표시 ON/OFF"),    td_para("영상 위 감지영역 오버레이 표시/숨김")],
        [td_bold("Mute"),               td_para("알림음 끄기/켜기 (감지 자체는 계속 동작)")],
        [td_bold("알람 확인 ACK"),       td_para("현재 발생한 모든 알람을 일괄 확인 처리")],
        [td_bold("1TV / 2TV 정파"),      td_para("정파 상태 표시 및 수동 전환")],
        [td_bold("⚙ / 🌙 / 창"),        td_para("설정 다이얼로그 열기 / 다크·라이트 모드 전환 / 창 모드 변경")],
    ]
    story.append(section_table(tb_rows, [0.3, 0.7]))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph("2.2  영상 뷰", H2_S))
    story.append(Paragraph(
        "캡쳐카드로 입력된 영상이 표시됩니다. 신호 없을 때는 <b>NO SIGNAL INPUT</b> 텍스트가 표시됩니다. "
        "비디오 감지영역(V1, V2...)과 오디오 레벨미터 감지영역(A1~A5)이 오버레이로 표시됩니다.",
        BODY_S))

    story.append(Paragraph("2.3  SYSTEM LOG 패널", H2_S))
    story.append(Paragraph(
        "우측 패널에 감지 이벤트·시스템 이벤트가 실시간으로 기록됩니다. "
        "상단 필터 버튼으로 표시 유형을 선택할 수 있습니다.",
        BODY_S))
    log_rows = [
        [th_para("필터"), th_para("표시 내용")],
        [td_bold("ALL"),   td_para("전체 로그 표시")],
        [td_bold("ERROR"), td_para("오류·알람 발생 이벤트")],
        [td_bold("STILL"), td_para("스틸(정지화면) 감지 이벤트")],
        [td_bold("AUDIO"), td_para("오디오 레벨미터 감지 이벤트")],
        [td_bold("EMBED"), td_para("임베디드 오디오 감지 이벤트")],
        [td_bold("INFO"),  td_para("시스템 시작·종료·프로세스 정보")],
        [td_bold("DEBUG"), td_para("디버그 메시지 (개발자용)")],
    ]
    story.append(section_table(log_rows, [0.18, 0.82]))
    story.append(PageBreak())

    # ── 3장 설정 다이얼로그 ────────────────────────────────────────────────────────
    story.append(Paragraph("3장  설정 다이얼로그", H1_S))
    story.append(hr(AW))
    story.append(Paragraph(
        "상단바 ⚙ 아이콘을 클릭하면 설정 다이얼로그가 열립니다. 7개의 탭으로 구성되어 있습니다.",
        BODY_S))
    story.append(Spacer(1, 3*mm))

    # 3.1 영상설정
    story.append(Paragraph("3.1  영상설정", H2_S))
    add_img('video_settings', "영상설정 탭", max_h=105*mm)
    for item, desc in [
        ("캡쳐 포트",          "캡쳐카드 입력 포트 번호 (0~3, 기본 0). 캡쳐카드가 여러 개일 때 번호 변경."),
        ("파일 입력 (테스트용)", "MP4 등 영상 파일을 포트 대신 소스로 사용. 파일 선택 시 재생 모드로 전환."),
        ("자동 녹화 설정",      "알람 발생 시 자동 녹화. 저장 폴더, 사전 버퍼(1~30초), 이후 녹화(1~60초) 설정."),
        ("최대 보관 기간 (일)", "이 기간이 지난 녹화 파일은 자동 삭제 (기본 7일, 1~365일)."),
        ("녹화 품질 설정",      "출력 해상도(960×540 권장) 및 FPS(10fps 권장). 해상도 높을수록 파일 크기 증가."),
    ]:
        story.append(Paragraph(f"• <b>{item}</b>: {desc}", BODY_S))
    story.append(Spacer(1, 3*mm))

    # 3.2 비디오 영역 설정
    story.append(Paragraph("3.2  비디오 영역 설정", H2_S))
    add_img('video_roi', "비디오 영역 설정 탭 (감지영역 V1, V2 등록된 상태)", max_h=105*mm)
    story.append(Paragraph(
        "[비디오 감지영역 편집] 버튼을 클릭하면 영상 위에 감지영역을 직접 그릴 수 있는 편집 모드가 활성화됩니다.",
        BODY_S))
    roi_rows = [
        [th_para("단축키"),                     th_para("동작")],
        [td_bold("드래그 (빈 곳)"),             td_para("새 감지영역 추가")],
        [td_bold("드래그 (영역 위)"),            td_para("영역 이동")],
        [td_bold("화살표 키 (↑↓←→)"),          td_para("선택 영역 10px 이동")],
        [td_bold("Shift + 화살표"),             td_para("선택 영역 1px 이동 (정밀 조정)")],
        [td_bold("Ctrl + 화살표"),              td_para("선택 영역 크기 10px 조정")],
        [td_bold("Ctrl + D"),                  td_para("선택 영역 복사")],
        [td_bold("Delete"),                    td_para("선택 영역 삭제")],
        [td_bold("Ctrl + 클릭"),               td_para("영역 선택 추가/제거")],
        [td_bold("Ctrl + 드래그 (선택 후)"),    td_para("복사하며 이동")],
    ]
    story.append(section_table(roi_rows, [0.4, 0.6]))
    story.append(PageBreak())

    # 3.3 오디오 레벨미터 영역 설정
    story.append(Paragraph("3.3  오디오 레벨미터 영역 설정", H2_S))
    add_img('audio_roi', "오디오 레벨미터 영역 설정 탭 (감지영역 A1~A5 등록된 상태)", max_h=105*mm)
    story.append(Paragraph(
        "방송 화면에 표시된 오디오 레벨 미터(VU 미터)의 위치를 감지 영역으로 지정합니다. "
        "감지영역 라벨은 자동으로 A1, A2, A3...으로 지정됩니다.",
        BODY_S))
    story.append(Paragraph(
        "HSV 색상 방식으로 오디오 레벨 미터의 색상 패턴을 감지합니다. "
        "감도설정 탭의 <b>오디오 레벨미터 감지 (HSV)</b> 섹션에서 색상 범위를 조정할 수 있습니다.",
        BODY_S))
    story.append(Spacer(1, 3*mm))

    # 3.4 감도설정
    story.append(Paragraph("3.4  감도설정", H2_S))
    add_img('sensitivity', "감도설정 탭", max_h=120*mm)

    sens = [
        ("블랙 감지", [
            ("밝기 임계값",         "0~255. 이 값 이하 픽셀을 어두운 픽셀로 판단 (기본 5)"),
            ("어두운 픽셀 비율 (%)", "50~100%. 이 비율 이상이면 블랙 판정 (기본 98%)"),
            ("움직임 감지 시 블랙 무시 기준", "0.0~5.0%. 프레임 간 변화 비율이 이 값 이상이면 블랙 무시 (화면 전환 오감지 방지)"),
            ("알람 발생 기준 (초)",  "블랙이 이 시간 이상 지속되면 알람 (기본 20초)"),
        ]),
        ("스틸 감지", [
            ("픽셀 차이 임계값",     "0~255. 프레임 간 픽셀 값 차이 기준 (기본 4)"),
            ("블록 변화 비율 (%)",   "변화된 블록 비율이 이 값 미만이면 스틸 판정 (기본 10%)"),
            ("연속 정상 프레임 수",  "이 수 이상 정상 프레임 연속 시 스틸 해제 (기본 3)"),
            ("알람 발생 기준 (초)",  "정지 화면이 이 시간 이상 지속되면 알람 (기본 60초)"),
        ]),
        ("오디오 레벨미터 감지 (HSV)", [
            ("H 범위 (색조)",       "0~179. 오디오 미터 색상의 색조 범위 (기본 40~95, 초록 계열)"),
            ("S 범위 (채도)",       "0~255. 색의 선명도 범위 (기본 80~255)"),
            ("V 범위 (명도)",       "0~255. 밝기 범위 (기본 60~255)"),
            ("감지 픽셀 비율 (%)",  "HSV 조건 픽셀 비율이 이 값 미만이면 알람 (기본 5%)"),
            ("복구 대기 (초)",      "정상 복구 후 이 시간이 지나야 알람 해제 (기본 2초)"),
        ]),
        ("임베디드 오디오 감지 (무음 감지)", [
            ("무음 임계값 (dB)",    "-60~0. 이 값 이하일 때 무음으로 판단 (기본 -50dB)"),
            ("알람 발생 기준 (초)", "무음이 이 시간 이상 지속되면 알람 (기본 20초)"),
        ]),
    ]
    for sec_name, items in sens:
        story.append(orange_label(sec_name))
        for param, desc in items:
            story.append(Paragraph(f"  • <b>{param}</b>: {desc}", BODY_S))
        story.append(Spacer(1, 2*mm))
    story.append(PageBreak())

    # 3.5 정파설정
    story.append(Paragraph("3.5  정파설정", H2_S))
    add_img('signoff', "정파설정 탭 (그룹 1: 1TV, 그룹 2: 2TV)", max_h=120*mm)
    story.append(Paragraph(
        "1TV와 2TV 각각의 자동 정파 스케줄을 설정합니다. "
        "[자동 정파 활성화]를 체크해야 자동으로 동작합니다.",
        BODY_S))
    so_rows = [
        [th_para("항목"),                     th_para("설명")],
        [td_bold("정파 시간 구간"),            td_para("정파 시작/종료 시각 (시:분). '익일' 체크 시 다음 날 종료")],
        [td_bold("정파준비 활성화"),           td_para("정파 시작 시각 N시간 전부터 정파준비 모드 (상단 버튼 색상 변경)")],
        [td_bold("정파해제준비 활성화"),       td_para("정파 종료 시각 N분 전부터 정파해제준비 모드")],
        [td_bold("정파 진입 기준 시간 (초)"),  td_para("정파 감지영역 스틸이 이 시간 이상 지속 시 자동 정파 진입 (보조 수단)")],
        [td_bold("조기 해제 기준 시간 (초)"),  td_para("정파 중 화면이 바뀌면 이 시간 후 자동 정파 종료")],
        [td_bold("적용 요일"),                td_para("이 요일에만 해당 그룹 자동 정파 동작. 전체/해제 버튼으로 일괄 선택")],
        [td_bold("정파 감지영역"),             td_para("정파 판단에 사용할 감지영역 선택 (미설정 시 경고 표시)")],
        [td_bold("정파 알림음"),              td_para("정파준비 시작, 정파 진입, 정파 해제 시 재생할 사운드 파일")],
    ]
    story.append(section_table(so_rows, [0.32, 0.68]))
    story.append(PageBreak())

    # 3.6 알림설정
    story.append(Paragraph("3.6  알림설정", H2_S))
    add_img('alarm', "알림설정 탭", max_h=120*mm)
    for item, desc in [
        ("알림음 파일",                 "알람 발생 시 재생할 WAV 파일. [찾아보기]로 변경, [테스트]로 미리 듣기."),
        ("텔레그램 알림 활성화",        "체크 시 텔레그램 봇을 통해 알람 메시지 발송."),
        ("Bot Token",                  "BotFather에서 발급받은 텔레그램 봇 토큰."),
        ("Chat ID",                    "알람 수신할 채팅/그룹/채널 ID (그룹은 음수 형식)."),
        ("시스템 알림 Chat ID (선택)",  "Watchdog 재spawn, 비정상 종료 등 시스템 이벤트를 별도 채팅으로 수신. 비워두면 기본 Chat ID로 발송."),
        ("연결 테스트",                 "설정된 봇으로 테스트 메시지를 발송하여 연결 확인."),
        ("알림 이벤트 선택",            "블랙/스틸/오디오/임베디드/정파/시스템 이벤트 각각 텔레그램 알림 ON/OFF."),
        ("재전송 대기 (초)",            "동일 감지영역 중복 알람 재전송 방지 대기 시간 (기본 60초)."),
        ("자동 재시작",                 "예약 재시작 활성화 및 기준 시각·주기·제외 시간대 설정. 프로그램 재시작으로 OS 리소스 초기화."),
    ]:
        story.append(Paragraph(f"• <b>{item}</b>: {desc}", BODY_S))
    story.append(Spacer(1, 3*mm))

    # 3.7 저장/불러오기
    story.append(Paragraph("3.7  저장/불러오기", H2_S))
    add_img('save', "저장/불러오기 탭", max_h=85*mm)
    for item, desc in [
        ("현재 설정 저장",   "현재 모든 설정을 JSON 파일로 내보냅니다. 다른 PC 이전 또는 백업 용도."),
        ("설정 파일 불러오기", "저장된 JSON 파일을 불러와 현재 설정에 적용합니다."),
        ("공장 초기화",      "모든 설정을 초기 기본값으로 되돌립니다. 되돌릴 수 없으므로 사용 전 반드시 설정을 저장하세요."),
    ]:
        story.append(Paragraph(f"• <b>{item}</b>: {desc}", BODY_S))
    story.append(PageBreak())

    # ── 4장 감지 유형 설명 ─────────────────────────────────────────────────────────
    story.append(Paragraph("4장  감지 유형 설명", H1_S))
    story.append(hr(AW))
    for title_t, desc_t in [
        ("블랙 감지 (Black Detection)",
         "캡쳐카드 입력 영상에서 비디오 감지영역 내 픽셀의 밝기가 설정된 임계값 이하인 픽셀 비율이 "
         "설정된 비율 이상인 상태가 설정된 시간 이상 지속될 때 알람이 발생합니다. "
         "방송 사고(블랙 아웃) 또는 캡쳐 케이블 단선 등의 상황을 감지합니다."),
        ("스틸 감지 (Still Detection)",
         "연속된 프레임 간 픽셀 변화량을 블록 단위로 비교하여 변화하는 블록의 비율이 설정값 미만인 "
         "상태가 설정된 시간 이상 지속될 때 알람이 발생합니다. "
         "방송 화면이 정지화면으로 고정되는 이상 상황을 감지합니다."),
        ("오디오 레벨미터 감지 (Audio Level Meter Detection)",
         "방송 화면에 표시된 VU 미터의 색상 패턴을 HSV 색공간으로 분석합니다. "
         "오디오 레벨미터 감지영역 내에서 설정된 HSV 범위에 해당하는 픽셀 비율이 설정값 미만이면 "
         "오디오 이상(레벨 소실)으로 판단합니다."),
        ("임베디드 오디오 감지 (Embedded Audio Detection)",
         "HDMI를 통해 전달되는 임베디드 오디오 신호를 실시간으로 측정합니다. "
         "음량이 설정된 무음 임계값(dB) 이하인 상태가 설정된 시간 이상 지속될 때 알람이 발생합니다. "
         "방송 음성의 무음 상태를 직접 감지합니다."),
    ]:
        story.append(KeepTogether([
            Paragraph(title_t, H2_S),
            Paragraph(desc_t, BODY_S),
            Spacer(1, 3*mm),
        ]))
    story.append(PageBreak())

    # ── 5장 정파 기능 ──────────────────────────────────────────────────────────────
    story.append(Paragraph("5장  정파 기능", H1_S))
    story.append(hr(AW))
    story.append(Paragraph(
        "정파(定波) 기능은 새벽 시간대의 방송 종료(정파)와 재개를 자동으로 감지하여 "
        "정파 시간 중에는 블랙/스틸 알람이 발생하지 않도록 합니다.",
        BODY_S))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("<b>자동 정파 동작 흐름</b>", H2_S))

    sf_rows = [
        [th_para("단계"), th_para("시점"), th_para("상태"), th_para("동작")],
        [td_bold("정파준비"),
         td_para("정파 시작 N시간 전"),
         td_para("주황색 표시"),
         td_para("감지 계속 동작, 담당자 인지 목적으로 색상 변경")],
        [td_bold("정파 진입"),
         td_para("정파 시작 시각"),
         td_para("빨간색 표시"),
         td_para("블랙/스틸 알람 억제 시작. 정파 감지영역이 스틸 상태이면 자동 진입")],
        [td_bold("정파해제준비"),
         td_para("정파 종료 N분 전"),
         td_para("주황색으로 전환"),
         td_para("정파 해제 임박 알림")],
        [td_bold("정파 해제"),
         td_para("정파 종료 시각"),
         td_para("정상 색상 전환"),
         td_para("블랙/스틸 알람 재활성화")],
        [td_bold("조기 해제"),
         td_para("정파 중 화면 변화 감지 시"),
         td_para("정상으로 전환"),
         td_para("조기 해제 기준 시간 경과 후 자동 정파 종료")],
    ]
    story.append(section_table(sf_rows, [0.15, 0.22, 0.18, 0.45]))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(
        "<b>참고:</b> 정파 감지영역을 반드시 설정해야 합니다. "
        "정파 시 화면에 표시되는 정지 이미지(컬러바, 로고 등) 영역을 지정하면 "
        "스틸 감지를 통한 자동 정파 진입이 가능합니다.",
        BODY_S))
    story.append(PageBreak())

    # ── 부록: FAQ ──────────────────────────────────────────────────────────────────
    story.append(Paragraph("부록  자주 묻는 질문 (FAQ)", H1_S))
    story.append(hr(AW))

    faqs = [
        ("Q. 메인 화면에 'NO SIGNAL INPUT'이 표시됩니다.",
         "캡쳐카드와 PC가 정상 연결되었는지 확인하세요. "
         "설정 → 영상설정 탭에서 포트 번호를 올바르게 설정했는지 확인하고 "
         "다른 포트 번호(0, 1, 2, 3)를 시도해보세요."),
        ("Q. 감지 ON 버튼이 비활성화됩니다.",
         "감지영역이 하나도 설정되지 않으면 감지를 시작할 수 없습니다. "
         "설정 → 비디오 영역 설정 탭에서 감지영역을 먼저 추가하세요."),
        ("Q. 텔레그램 알림이 수신되지 않습니다.",
         "① Bot Token과 Chat ID가 정확한지 확인  "
         "② 알림설정 탭의 [연결 테스트] 버튼으로 통신 확인  "
         "③ 해당 감지 이벤트의 텔레그램 알림이 체크되어 있는지 확인  "
         "④ PC의 인터넷 연결 상태 확인"),
        ("Q. 알람이 너무 자주 발생하거나 오감지가 많습니다.",
         "감도설정 탭에서 알람 발생 기준 시간을 늘리거나(예: 20초 → 40초), "
         "블랙 감지의 경우 움직임 감지 시 블랙 무시 기준값을 조정하세요. "
         "스틸 감지의 경우 연속 정상 프레임 수를 늘려 오감지를 줄일 수 있습니다."),
        ("Q. 정파 시간에도 알람이 발생합니다.",
         "정파설정 탭에서 정파 시간 구간과 적용 요일이 올바르게 설정되어 있는지 확인하세요. "
         "정파 감지영역이 선택되어 있지 않으면 자동 정파 진입이 되지 않을 수 있습니다."),
        ("Q. 프로그램이 예기치 않게 자동으로 재시작됩니다.",
         "알림설정 탭의 [자동 재시작] 기능이 활성화된 경우입니다. "
         "[예약 재시작 활성화] 체크를 해제하면 자동 재시작을 비활성화할 수 있습니다."),
    ]

    q_style = ps('q', fontName='MalgunBold', fontSize=10, textColor=DARK,
                 spaceBefore=5, spaceAfter=2, leading=14)
    a_style = ps('a', fontSize=9.5, textColor=GRAY_TEXT,
                 spaceAfter=3, leading=14, leftIndent=8)

    for q, a in faqs:
        story.append(Paragraph(q, q_style))
        story.append(Paragraph(f"A. {a}", a_style))
        story.append(HRFlowable(width=AW, thickness=0.4, color=BORDER,
                                spaceAfter=2*mm, spaceBefore=2*mm))

    # ── 헤더/푸터 ──────────────────────────────────────────────────────────────────
    def page_deco(canvas_obj, doc):
        canvas_obj.saveState()
        W_p, H_p = A4
        # 헤더
        canvas_obj.setFillColor(ORANGE)
        canvas_obj.rect(0, H_p - 11*mm, W_p, 11*mm, fill=1, stroke=0)
        canvas_obj.setFillColor(WHITE)
        canvas_obj.setFont('MalgunBold', 8)
        canvas_obj.drawString(15*mm, H_p - 7*mm, "KBS On-Air Monitoring v2.1.0  사용자 매뉴얼")
        canvas_obj.setFont('Malgun', 8)
        canvas_obj.drawRightString(W_p - 15*mm, H_p - 7*mm, str(doc.page))
        # 푸터
        canvas_obj.setFillColor(BORDER)
        canvas_obj.rect(0, 0, W_p, 8*mm, fill=1, stroke=0)
        canvas_obj.setFillColor(GRAY_TEXT)
        canvas_obj.setFont('Malgun', 7)
        canvas_obj.drawCentredString(W_p / 2, 2.5*mm, "KBS 기술본부 — 내부 배포용 문서")
        canvas_obj.restoreState()

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=MRG, rightMargin=MRG,
        topMargin=MRG + 11*mm,
        bottomMargin=MRG + 8*mm,
        title="KBS On-Air Monitoring v2.1.0 사용자 매뉴얼",
        author="minwoo@kbs.co.kr",
    )
    doc.build(story, onFirstPage=page_deco, onLaterPages=page_deco)
    print(f"  ✓ 전체 매뉴얼: {path}")


# =============================================================================
if __name__ == '__main__':
    print("PDF 생성 시작...")
    build_quick_ref()
    build_full_manual()
    print("\n완료! manual/ 폴더를 확인하세요.")
