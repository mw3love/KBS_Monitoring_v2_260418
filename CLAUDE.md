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

## 개발 규칙
- 모든 응답은 한국어
- PySide6 사용 (PyQt 아님)
- 다크 모드 UI 기본
- 색상 원칙·QSpinBox 금지: `ui/CLAUDE.md` 참조
- 파일 인코딩: UTF-8
- 들여쓰기: 4 spaces
- docstring: 한국어

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
main.py (= UI 프로세스, Launcher 겸임)
  ├─ SharedMemory 생성 (frame_shm, state_shm) + 잔존 정리
  ├─ result_queue, cmd_queue, shutdown_event 생성
  ├─ Watchdog Process spawn (Detection params + 핸들 전달)
  └─ QApplication + MainWindow 실행 (이 프로세스가 UI)

UI Process (PySide6 이벤트 루프)
  ├─ UIBridge (QThread): result_queue 폴링 → Qt Signal 변환
  ├─ SharedFramePoller (QTimer ~33ms): seq_no 변경 시 프레임 화면 갱신
  ├─ AlarmSystem: 시각/청각 알림 관리 + ack 상태 관리 (UI 프로세스 전용)
  └─ DetectionReady 수신 → 런타임 상태(detection_enabled/mute/volume/signoff_state/ROIs) 재주입

Watchdog Process  (Detection의 spawn 주체)
  ├─ Detection Process spawn / 감시 / 재spawn 전담
  ├─ heartbeat.dat 감시 → 10초 무응답 시 Detection kill 후 재spawn
  ├─ 텔레그램 알림 직접 발송 (UI가 죽어도 알림 보장)
  ├─ main(UI) 생존 확인 (30초 주기 psutil.pid_exists) → 죽으면 Detection 정리 + 자신 종료
  └─ shutdown_event set 시 "의도된 종료" 플래그 ON → false-positive respawn 방지

Detection Process (PySide6 임포트 금지 — 세부 규칙은 detection/CLAUDE.md)
  ├─ 기동 시 config/kbs_config.json 자체 로드 (fast start)
  ├─ DetectionReady 이벤트 발행 (최초 + 재spawn 직후 각 1회)
  ├─ VideoCaptureWorker   (threading.Thread)
  ├─ AudioMonitorWorker   (threading.Thread, sounddevice 단독 소유)
  ├─ DetectionEngine      (블랙/스틸/HSV/임베디드)
  ├─ SignoffManager       (threading.Thread + time.sleep(1))
  ├─ AutoRecorder         (순환버퍼 + ffmpeg)
  ├─ TelegramWorker       (daemon 스레드, 일반 감지 알림)
  └─ HeartbeatWriter      (5초 주기 heartbeat.dat 갱신)
```

- **소유권 원칙**: main은 SharedMemory/Queue/UI 소유. Watchdog은 Detection 소유. 재spawn 시에도 Queue·SharedMemory 핸들은 main이 만든 그대로 재사용.

## 프로세스 간 통신 규칙

> **세부 스펙은 `docs_ipc_spec.md`에 고정됨** (메시지 dataclass 전체 목록, SharedMemory 바이트 레이아웃, 생명주기 시퀀스). 아래는 원칙 요약. 메시지·필드 추가/변경 시 반드시 `docs_ipc_spec.md`를 먼저 갱신.

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
├── main.py
├── data/
│   ├── heartbeat.dat
│   └── last_exit.json
├── processes/
│   ├── detection_process.py
│   └── watchdog_process.py
├── ipc/
│   ├── shared_frame.py
│   ├── shared_state.py
│   └── messages.py
├── detection/
│   ├── video_capture.py
│   ├── audio_monitor.py
│   ├── detector.py
│   ├── detection_state.py
│   ├── signoff_manager.py
│   ├── auto_recorder.py
│   └── telegram_worker.py
├── ui/
│   ├── main_window.py
│   ├── ui_bridge.py
│   ├── alarm.py
│   ├── top_bar.py
│   ├── video_widget.py
│   ├── log_widget.py
│   ├── settings_dialog.py
│   ├── roi_editor.py
│   └── dual_slider.py
├── core/
│   └── roi_manager.py
├── utils/
│   ├── config_manager.py
│   └── logger.py
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

### Windows multiprocessing 필수 조건
```python
# main.py 최상단 — 없으면 Windows에서 무한 재spawn 발생
if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
```

### SharedMemory read_frame() 규칙
- 반드시 `.copy()` 후 반환 (SharedMemory 해제 시 원본 참조 무효화 방지)

> Detection·UI 프로세스별 추가 원칙은 `detection/CLAUDE.md`, `ui/CLAUDE.md` 참조.

---

## 프로세스 책임 분담

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

---

## 재spawn · 종료 · 크래시 시퀀스 (요약)

> 상세 단계는 `docs_ipc_spec.md §3`. 여기서는 원칙만.

### Detection 재spawn 시 상태 복원 (하이브리드)
- Detection은 기동 시 **`config/kbs_config.json` 자체 로드** (Fast start, UI 대기 불필요)
- Detection은 준비 완료 시 **`DetectionReady` 이벤트 발행**
- UI는 `DetectionReady` 수신 시 **UI 보유 런타임 상태만 재주입**:
  - `ApplyConfig(reason='restore')`, `SetDetectionEnabled`, `SetVolume`, `SetMute`, `SetSignoffState` × 2, `UpdateROIs`
- 알람 ack 상태는 UI 전용 → 재주입 없음. Detection의 새 `AlarmTrigger`가 UI ack 필터를 자연 통과/차단.

### 정상 종료 순서
1. UI `closeEvent` → `shutdown_event.set()` + `Shutdown` 메시지
2. Watchdog "의도된 종료" 플래그 ON (재spawn 억제)
3. Detection 작업자 join(3s) → 종료
4. Watchdog Detection join(5s) → 실패 시 terminate → Watchdog 종료
5. main: `last_exit.json` 기록 → SharedMemory `close()`+`unlink()` → `QApplication.quit()`

### 비정상 종료 대응
- **Detection 크래시**: Watchdog이 재spawn + 텔레그램 알림 ("중단 감지" → "복구 완료")
- **UI(main) 크래시**: Watchdog이 30초 주기로 `psutil.pid_exists(parent)` 감시 → 사라지면 Detection 정리 + 자신 종료 + 텔레그램 "전체 비정상 종료" 알림
- **Watchdog 자체 크래시**: main은 Watchdog join 실패 시 Detection 정리 + 로그 + 텔레그램 (main 프로세스에서 직접 HTTP 발송)

### 텔레그램 발송 주체 분리
- 감지 이벤트 알림: Detection의 `TelegramWorker` 전담
- 프로세스 생존/재spawn/크래시 알림: Watchdog 또는 main에서 직접 HTTP 발송 (Detection이 죽었을 때도 송신 가능)
- 중복 방지: 메시지 prefix(`[DETECT]` / `[SYSTEM]`) 구분 + Watchdog·main은 Detection의 쿨다운과 무관
