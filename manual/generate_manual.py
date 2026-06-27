#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KBS Monitoring v2.1.0 사용자 매뉴얼 HTML 생성 스크립트"""

import base64
import os

BASE = r"G:\내 드라이브\A1. 개인 자료\A1. AI 연습\260418 KBS_Monitoring_v2"
IMG_DIR = os.path.join(BASE, "images")
OUT_FILE = os.path.join(BASE, "manual", "KBS_Monitoring_매뉴얼.html")

IMAGE_FILES = {
    "main":    "Snipaste_2026-05-03_20-36-23.png",
    "vid":     "Snipaste_2026-05-03_20-36-54.png",
    "vroi":    "Snipaste_2026-05-03_20-36-57.png",
    "aroi":    "Snipaste_2026-05-03_20-36-59.png",
    "sens":    "Snipaste_2026-05-03_20-37-01.png",
    "signoff": "Snipaste_2026-05-03_20-37-03.png",
    "notify":  "Snipaste_2026-05-03_20-37-06.png",
    "saveload":"Snipaste_2026-05-03_20-37-09.png",
}

def to_b64(filename):
    path = os.path.join(IMG_DIR, filename)
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{data}"

print("이미지 base64 인코딩 중...")
imgs = {k: to_b64(v) for k, v in IMAGE_FILES.items()}
print("완료.")

HTML = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KBS On-Air Monitoring v2.1.0 사용자 매뉴얼</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
  --orange: #D97757;
  --orange-light: #F4A27A;
  --orange-dark: #B5593A;
  --bg: #F8F9FA;
  --bg-white: #FFFFFF;
  --text: #1A1A2E;
  --text-secondary: #555577;
  --border: #E0E0E8;
  --sidebar-w: 240px;
  --radius: 8px;
  --shadow: 0 2px 12px rgba(0,0,0,0.08);
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: 'Noto Sans KR', -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 15px;
  line-height: 1.7;
}}

/* ── Sidebar ── */
#sidebar {{
  position: fixed;
  top: 0; left: 0;
  width: var(--sidebar-w);
  height: 100vh;
  background: var(--bg-white);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  z-index: 100;
  display: flex;
  flex-direction: column;
}}

.sidebar-header {{
  padding: 20px 16px 16px;
  border-bottom: 2px solid var(--orange);
  background: linear-gradient(135deg, #fff 0%, #fff8f5 100%);
}}

.sidebar-header h1 {{
  font-size: 13px;
  font-weight: 700;
  color: var(--orange);
  letter-spacing: -0.3px;
  line-height: 1.4;
}}

.sidebar-header .version {{
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 3px;
}}

nav {{
  flex: 1;
  padding: 12px 0;
}}

nav a {{
  display: block;
  padding: 7px 16px;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
  font-weight: 400;
  border-left: 3px solid transparent;
  transition: all 0.15s;
  line-height: 1.4;
}}

nav a:hover {{
  color: var(--orange);
  background: rgba(217,119,87,0.06);
  border-left-color: var(--orange-light);
}}

nav a.active {{
  color: var(--orange);
  background: rgba(217,119,87,0.1);
  border-left-color: var(--orange);
  font-weight: 500;
}}

nav .nav-section {{
  padding: 10px 16px 4px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #AAA;
}}

nav a.sub {{
  padding-left: 28px;
  font-size: 12.5px;
}}

/* ── Main content ── */
#content {{
  margin-left: var(--sidebar-w);
  padding: 40px 48px;
  max-width: 1000px;
}}

section {{
  margin-bottom: 60px;
  scroll-margin-top: 24px;
}}

h2 {{
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  border-bottom: 3px solid var(--orange);
  padding-bottom: 10px;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  gap: 10px;
}}

h2 .num {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px; height: 32px;
  background: var(--orange);
  color: white;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}}

h3 {{
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin: 32px 0 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}}

h3::before {{
  content: '';
  display: inline-block;
  width: 4px; height: 18px;
  background: var(--orange);
  border-radius: 2px;
}}

h4 {{
  font-size: 15px;
  font-weight: 700;
  color: var(--orange-dark);
  margin: 20px 0 10px;
}}

p {{ margin-bottom: 12px; color: var(--text-secondary); }}

/* ── Cards / boxes ── */
.card {{
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 20px;
  box-shadow: var(--shadow);
}}

.info-box {{
  background: #FFF8F5;
  border: 1px solid var(--orange-light);
  border-radius: var(--radius);
  padding: 14px 18px;
  margin: 16px 0;
  font-size: 14px;
  color: var(--text);
}}

.info-box .icon {{ color: var(--orange); font-weight: 700; margin-right: 6px; }}

.warn-box {{
  background: #FFF5F5;
  border: 1px solid #F5A0A0;
  border-radius: var(--radius);
  padding: 14px 18px;
  margin: 16px 0;
  font-size: 14px;
  color: #7A0000;
}}

/* ── Tables ── */
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0 20px;
  background: var(--bg-white);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow);
  font-size: 14px;
}}

thead {{
  background: var(--orange);
  color: white;
}}

thead th {{
  padding: 11px 14px;
  text-align: left;
  font-weight: 600;
  font-size: 13px;
}}

tbody tr {{ border-bottom: 1px solid var(--border); }}
tbody tr:last-child {{ border-bottom: none; }}
tbody tr:hover {{ background: #FFF8F5; }}
tbody td {{ padding: 10px 14px; vertical-align: top; color: var(--text-secondary); }}
tbody td:first-child {{ color: var(--text); font-weight: 500; }}

/* ── Images ── */
.img-wrap {{
  margin: 20px 0;
  text-align: center;
}}

.img-wrap img {{
  max-width: 100%;
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  border: 1px solid var(--border);
  cursor: zoom-in;
  transition: transform 0.15s;
}}

.img-wrap img:hover {{ transform: scale(1.01); }}

.img-caption {{
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}}

/* ── Keyboard shortcuts ── */
kbd {{
  display: inline-block;
  background: #F0F0F5;
  border: 1px solid #CCC;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 12px;
  font-family: monospace;
  color: var(--text);
  box-shadow: 0 1px 0 #BBB;
}}

/* ── Flow / steps ── */
.flow {{
  display: flex;
  align-items: stretch;
  gap: 0;
  margin: 20px 0;
  flex-wrap: wrap;
}}

.flow-step {{
  flex: 1;
  min-width: 120px;
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  text-align: center;
  font-size: 13px;
  font-weight: 500;
  position: relative;
  margin: 4px;
}}

.flow-step.orange {{ background: var(--orange); color: white; border-color: var(--orange); }}
.flow-step.red {{ background: #C0392B; color: white; border-color: #C0392B; }}
.flow-step.green {{ background: #27AE60; color: white; border-color: #27AE60; }}
.flow-step .sub {{ font-size: 11px; font-weight: 400; opacity: 0.85; margin-top: 3px; }}

/* ── Hamburger ── */
#menu-toggle {{
  display: none;
  position: fixed;
  top: 12px; left: 12px;
  z-index: 200;
  background: var(--orange);
  border: none;
  border-radius: 6px;
  width: 40px; height: 40px;
  cursor: pointer;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
}}

#menu-toggle span {{
  display: block;
  width: 20px; height: 2px;
  background: white;
  border-radius: 2px;
  transition: 0.3s;
}}

/* ── Lightbox ── */
#lightbox {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
  z-index: 1000;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}}

#lightbox.open {{ display: flex; }}

#lightbox img {{
  max-width: 92vw;
  max-height: 90vh;
  border-radius: 8px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.5);
  cursor: default;
}}

#lightbox-close {{
  position: absolute;
  top: 16px; right: 20px;
  color: white;
  font-size: 32px;
  cursor: pointer;
  line-height: 1;
  opacity: 0.8;
}}

#lightbox-close:hover {{ opacity: 1; }}

/* ── Quick ref ── */
.quick-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin: 16px 0;
}}

.quick-item {{
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  font-size: 13px;
}}

.quick-item .num-badge {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px; height: 22px;
  background: var(--orange);
  color: white;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  margin-right: 6px;
}}

.quick-item .label {{ font-weight: 700; color: var(--text); }}
.quick-item .desc {{ color: var(--text-secondary); margin-top: 3px; font-size: 12px; }}

/* ── FAQ ── */
.faq-item {{
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 12px;
  overflow: hidden;
}}

.faq-q {{
  padding: 14px 18px;
  font-weight: 700;
  color: var(--text);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
}}

.faq-q::after {{ content: '▼'; font-size: 11px; color: var(--orange); transition: transform 0.2s; }}
.faq-item.open .faq-q::after {{ transform: rotate(180deg); }}

.faq-a {{
  display: none;
  padding: 14px 18px;
  background: #FFF8F5;
  border-top: 1px solid var(--border);
  font-size: 14px;
  color: var(--text-secondary);
}}

.faq-item.open .faq-a {{ display: block; }}

/* ── @media print ── */
@media print {{
  #sidebar, #menu-toggle {{ display: none !important; }}
  #content {{
    margin-left: 0;
    padding: 20px;
    max-width: 100%;
  }}
  .img-wrap img {{ box-shadow: none; cursor: default; }}
  .faq-a {{ display: block !important; }}
  #lightbox {{ display: none !important; }}
}}

/* ── Responsive ── */
@media (max-width: 768px) {{
  #menu-toggle {{ display: flex; }}

  #sidebar {{
    transform: translateX(-100%);
    transition: transform 0.3s ease;
  }}

  #sidebar.open {{ transform: translateX(0); }}

  #content {{
    margin-left: 0;
    padding: 64px 20px 40px;
  }}
}}

/* Scrollbar */
#sidebar::-webkit-scrollbar {{ width: 4px; }}
#sidebar::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 2px; }}
</style>
</head>
<body>

<!-- Hamburger -->
<button id="menu-toggle" onclick="toggleSidebar()" aria-label="메뉴">
  <span></span><span></span><span></span>
</button>

<!-- Sidebar -->
<aside id="sidebar">
  <div class="sidebar-header">
    <h1>KBS On-Air<br>Monitoring</h1>
    <div class="version">v2.1.0 사용자 매뉴얼</div>
  </div>
  <nav>
    <a href="#s0" onclick="closeSidebar()">0. 빠른 참조</a>
    <a href="#s1" onclick="closeSidebar()">1. 개요</a>
    <a href="#s2" onclick="closeSidebar()">2. 메인 화면</a>
    <a href="#s3" onclick="closeSidebar()">3. 설정 다이얼로그</a>
    <a href="#s3-1" class="sub" onclick="closeSidebar()">3.1 영상설정</a>
    <a href="#s3-2" class="sub" onclick="closeSidebar()">3.2 비디오 영역 설정</a>
    <a href="#s3-3" class="sub" onclick="closeSidebar()">3.3 오디오 레벨미터 영역</a>
    <a href="#s3-4" class="sub" onclick="closeSidebar()">3.4 감도설정</a>
    <a href="#s3-5" class="sub" onclick="closeSidebar()">3.5 정파설정</a>
    <a href="#s3-6" class="sub" onclick="closeSidebar()">3.6 알림설정</a>
    <a href="#s3-7" class="sub" onclick="closeSidebar()">3.7 저장/불러오기</a>
    <a href="#s4" onclick="closeSidebar()">4. 감지 유형 설명</a>
    <a href="#s5" onclick="closeSidebar()">5. 정파 기능</a>
    <a href="#s6" onclick="closeSidebar()">6. FAQ</a>
  </nav>
</aside>

<!-- Main -->
<main id="content">

<!-- ═══ 0. 빠른 참조 ═══ -->
<section id="s0">
  <h2><span class="num">0</span>빠른 참조</h2>

  <div class="img-wrap">
    <img src="{imgs['main']}" alt="메인 화면" onclick="openLightbox(this)">
    <div class="img-caption">▲ KBS On-Air Monitoring v2.1.0 메인 화면</div>
  </div>

  <h3>주요 UI 요소</h3>
  <div class="quick-grid">
    <div class="quick-item">
      <span class="num-badge">①</span><span class="label">시스템 성능</span>
      <div class="desc">CPU / RAM / GPU 실시간 표시</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">②</span><span class="label">현재시간</span>
      <div class="desc">HH:MM:SS 실시간 표시</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">③</span><span class="label">Embedded Audio 레벨미터</span>
      <div class="desc">HDMI 입력 오디오 L/R 세그먼트</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">④</span><span class="label">감지 현황</span>
      <div class="desc">V(영상) · A(오디오) · EA(임베디드) 카운터</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑤</span><span class="label">감지 ON 토글</span>
      <div class="desc">감지 시작·중지 (활성 시 주황색)</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑥</span><span class="label">영역 표시 ON/OFF</span>
      <div class="desc">감지영역 오버레이 표시 전환</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑦</span><span class="label">Mute</span>
      <div class="desc">알림음 끄기 (감지는 계속 진행)</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑧</span><span class="label">알람 확인 ACK</span>
      <div class="desc">발생 알람 일괄 확인 처리</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑨</span><span class="label">1TV · 2TV 정파</span>
      <div class="desc">정파 상태 표시 및 수동 전환</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑩</span><span class="label">⚙ / 다크모드 / 창 모드</span>
      <div class="desc">설정, 테마, 화면 모드 전환</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑪</span><span class="label">영상 뷰</span>
      <div class="desc">캡쳐 카드 실시간 영상 표시</div>
    </div>
    <div class="quick-item">
      <span class="num-badge">⑫</span><span class="label">SYSTEM LOG 패널</span>
      <div class="desc">실시간 감지 이벤트 및 시스템 로그</div>
    </div>
  </div>

  <h3>설정 탭 요약</h3>
  <table>
    <thead><tr><th>탭</th><th>주요 기능</th></tr></thead>
    <tbody>
      <tr><td>3.1 영상설정</td><td>캡쳐 포트, 자동 녹화, 파일 저장 설정</td></tr>
      <tr><td>3.2 비디오 영역 설정</td><td>블랙/스틸 감지 대상 영역(V1~) 드래그 지정</td></tr>
      <tr><td>3.3 오디오 레벨미터 영역</td><td>VU 미터 감지 영역(A1~A5) 지정</td></tr>
      <tr><td>3.4 감도설정</td><td>블랙·스틸·오디오·임베디드 감도 파라미터</td></tr>
      <tr><td>3.5 정파설정</td><td>1TV/2TV 정파 시간대·요일·알림음 설정</td></tr>
      <tr><td>3.6 알림설정</td><td>알림음 파일, 텔레그램 봇, 자동 재시작</td></tr>
      <tr><td>3.7 저장/불러오기</td><td>설정 JSON 내보내기·가져오기·초기화</td></tr>
    </tbody>
  </table>
</section>

<!-- ═══ 1. 개요 ═══ -->
<section id="s1">
  <h2><span class="num">1</span>개요</h2>

  <div class="card">
    <h4>목적</h4>
    <p>KBS 방송 송출 이상 — 블랙(Black), 스틸(Still), 오디오 무음, 임베디드 오디오 무음 — 을 자동으로 감지하고, 화면 알람·알림음·텔레그램 메시지로 즉시 통보하는 16채널 On-Air 모니터링 시스템입니다.</p>
  </div>

  <h3>시스템 요구사항</h3>
  <table>
    <thead><tr><th>항목</th><th>내용</th></tr></thead>
    <tbody>
      <tr><td>운영체제</td><td>Windows 10/11 (64-bit)</td></tr>
      <tr><td>캡쳐 장치</td><td>USB 또는 PCIe HDMI 캡쳐 카드 (DirectShow 호환)</td></tr>
      <tr><td>Python</td><td>3.10 이상 (실행 파일 사용 시 불필요)</td></tr>
      <tr><td>ffmpeg</td><td>자동 녹화 시 필요 (<code>winget install ffmpeg</code>)</td></tr>
      <tr><td>GPU</td><td>NVIDIA GPU 권장 (없으면 N/A 표시)</td></tr>
    </tbody>
  </table>

  <h3>실행 및 종료</h3>
  <div class="info-box"><span class="icon">▶</span><strong>실행:</strong> <code>KBS_Monitoring.exe</code> 더블클릭, 또는 터미널에서 <code>python main.py</code></div>
  <div class="info-box"><span class="icon">■</span><strong>종료:</strong> 창 닫기 버튼(×) — 설정이 자동 저장됩니다.</div>
  <div class="warn-box">⚠ 강제 종료(프로세스 킬) 시 SharedMemory가 잔류할 수 있습니다. 재실행 시 자동으로 정리됩니다.</div>
</section>

<!-- ═══ 2. 메인 화면 ═══ -->
<section id="s2">
  <h2><span class="num">2</span>메인 화면</h2>

  <div class="img-wrap">
    <img src="{imgs['main']}" alt="메인 화면 전체" onclick="openLightbox(this)">
    <div class="img-caption">▲ 메인 화면 전체 구성 (클릭 시 확대)</div>
  </div>

  <h3>상단바 항목</h3>
  <table>
    <thead><tr><th>요소</th><th>설명</th><th>비고</th></tr></thead>
    <tbody>
      <tr><td>시스템 성능</td><td>CPU / RAM / GPU 실시간 사용률</td><td>GPU는 NVIDIA만 표시</td></tr>
      <tr><td>현재시간</td><td>HH:MM:SS 실시간</td><td>—</td></tr>
      <tr><td>EA 레벨미터</td><td>Embedded Audio L/R 세그먼트 VU 미터</td><td>33ms 주기 갱신</td></tr>
      <tr><td>V / A / EA 카운터</td><td>누적 감지 횟수 (영상/오디오/임베디드)</td><td>ACK 시 초기화</td></tr>
      <tr><td>감지 ON</td><td>감지 시작·중지 토글</td><td>활성 시 주황색</td></tr>
      <tr><td>영역 표시</td><td>감지영역 오버레이 ON/OFF</td><td>—</td></tr>
      <tr><td>Mute</td><td>알림음 끄기 (감지·기록은 계속)</td><td>—</td></tr>
      <tr><td>ACK</td><td>발생한 모든 알람 일괄 확인</td><td>—</td></tr>
      <tr><td>1TV / 2TV</td><td>정파 상태 표시 및 수동 전환</td><td>주황·빨강 색상으로 상태 구분</td></tr>
      <tr><td>⚙ 설정</td><td>설정 다이얼로그 열기</td><td>—</td></tr>
      <tr><td>다크모드</td><td>다크/라이트 테마 전환</td><td>—</td></tr>
      <tr><td>창 모드</td><td>전체화면·창 모드 전환</td><td>—</td></tr>
    </tbody>
  </table>

  <h3>영상 뷰</h3>
  <p>캡쳐 카드에서 수신한 영상을 실시간으로 표시합니다. 감지영역 오버레이(영역 표시 ON 시)가 영상 위에 겹쳐 표시됩니다. 신호가 없으면 <strong>NO SIGNAL INPUT</strong> 메시지가 나타납니다.</p>

  <h3>SYSTEM LOG 패널</h3>
  <p>감지 이벤트와 시스템 상태를 실시간으로 표시합니다. 최대 500개 항목을 유지하며 오래된 항목은 자동 제거됩니다.</p>
  <table>
    <thead><tr><th>필터</th><th>표시 내용</th></tr></thead>
    <tbody>
      <tr><td>ALL</td><td>모든 로그</td></tr>
      <tr><td>ERROR</td><td>오류 메시지</td></tr>
      <tr><td>STILL</td><td>스틸(정지화면) 감지 이벤트</td></tr>
      <tr><td>AUDIO</td><td>오디오 레벨미터 감지 이벤트</td></tr>
      <tr><td>EMBED</td><td>임베디드 오디오 감지 이벤트</td></tr>
      <tr><td>INFO</td><td>일반 정보 메시지</td></tr>
      <tr><td>DEBUG</td><td>디버그 상세 메시지</td></tr>
    </tbody>
  </table>
</section>

<!-- ═══ 3. 설정 다이얼로그 ═══ -->
<section id="s3">
  <h2><span class="num">3</span>설정 다이얼로그</h2>
  <p>상단바의 <strong>⚙ 설정</strong> 버튼을 클릭하면 7개 탭으로 구성된 설정 다이얼로그가 열립니다. 설정은 창 닫기 시 자동 저장됩니다.</p>

  <!-- 3.1 -->
  <h3 id="s3-1">3.1 영상설정</h3>
  <div class="img-wrap">
    <img src="{imgs['vid']}" alt="설정 > 영상설정" onclick="openLightbox(this)">
    <div class="img-caption">▲ 설정 > 영상설정 탭 (클릭 시 확대)</div>
  </div>

  <table>
    <thead><tr><th>항목</th><th>설명</th><th>기본값</th></tr></thead>
    <tbody>
      <tr><td>캡쳐 포트</td><td>캡쳐 카드 인덱스 (0~3)</td><td>0</td></tr>
      <tr><td>파일 입력</td><td>MP4 파일로 대체 입력 (테스트용)</td><td>비활성</td></tr>
      <tr><td>자동 녹화 — 저장 폴더</td><td>녹화 파일 저장 경로</td><td>./recordings</td></tr>
      <tr><td>사전 버퍼</td><td>알람 발생 전 녹화 시작 시간 (1~30초)</td><td>10초</td></tr>
      <tr><td>이후 녹화</td><td>알람 종료 후 추가 녹화 시간 (1~60초)</td><td>30초</td></tr>
      <tr><td>최대 보관 기간</td><td>녹화 파일 자동 삭제 기준 (1~365일)</td><td>7일</td></tr>
      <tr><td>해상도</td><td>녹화 해상도 (권장: 960×540)</td><td>960×540</td></tr>
      <tr><td>FPS</td><td>녹화 프레임레이트 (권장: 10fps)</td><td>10fps</td></tr>
    </tbody>
  </table>

  <div class="info-box"><span class="icon">💡</span>ffmpeg가 설치되지 않으면 임베디드 오디오 없이 비디오 전용 MP4로 저장됩니다.</div>

  <!-- 3.2 -->
  <h3 id="s3-2">3.2 비디오 영역 설정</h3>
  <div class="img-wrap">
    <img src="{imgs['vroi']}" alt="설정 > 비디오 영역 설정" onclick="openLightbox(this)">
    <div class="img-caption">▲ 설정 > 비디오 영역 설정 탭 (클릭 시 확대)</div>
  </div>

  <p><strong>[비디오 감지영역 편집]</strong> 버튼을 클릭하면 영상 위에서 드래그로 영역을 지정합니다. 라벨은 V1, V2, V3… 순으로 자동 지정됩니다.</p>

  <h4>편집 단축키</h4>
  <table>
    <thead><tr><th>동작</th><th>단축키</th></tr></thead>
    <tbody>
      <tr><td>새 영역 추가</td><td>빈 곳에서 <kbd>드래그</kbd></td></tr>
      <tr><td>영역 이동</td><td>영역 위에서 <kbd>드래그</kbd></td></tr>
      <tr><td>10px 이동</td><td><kbd>↑</kbd> <kbd>↓</kbd> <kbd>←</kbd> <kbd>→</kbd></td></tr>
      <tr><td>1px 정밀 이동</td><td><kbd>Shift</kbd> + <kbd>↑↓←→</kbd></td></tr>
      <tr><td>크기 10px 조정</td><td><kbd>Ctrl</kbd> + <kbd>↑↓←→</kbd></td></tr>
      <tr><td>영역 복사</td><td><kbd>Ctrl</kbd> + <kbd>D</kbd></td></tr>
      <tr><td>영역 삭제</td><td><kbd>Delete</kbd></td></tr>
      <tr><td>다중 선택</td><td><kbd>Ctrl</kbd> + <kbd>클릭</kbd></td></tr>
      <tr><td>복사하며 이동</td><td>선택 후 <kbd>Ctrl</kbd> + <kbd>드래그</kbd></td></tr>
    </tbody>
  </table>

  <!-- 3.3 -->
  <h3 id="s3-3">3.3 오디오 레벨미터 영역 설정</h3>
  <div class="img-wrap">
    <img src="{imgs['aroi']}" alt="설정 > 오디오 레벨미터 영역 설정" onclick="openLightbox(this)">
    <div class="img-caption">▲ 설정 > 오디오 레벨미터 영역 설정 탭 (클릭 시 확대)</div>
  </div>

  <p>방송 화면에 표시되는 VU 미터 위치를 감지 영역으로 지정합니다. 라벨은 A1~A5로 자동 지정됩니다.</p>
  <p>HSV 색상 방식으로 레벨 미터의 초록색 패턴을 감지합니다. 색상 범위는 <strong>3.4 감도설정</strong> 탭의 <em>오디오 레벨미터 감지 HSV</em> 섹션에서 조정합니다.</p>

  <div class="info-box"><span class="icon">💡</span>단축키는 비디오 영역 설정(3.2)과 동일합니다.</div>

  <!-- 3.4 -->
  <h3 id="s3-4">3.4 감도설정</h3>
  <div class="img-wrap">
    <img src="{imgs['sens']}" alt="설정 > 감도설정" onclick="openLightbox(this)">
    <div class="img-caption">▲ 설정 > 감도설정 탭 (클릭 시 확대)</div>
  </div>

  <h4>블랙 감지</h4>
  <table>
    <thead><tr><th>파라미터</th><th>범위</th><th>기본값</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>밝기 임계값</td><td>0~255</td><td>5</td><td>이 값 이하이면 "어두운 픽셀"로 판정</td></tr>
      <tr><td>어두운 픽셀 비율</td><td>50~100%</td><td>98%</td><td>이 비율 이상이면 블랙으로 판정</td></tr>
      <tr><td>움직임 무시 기준</td><td>0.0~5.0%</td><td>0.2%</td><td>화면 전환 오감지 방지 (변화 픽셀 비율)</td></tr>
      <tr><td>알람 발생 기준</td><td>초</td><td>5초</td><td>이 시간 지속 시 알람 발생</td></tr>
      <tr><td>알림음 지속</td><td>초</td><td>60초</td><td>알림음이 울리는 최대 시간</td></tr>
    </tbody>
  </table>

  <h4>스틸 감지</h4>
  <table>
    <thead><tr><th>파라미터</th><th>범위</th><th>기본값</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>픽셀 차이 임계값</td><td>0~255</td><td>4</td><td>프레임 간 픽셀 변화 감지 최소값</td></tr>
      <tr><td>블록 변화 비율</td><td>%</td><td>10%</td><td>이 비율 미만이면 정지 화면으로 판정</td></tr>
      <tr><td>연속 정상 프레임</td><td>프레임</td><td>3</td><td>정상 복귀 판정에 필요한 연속 정상 프레임 수</td></tr>
      <tr><td>알람 발생 기준</td><td>초</td><td>120초</td><td>이 시간 지속 시 알람 발생</td></tr>
    </tbody>
  </table>

  <h4>오디오 레벨미터 감지 (HSV)</h4>
  <table>
    <thead><tr><th>파라미터</th><th>기본값</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>H 범위 (색조)</td><td>40~95</td><td>초록 계열 색상 범위 (OpenCV 기준 0~180)</td></tr>
      <tr><td>S 범위 (채도)</td><td>80~255</td><td>채도 범위</td></tr>
      <tr><td>V 범위 (명도)</td><td>60~255</td><td>명도 범위</td></tr>
      <tr><td>감지 픽셀 비율</td><td>5%</td><td>이 비율 이상이면 레벨 있음으로 판정</td></tr>
      <tr><td>복구 대기</td><td>2초</td><td>정상 복귀 후 추가 대기 시간</td></tr>
    </tbody>
  </table>

  <h4>임베디드 오디오 감지 (무음)</h4>
  <table>
    <thead><tr><th>파라미터</th><th>기본값</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>무음 임계값</td><td>-50 dB</td><td>이 값 이하이면 무음으로 판정</td></tr>
      <tr><td>알람 발생 기준</td><td>60초</td><td>이 시간 지속 시 알람 발생</td></tr>
    </tbody>
  </table>

  <!-- 3.5 -->
  <h3 id="s3-5">3.5 정파설정</h3>
  <div class="img-wrap">
    <img src="{imgs['signoff']}" alt="설정 > 정파설정" onclick="openLightbox(this)">
    <div class="img-caption">▲ 설정 > 정파설정 탭 (클릭 시 확대)</div>
  </div>

  <p>그룹 1(1TV)과 그룹 2(2TV) 각각 별도로 설정합니다.</p>
  <table>
    <thead><tr><th>항목</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>정파 시간 구간</td><td>시작 ~ 종료 시각 지정 (익일 옵션 포함)</td></tr>
      <tr><td>정파준비 활성화</td><td>정파 N시간 전 준비 상태 전환</td></tr>
      <tr><td>정파해제준비 활성화</td><td>정파 종료 N분 전 해제 준비 상태 전환</td></tr>
      <tr><td>정파 진입 기준 시간</td><td>스틸 지속 시 자동 정파 진입 (초)</td></tr>
      <tr><td>조기 해제 기준 시간</td><td>정파 중 화면 변화 감지 시 자동 종료 (초)</td></tr>
      <tr><td>적용 요일</td><td>전체 선택/해제 버튼 포함</td></tr>
      <tr><td>정파 감지영역</td><td>정파 판정에 사용할 감지영역 선택 (미설정 시 경고)</td></tr>
      <tr><td>정파준비 알림음</td><td>정파 준비 시작 시 재생할 WAV 파일</td></tr>
      <tr><td>정파 진입 알림음</td><td>정파 진입 시 재생할 WAV 파일</td></tr>
      <tr><td>정파 해제 알림음</td><td>정파 해제 시 재생할 WAV 파일</td></tr>
    </tbody>
  </table>

  <div class="warn-box">⚠ 정파 감지영역이 설정되지 않으면 자동 정파 진입이 동작하지 않습니다. 반드시 영역을 지정하세요.</div>

  <!-- 3.6 -->
  <h3 id="s3-6">3.6 알림설정</h3>
  <div class="img-wrap">
    <img src="{imgs['notify']}" alt="설정 > 알림설정" onclick="openLightbox(this)">
    <div class="img-caption">▲ 설정 > 알림설정 탭 (클릭 시 확대)</div>
  </div>

  <h4>알림음</h4>
  <p>WAV 형식 파일을 지정합니다. 찾아보기·초기화·테스트 버튼으로 관리합니다.</p>

  <h4>텔레그램 봇</h4>
  <table>
    <thead><tr><th>항목</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>Bot Token</td><td>BotFather에서 발급받은 API 토큰</td></tr>
      <tr><td>Chat ID</td><td>감지 알림 수신 채팅방 ID</td></tr>
      <tr><td>시스템 알림 Chat ID</td><td>프로세스 크래시·재시작 등 시스템 알림 채팅방</td></tr>
      <tr><td>연결 테스트</td><td>현재 설정으로 테스트 메시지 발송</td></tr>
    </tbody>
  </table>

  <h4>텔레그램 알림 이벤트</h4>
  <table>
    <thead><tr><th>이벤트</th><th>기본</th></tr></thead>
    <tbody>
      <tr><td>블랙 감지</td><td>ON</td></tr>
      <tr><td>스틸 감지</td><td>ON</td></tr>
      <tr><td>오디오 레벨미터 감지</td><td>ON</td></tr>
      <tr><td>임베디드 오디오 감지</td><td>ON</td></tr>
      <tr><td>정파 이벤트</td><td>ON</td></tr>
      <tr><td>시스템 알림 (재spawn 등)</td><td>ON</td></tr>
    </tbody>
  </table>

  <h4>기타 설정</h4>
  <table>
    <thead><tr><th>항목</th><th>기본값</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>재전송 대기</td><td>60초</td><td>동일 이벤트 중복 알림 방지 대기 시간</td></tr>
      <tr><td>예약 재시작</td><td>비활성</td><td>지정 시각에 프로그램 자동 재시작</td></tr>
      <tr><td>기준 시각 / 주기</td><td>—</td><td>재시작 시각과 반복 주기 설정</td></tr>
      <tr><td>제외 시간대</td><td>—</td><td>재시작을 건너뛸 시간대 지정</td></tr>
    </tbody>
  </table>

  <!-- 3.7 -->
  <h3 id="s3-7">3.7 저장/불러오기</h3>
  <div class="img-wrap">
    <img src="{imgs['saveload']}" alt="설정 > 저장/불러오기" onclick="openLightbox(this)">
    <div class="img-caption">▲ 설정 > 저장/불러오기 탭 (클릭 시 확대)</div>
  </div>

  <table>
    <thead><tr><th>기능</th><th>설명</th></tr></thead>
    <tbody>
      <tr><td>현재 설정 저장</td><td>모든 설정을 JSON 파일로 내보내기</td></tr>
      <tr><td>설정 파일 불러오기</td><td>저장된 JSON 파일을 불러와 즉시 적용</td></tr>
      <tr><td>공장 초기화</td><td>모든 설정을 기본값으로 되돌림 (⚠ 되돌릴 수 없음)</td></tr>
    </tbody>
  </table>

  <div class="warn-box">⚠ <strong>공장 초기화</strong>는 감지영역, 정파설정, 텔레그램 설정을 포함한 모든 설정이 삭제됩니다. 실행 전 반드시 백업(현재 설정 저장)하세요.</div>
</section>

<!-- ═══ 4. 감지 유형 ═══ -->
<section id="s4">
  <h2><span class="num">4</span>감지 유형 설명</h2>

  <div class="card">
    <h4>블랙 감지 (Black Detection)</h4>
    <p>감지영역 내 픽셀 밝기를 분석합니다. 어두운 픽셀(밝기 ≤ 임계값)의 비율이 설정값 이상이고, 일정 시간 이상 지속되면 알람을 발생시킵니다. 화면 전환 오감지를 방지하기 위해 움직임(픽셀 변화율)이 임계값 이상이면 블랙 판정을 잠시 보류합니다.</p>
  </div>

  <div class="card">
    <h4>스틸 감지 (Still Detection)</h4>
    <p>연속 프레임 간 블록 단위 픽셀 변화량을 분석합니다. 변화가 있는 블록의 비율이 설정값 미만으로 오래 지속되면 정지 화면으로 판정하여 알람을 발생시킵니다. 연속 정상 프레임 수 조건을 통해 복귀 오판정을 방지합니다.</p>
  </div>

  <div class="card">
    <h4>오디오 레벨미터 감지 (HSV Detection)</h4>
    <p>방송 화면 내 VU 미터 영역을 감지영역으로 지정한 뒤, HSV 색공간에서 초록색 계열 픽셀 비율을 측정합니다. 초록색 픽셀이 충분하면 오디오 레벨이 존재한다고 판정하고, 부족하면 무음으로 판정합니다.</p>
  </div>

  <div class="card">
    <h4>임베디드 오디오 감지 (Embedded Audio)</h4>
    <p>캡쳐 카드를 통해 들어오는 HDMI 임베디드 오디오 신호의 음량(dB)을 직접 측정합니다. 음량이 무음 임계값 이하로 지속되면 알람을 발생시킵니다. sounddevice 라이브러리가 없으면 더미 신호로 동작합니다.</p>
  </div>

  <table>
    <thead><tr><th>감지 유형</th><th>분석 방식</th><th>표기</th></tr></thead>
    <tbody>
      <tr><td>블랙 감지</td><td>밝기 기반 픽셀 비율</td><td>V (영상)</td></tr>
      <tr><td>스틸 감지</td><td>연속 프레임 블록 변화량</td><td>V (영상)</td></tr>
      <tr><td>오디오 레벨미터</td><td>HSV 색공간 픽셀 비율</td><td>A (오디오)</td></tr>
      <tr><td>임베디드 오디오</td><td>HDMI 오디오 신호 dB 측정</td><td>EA (임베디드)</td></tr>
    </tbody>
  </table>
</section>

<!-- ═══ 5. 정파 기능 ═══ -->
<section id="s5">
  <h2><span class="num">5</span>정파 기능</h2>

  <p>방송 정파 시간대를 사전에 설정하여, 블랙·스틸 알람이 억제되고 정파 전용 알림음이 재생됩니다.</p>

  <h3>정파 상태 흐름</h3>
  <div class="flow">
    <div class="flow-step">
      정상<br>
      <div class="sub">기본 감지 운용</div>
    </div>
    <div class="flow-step orange">
      정파준비<br>
      <div class="sub">N시간 전, 주황색</div>
    </div>
    <div class="flow-step red">
      정파 진입<br>
      <div class="sub">시작 시각, 빨간색<br>블랙·스틸 억제</div>
    </div>
    <div class="flow-step orange">
      정파해제준비<br>
      <div class="sub">종료 N분 전, 주황색</div>
    </div>
    <div class="flow-step green">
      정파 해제<br>
      <div class="sub">종료 시각, 정상 복귀</div>
    </div>
  </div>

  <h3>정파 동작 상세</h3>
  <table>
    <thead><tr><th>상태</th><th>색상</th><th>동작</th></tr></thead>
    <tbody>
      <tr><td>정파준비</td><td>주황색</td><td>알림음 재생, 오퍼레이터에게 정파 준비 알림</td></tr>
      <tr><td>정파 진입</td><td>빨간색</td><td>블랙·스틸 알람 억제, 정파 알림음 재생, 텔레그램 발송</td></tr>
      <tr><td>정파해제준비</td><td>주황색</td><td>정파 해제 예정 알림</td></tr>
      <tr><td>정파 해제</td><td>초록색</td><td>알람 억제 해제, 정상 감지 복귀, 해제 알림음 재생</td></tr>
    </tbody>
  </table>

  <h3>조기 해제</h3>
  <p>정파 시간 중 감지영역에서 화면 변화(방송 재개)가 조기 해제 기준 시간 이상 감지되면, 정파 종료 시각 이전이라도 자동으로 정파가 해제됩니다.</p>

  <div class="info-box"><span class="icon">💡</span>1TV와 2TV는 독립적으로 운용됩니다. 각각 다른 시간대, 요일, 감지영역을 설정할 수 있습니다.</div>
</section>

<!-- ═══ 6. FAQ ═══ -->
<section id="s6">
  <h2><span class="num">6</span>FAQ</h2>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. 화면에 "NO SIGNAL INPUT"이 표시됩니다.</div>
    <div class="faq-a">캡쳐 카드와 케이블 연결을 확인하세요. 설정 &gt; 영상설정에서 <strong>캡쳐 포트</strong> 번호를 0, 1, 2, 3 중 다른 값으로 변경해 보세요.</div>
  </div>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. "감지 ON" 버튼이 비활성화(회색)입니다.</div>
    <div class="faq-a">비디오 감지영역이 하나 이상 설정되어 있어야 감지가 활성화됩니다. 설정 &gt; 비디오 영역 설정 탭에서 영역을 먼저 추가하세요.</div>
  </div>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. 텔레그램 알림이 수신되지 않습니다.</div>
    <div class="faq-a">① Bot Token과 Chat ID가 정확한지 확인하세요. ② 알림설정 탭에서 <strong>연결 테스트</strong>를 눌러 테스트 메시지가 수신되는지 확인하세요. ③ 해당 이벤트의 텔레그램 알림 체크박스가 켜져 있는지 확인하세요.</div>
  </div>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. 오감지가 너무 많습니다.</div>
    <div class="faq-a">① 감도설정에서 <strong>알람 발생 기준 시간</strong>을 늘리세요 (예: 블랙 5초 → 15초). ② 블랙 감지의 <strong>움직임 무시 기준값</strong>을 높여 화면 전환 오감지를 줄이세요. ③ 스틸 감지의 <strong>블록 변화 비율</strong>을 낮추세요.</div>
  </div>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. 정파 중에도 알람이 발생합니다.</div>
    <div class="faq-a">정파설정 탭에서 ① 정파 <strong>시작·종료 시각</strong>, ② <strong>적용 요일</strong>, ③ <strong>정파 감지영역</strong>이 올바르게 설정되었는지 확인하세요. 정파 감지영역이 비어 있으면 자동 정파 진입이 동작하지 않습니다.</div>
  </div>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. 프로그램이 자동으로 재시작됩니다.</div>
    <div class="faq-a">알림설정 탭의 <strong>자동 재시작</strong> 기능이 활성화되어 있을 수 있습니다. 해당 옵션을 비활성화하면 예약 재시작이 중지됩니다.</div>
  </div>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. 녹화 파일이 저장되지 않습니다.</div>
    <div class="faq-a">① 영상설정 탭에서 <strong>저장 폴더</strong> 경로가 유효한지 확인하세요. ② 디스크 여유 공간을 확인하세요. ③ ffmpeg가 설치되어 있지 않으면 임베디드 오디오 없이 저장됩니다 (<code>winget install ffmpeg</code>).</div>
  </div>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Q. GPU 정보가 N/A로 표시됩니다.</div>
    <div class="faq-a">NVIDIA GPU가 없거나 gputil 라이브러리가 설치되지 않은 경우입니다. 시스템 동작에는 영향이 없습니다.</div>
  </div>
</section>

</main>

<!-- Lightbox -->
<div id="lightbox" onclick="closeLightbox()">
  <span id="lightbox-close" onclick="closeLightbox()">×</span>
  <img id="lightbox-img" src="" alt="" onclick="event.stopPropagation()">
</div>

<script>
// ── Sidebar highlight on scroll ──
const sections = document.querySelectorAll('section[id]');
const navLinks = document.querySelectorAll('nav a');

const observer = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      navLinks.forEach(a => a.classList.remove('active'));
      const id = e.target.id;
      const link = document.querySelector(`nav a[href="#${{id}}"]`);
      if (link) link.classList.add('active');
    }}
  }});
}}, {{ rootMargin: '-20% 0px -70% 0px' }});

sections.forEach(s => observer.observe(s));

// ── Smooth scroll ──
document.querySelectorAll('nav a').forEach(a => {{
  a.addEventListener('click', e => {{
    const href = a.getAttribute('href');
    if (href && href.startsWith('#')) {{
      e.preventDefault();
      const target = document.querySelector(href);
      if (target) target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}
  }});
}});

// ── Lightbox ──
function openLightbox(img) {{
  document.getElementById('lightbox-img').src = img.src;
  document.getElementById('lightbox').classList.add('open');
}}

function closeLightbox() {{
  document.getElementById('lightbox').classList.remove('open');
}}

document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') closeLightbox();
}});

// ── FAQ accordion ──
function toggleFaq(el) {{
  el.parentElement.classList.toggle('open');
}}

// ── Mobile sidebar ──
function toggleSidebar() {{
  document.getElementById('sidebar').classList.toggle('open');
}}

function closeSidebar() {{
  document.getElementById('sidebar').classList.remove('open');
}}
</script>
</body>
</html>"""

print(f"HTML 파일 쓰는 중... ({len(HTML):,} 글자)")
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"완료: {OUT_FILE}")
print(f"파일 크기: {os.path.getsize(OUT_FILE):,} bytes")
