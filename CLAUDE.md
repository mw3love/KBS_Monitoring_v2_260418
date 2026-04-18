# KBS Monitoring v2 — 개발 규칙 (CLAUDE.md)

## 프로젝트 개요
- KBS 16채널 방송 모니터링 시스템 v2
- v1(KBS Peacock v1.6.x)의 "장기 운영 시 감지 루프 freeze" 문제를 근본 해결하기 위해 재작성
- **핵심 변경**: multiprocessing 기반 아키텍처 (UI/감지 프로세스 분리)

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
  └─ UIBridge (QThread): result_queue 폴링 → Qt Signal 변환

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
| `kbs_state_v2` | detection_enabled, mute, volume | UI → Detection |

- **Detection 프로세스**: `shared_frame.write_frame(ndarray)`
- **UI 프로세스**: `shared_frame.read_frame()` → 반드시 `.copy()` 후 반환
- seq_no 기반 변경 감지 (Lock 없음, 1프레임 지연 허용)

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
├── main.py                          # Launcher
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
│   ├── top_bar.py                   # 상단 바
│   ├── video_widget.py              # 프레임 표시 + ROI 오버레이
│   ├── log_widget.py                # 시스템 로그
│   ├── settings_dialog.py           # 6탭 설정 (비모달)
│   ├── roi_editor.py                # 반화면 ROI 편집기
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
| `core/signoff_manager.py` | `detection/signoff_manager.py` | QTimer → time.sleep |
| `core/auto_recorder.py` | `detection/auto_recorder.py` | 거의 없음 |
| `core/telegram_notifier.py` | `detection/telegram_worker.py` | QObject 제거 |
| `core/roi_manager.py` | `core/roi_manager.py` | 없음 |
| `ui/video_widget.py` | `ui/video_widget.py` | 프레임 소스만 변경 |
| `ui/log_widget.py` | `ui/log_widget.py` | 없음 |
| `ui/dual_slider.py` | `ui/dual_slider.py` | 없음 |
| `utils/` | `utils/` | 거의 없음 |

### 새로 작성하는 파일 (v2 신규)
- `main.py`, `processes/*`, `ipc/*`, `ui/ui_bridge.py`, `ui/main_window.py`
