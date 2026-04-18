# KBS Monitoring v2 — 개발 규칙 (CLAUDE.md)

## 프로젝트 개요
- KBS 16채널 방송 모니터링 시스템 v2
- v1(KBS Peacock v1.6.x)의 "장기 운영 시 감지 루프 freeze" 문제를 근본 해결하기 위해 재작성
- **핵심 변경**: multiprocessing 기반 아키텍처 (UI/감지 프로세스 분리)

## UI 디자인 레퍼런스
- 목업 디자인 파일 위치: `design/` 폴더 (Claude Design 2026-04-18 제작)
- **색상 시스템**: `design/styles.css` — 모든 색상 토큰, 컴포넌트 스타일 정의
- **UI 구조**: `design/topbar.jsx`, `design/panels.jsx`, `design/app.jsx`
- **설정 다이얼로그**: `design/settings.jsx` (7탭 전체)
- **디자인 대화**: `design/chats/chat1.md` — 디자인 의도/결정 사유
- **적용 스타일**: V2 오렌지 적극 — Claude 오렌지(`#D97757`)를 primary accent로
- UI 코드 작성 시 반드시 `design/styles.css`의 색상 토큰을 참조할 것

## 작업 진행 규칙

### 소통 규칙
- 사용자 명령이 불명확하거나 해석이 여러 가지일 경우, 명확하게 이해될 때까지 무한정 질문할 것 (추측으로 진행 금지)
- 작업 완료 후 결과가 초기 계획(PROGRESS.md, CLAUDE.md, docs_기능_레퍼런스.md)과 달라진 부분이 있으면, 관련 문서를 업데이트할지 반드시 사용자에게 확인할 것
- 파일 수정 전, 영향받는 다른 파일 목록을 먼저 알려줄 것

### 진행 관리 규칙
- 각 작업 항목 완료 시 즉시 `PROGRESS.md`의 해당 `[ ]` → `[x]` 로 업데이트
- Phase 전체 완료 시 상단 "현재 단계" 텍스트도 업데이트
- PROGRESS.md 업데이트는 해당 Phase 커밋에 함께 포함
- 커밋은 Phase 단위로 (중간에 임의 커밋 금지)
- 커밋 메시지 형식: `phase0-b: 패키지 골격 생성` 형식

### CLAUDE.md 분리 규칙
- CLAUDE.md가 200줄을 초과하면 관련 폴더에 하위 CLAUDE.md를 별도 생성
  (예: `ui/CLAUDE.md`, `detection/CLAUDE.md`)
- 루트 CLAUDE.md는 전체 아키텍처·공통 규칙만 유지
- 하위 CLAUDE.md는 Claude Code가 해당 폴더 작업 시 자동으로 로드됨 (별도 참조 불필요)

### v1 코드 이식 규칙
- v1 코드 이식 시, `QThread` / `QTimer` / `Signal` / `QObject` 잔재 여부를 체크 후 보고할 것
- Detection 프로세스에 이식하는 코드는 PySide6 임포트가 없는지 반드시 확인
- 이식 후 변경사항 목록을 사용자에게 보고할 것

## 개발 규칙
- 모든 응답은 한국어
- PySide6 사용 (PyQt 아님)
- 다크 모드 UI 기본
- 색상 원칙: 정상=색 없음(기본 배경/텍스트), 이상=빨간색만 사용 (초록색 금지)
  - 예외: `ui/log_widget.py`의 로그 타입 구분 색상은 시각 구별을 위해 허용
    (블랙이상=빨간 #cc0000, 스틸이상=보라 #7B2FBE, 오디오레벨미터=초록 #006600, 임베디드=파란 #004488)
- 파일 인코딩: UTF-8
- 들여쓰기: 4 spaces
- docstring: 한국어
- QSpinBox 위아래 버튼 사용 금지

## 용어
- ROI → "감지영역"으로 통일
- 감지합계 표기: V(영상) A(오디오레벨미터) EA(임베디드오디오)

## 설치된 외부 패키지 (v1과 동일)
```
PySide6
opencv-python
numpy
sounddevice    (없으면 더미 신호로 동작)
psutil
gputil         (NVIDIA GPU 없으면 N/A 표시)
pycaw          (Windows 시스템 볼륨 제어)
requests       (텔레그램 HTTP 발송)
```

## 외부 도구: ffmpeg
- 용도: 자동 녹화 MP4에 임베디드 오디오 합성 (`detection/auto_recorder.py`)
- 설치: `winget install ffmpeg`
- 미설치 시: 비디오 전용 MP4로 폴백 (에러 아님)

---

## 아키텍처 — 프로세스 구조

```
main.py (Launcher)
  ├─ SharedMemory 생성 (frame_shm, state_shm)
  ├─ result_queue, cmd_queue 생성
  ├─ Detection Process spawn
  ├─ Watchdog Process spawn
  └─ QApplication + MainWindow 실행 (현재 프로세스 = UI)

UI Process (PySide6 이벤트 루프)
  ├─ UIBridge (QThread): result_queue 폴링 → Qt Signal 변환
  └─ AlarmSystem: 시각/청각 알림 관리 (QTimer 500ms 깜빡임, threading.Thread 사운드 재생)

Detection Process (PySide6 임포트 없음)
  ├─ VideoCaptureWorker   (threading.Thread)
  ├─ AudioMonitorWorker   (threading.Thread)
  ├─ DetectionEngine      (블랙/스틸/HSV/임베디드)
  ├─ SignoffManager       (threading.Thread + time.sleep)
  ├─ AutoRecorder         (순환버퍼 + ffmpeg)
  ├─ TelegramWorker       (daemon 스레드)
  └─ HeartbeatWriter      (5초 주기 heartbeat.dat 갱신)

Watchdog Process
  └─ heartbeat.dat 감시 → 10초 무응답 시 Detection 재spawn + 텔레그램 알림
```

## 프로세스 간 통신 규칙

### SharedMemory
| 이름 | 용도 | 방향 |
|------|------|------|
| `kbs_frame_v2` | 프레임 픽셀 (~6MB) | Detection → UI |
| `kbs_state_v2` | detection_enabled, mute, volume, level_l, level_r | 양방향 |

- **Detection 프로세스**: `shared_frame.write_frame(ndarray)`
- **UI 프로세스**: `shared_frame.read_frame()` → 반드시 `.copy()` 후 반환
- seq_no 기반 변경 감지 (Lock 없음, 1프레임 지연 허용)
- **L/R 레벨미터(`level_l`, `level_r` float)**: Detection → UI 방향. UI는 약 33ms 주기로 읽어 상단바 세그먼트 표시 (고빈도 값은 result_queue 대신 SharedMemory로 전달)
- **잔존 정리**: `main.py` 시작 시 기존 이름으로 `SharedMemory(name=..., create=False)` 시도 → 성공하면 `unlink()` 후 재생성. 정상 종료 시 try-finally로 반드시 `close()` + `unlink()`

### Queue
| Queue | 방향 | maxsize | 내용 |
|-------|------|---------|------|
| `result_queue` | Detection → UI | 200 | 감지결과, 알림이벤트, 로그, DIAG |
| `cmd_queue` | UI → Detection | 50 | 설정변경, ROI업데이트, 정파명령 |

- `put_nowait()` 사용 (블로킹 금지)
- Full 시: `get_nowait()` 1개 drop 후 재시도

## 파일 구조
```
kbs_monitoring_v2/
├── main.py                          # Launcher (faulthandler 활성화 포함)
├── data/                            # 런타임 상태 파일 (gitignore)
│   ├── heartbeat.dat                # 바이너리 8바이트: time.time() double
│   └── last_exit.json               # {"exit_time","exit_code","reason","pid"}
├── processes/
│   ├── detection_process.py         # Detection 프로세스 진입점 + 메인 루프
│   └── watchdog_process.py          # Watchdog 프로세스
├── ipc/
│   ├── shared_frame.py              # SharedMemory 프레임 버퍼 래퍼
│   ├── shared_state.py              # SharedMemory 상태 버퍼 래퍼
│   └── messages.py                  # Queue 메시지 dataclass 정의
├── detection/
│   ├── video_capture.py             # VideoCaptureWorker (threading.Thread)
│   ├── audio_monitor.py             # AudioMonitorWorker (threading.Thread)
│   ├── detector.py                  # DetectionEngine
│   ├── detection_state.py           # DetectionState (히스테리시스)
│   ├── signoff_manager.py           # SignoffManager
│   ├── auto_recorder.py             # 순환버퍼 + ffmpeg
│   └── telegram_worker.py           # HTTP 전송 스레드
├── ui/
│   ├── main_window.py               # MainWindow (3분할, IPC 연결)
│   ├── ui_bridge.py                 # result_queue → Qt Signal (QThread)
│   ├── alarm.py                     # AlarmSystem (시각/청각 알림, UI 프로세스 전용)
│   ├── top_bar.py                   # 상단 바
│   ├── video_widget.py              # 프레임 표시 + ROI 오버레이
│   ├── log_widget.py                # 시스템 로그
│   ├── settings_dialog.py           # 7탭 설정 (비모달)
│   ├── roi_editor.py                # ROI 편집 캔버스 (설정창+영상 동시 표시)
│   └── dual_slider.py               # HSV 듀얼 슬라이더
├── core/
│   └── roi_manager.py               # ROI dataclass + ROIManager
├── utils/
│   ├── config_manager.py            # JSON 설정 저장/불러오기
│   └── logger.py                    # 파일 로그 (일별 로테이션)
├── config/
│   └── default_config.json
└── resources/
    ├── sounds/
    └── styles/
        ├── dark_theme.qss
        └── light_theme.qss
```

---

## 핵심 설계 원칙

### Detection 프로세스 절대 규칙
- **PySide6 임포트 금지** (Qt 이벤트 루프 없음)
- QThread, QTimer, Signal/Slot 사용 금지
- 메인 루프: `while running: ... time.sleep(0.200 - elapsed)`
- 예외 발생 시 로그 후 루프 계속 (루프 탈출 금지)
- DIAG 블록과 감지 블록은 반드시 독립된 try-except로 분리

```python
# 올바른 패턴
while self._running:
    t = time.monotonic()
    try:
        _run_diag_if_needed()
    except Exception as e:
        log_error(str(e))
    try:
        _run_detection_once()
    except Exception as e:
        log_error(str(e))
    time.sleep(max(0, 0.200 - (time.monotonic() - t)))
```

### Windows multiprocessing 필수 조건
```python
# main.py 최상단 — 없으면 Windows에서 무한 재spawn 발생
if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
```

### 히스테리시스 원칙 (v1에서 이식)
- 경보 전/후 대칭 적용
- SignoffManager: IDLE 진입 시 `_reset_enter_timers()`, SIGNOFF 진입 시 `_reset_exit_timers()`
- still_reset_frames: 연속 정상 프레임 카운터 (글리치 방지)

### AlarmSystem 위치
- UI 프로세스에만 존재 (winsound는 Windows GUI 스레드 연관)
- trigger/resolve는 UIBridge.alarm_event_received Signal로 수신

### SharedMemory read_frame() 규칙
- 반드시 `.copy()` 후 반환 (SharedMemory 해제 시 원본 참조 무효화 방지)

### v1에서 그대로 이식 가능한 파일
| v1 | v2 | 주요 변경 |
|----|----|----|
| `core/detector.py` | `detection/detector.py` | Signal 제거, dict 반환 |
| `core/detection_state.py` | `detection/detection_state.py` | Signal 제거 |
| `core/signoff_manager.py` | `detection/signoff_manager.py` | QTimer → time.sleep(1) (1초 주기 상태 점검) |
| `core/auto_recorder.py` | `detection/auto_recorder.py` | 거의 없음 |
| `core/telegram_notifier.py` | `detection/telegram_worker.py` | QObject 제거 |
| `core/roi_manager.py` | `core/roi_manager.py` | 없음 |
| `ui/video_widget.py` | `ui/video_widget.py` | 프레임 소스만 변경 |
| `ui/log_widget.py` | `ui/log_widget.py` | 없음 |
| `ui/dual_slider.py` | `ui/dual_slider.py` | 없음 |
| `utils/` | `utils/` | 거의 없음 |

### 새로 작성하는 파일 (v2 신규)
- `main.py`, `processes/*`, `ipc/*`, `ui/ui_bridge.py`, `ui/main_window.py`

---

## v1 반복 버그에서 도출한 추가 원칙

### 예외 처리 원칙
- 모든 DIAG 섹션은 반드시 독립된 try-except로 격리 (하나 실패해도 나머지 계속)
- `traceback.format_exc()` 호출 자체도 inner-try로 보호 (호출 실패 시 에러 정보 소실 방지)
- `threading.Thread.start()` 실패 시 OSError를 반드시 로그에 기록

### PySide6 QWidget 생성 규칙 (v1 ui/CLAUDE.md 이식)
- `QScrollArea` 사용 시: `QWidget()` 생성 직후 **즉시** `setWidget()` 호출 (GC 삭제 방지)
- 레이아웃 변수명은 역할별로 명확하게 (`inner`, `layout` 같은 범용 이름 재사용 금지)
  - 잘못된 예: `layout = QVBoxLayout()` → 이후 `layout = QHBoxLayout()` 덮어쓰기 → 이전 위젯 GC 삭제
  - 올바른 예: `scroll_layout = QVBoxLayout()`, `button_row = QHBoxLayout()`

### 상태 전환 타이머 초기화 원칙
- SignoffManager 상태 전환 시 반드시 해당 방향의 타이머 초기화 함수 호출
  - IDLE 진입 시: `_reset_enter_timers()` (미호출 시 다음 날 PREPARATION 즉시 SIGNOFF 전환 버그)
  - SIGNOFF 진입 시: `_reset_exit_timers()` (미호출 시 이전 주기 stale 타이머 잔류)

### 설정 동기화 원칙
- 파라미터 추가·변경 시 반드시 3파일 동시 업데이트:
  1. `config/default_config.json` — 새 설치 기본값
  2. `utils/config_manager.py` `DEFAULT_CONFIG` — 런타임 fallback
  3. `config/kbs_config.json` — 현재 운영 설정 (값 확인)
- 설정 갱신 후 즉시 진단 로그 기록 (silent 실패 방지)

### 예약 재시작 중복 방지 원칙
- 중복 실행 방지는 시각(HH:MM)이 아닌 **날짜+시각(YYYY-MM-DD HH:MM)** 조합으로 관리
  - 시각만으로 방지 시 매일 같은 시각에 재시작 불가

### 정파 억제 규칙
- 억제는 그룹별로만 적용: `is_signoff_label(label, group_id)` 사용
- 임베디드 오디오는 그룹 귀속이 없으므로 정파 억제 적용 불가 (`is_any_signoff()` 금지)
- PREPARATION 상태: 스틸만 억제, 블랙은 계속 알림

### faulthandler 필수 적용
- `main.py` 시작 시 반드시 `faulthandler.enable(file=open("logs/fault.log", "a"))` 적용
- Python try-except는 C++ 레벨 segfault 감지 불가 → faulthandler만 감지 가능

---

## 프로세스 책임 분담

### 오디오 서브시스템 (Detection 프로세스 단독)
- `sounddevice` 스트림 오픈/읽기
- `pycaw` 시스템 볼륨/Mute 제어
- UI는 `cmd_queue`로 `SetVolume(value)`, `SetMute(bool)` 명령만 전송
- 근거: 오디오 스트림과 시스템 볼륨을 서로 다른 프로세스에서 제어 시 충돌 위험

### 알림 상태(Acknowledge)
- **UI 프로세스에만 존재** (`ui/alarm.py`의 `AlarmSystem`이 보관)
- Detection은 trigger/resolve 이벤트만 계속 발행 (ack 상태 모름)
- UI는 동일 라벨 재trigger 시 사운드/깜빡임 억제, resolve 수신 시 ack 해제
- 근거: Detection은 "감지 중", UI는 "사용자 알림 중" — 관심사 분리

### 로그 파일 분리 (Windows 동시 쓰기 충돌 방지)
- Detection: `logs/YYYYMMDD_detection.txt`
- UI: `logs/YYYYMMDD_ui.txt`
- Watchdog: `logs/YYYYMMDD_watchdog.txt`
- UI 로그 위젯(`log_widget`)은 Detection 로그를 `result_queue` 메시지로도 받아 화면에 통합 표시 (파일 따로, 화면 통합)
- 각 프로세스의 `utils/logger.py` 인스턴스는 자기 파일에만 기록

### 메모리 버퍼 상한
- `auto_recorder` 순환버퍼: 채널당 `pre_seconds × fps × 프레임크기` 계산값 상한, 초과분 drop 시 로그 기록
- `log_widget`: 500개 (초과 시 오래된 항목 제거)
- `result_queue`: maxsize=200 (Full 시 1개 drop 후 재시도)
- Phase 5 검증 시: 24h 실행 후 psutil RSS 측정
