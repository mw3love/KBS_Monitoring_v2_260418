# KBS Monitoring v2 — 작업 진행 체크리스트

> 마지막 업데이트: 2026-04-26 (파트 7 수정 완료)
> 현재 단계: Phase 5 진행 중 (코딩 완료 / 실기 테스트 대기 중)

---

## Phase 0-A — 저장소 초기화 ✅
- [x] git init
- [x] `.gitignore` 생성
- [x] `CLAUDE.md` 생성 (개발 규칙 + 아키텍처 원칙)
- [x] `PROGRESS.md` 생성 (이 파일)
- [x] `docs_기능_레퍼런스.md` 복사 (v1 → v2)

---

## Phase 0-A-fix2 — 설계 공백 확정 (IPC/생명주기/모순 해소)
- [x] `docs_ipc_spec.md` 신규 작성 (메시지/SharedMemory/생명주기 단일 진실 원천)
- [x] `CLAUDE.md` 보강: Launcher=UI 확정, Watchdog이 Detection spawn 주체, 재spawn 복원 하이브리드, 종료/크래시 시퀀스, 오디오 장치 선택 규칙, 텔레그램 주체 분리
- [x] `docs_기능_레퍼런스.md` 모순 해소: 포트 0~31 / detection_interval 이산값 / pre_seconds 1~30 / 임베디드 오디오 장치 UI / DIAG-IPC / UI 생존 감시 / 시스템 알림 prefix
- [x] 커밋: `phase0-a-fix2: 설계 공백 확정 (IPC 스펙 + 아키텍처 결정 반영)`

**완료 기준**: 위 세 문서 간 모순 0, Phase 0-B 구현 시 "이 내용은 어디에 있어야 하나?" 질문 없이 진행 가능.

---

## Phase 0-B — 패키지 골격 ✅
- [x] 디렉토리 구조 + 각 `__init__.py` 생성 (`data/`, `logs/snapshots/` 포함, `.gitkeep`으로 빈 폴더 유지)
- [x] `ipc/messages.py`: **`docs_ipc_spec.md §2`의 모든** 메시지 dataclass 정의 (누락 검증 스크립트 포함)
- [x] `ipc/shared_frame.py`: `docs_ipc_spec.md §1.1` 레이아웃 구현 (Lamport seq, width/height/flags 헤더)
- [x] `ipc/shared_state.py`: `docs_ipc_spec.md §1.2` 레이아웃 구현 (magic/version 검증 + Lock)
- [x] `core/roi_manager.py`: v1에서 복사
- [x] `utils/config_manager.py`: v1 복사 + v2 신규 키 추가(`config_version`, `embedded.audio_input_device`, 시스템 알림 키)
- [x] `utils/logger.py`: v1 복사 + 프로세스별 파일명 suffix 지원 (`_detection`/`_ui`/`_watchdog`)
- [x] `config/default_config.json`: v1 복사 + v2 키 추가 + `"config_version": 2`
- [x] resources/ 폴더 + 빈 파일 구조 (dark_theme.qss, light_theme.qss 골격)
- [x] **IPC 스펙 정합성 테스트**: `tests/test_ipc_contract.py` — 7/7 PASS
- [x] 커밋: `phase0-b: 패키지 골격 생성`

**완료 기준**: `python -c "from ipc.shared_frame import SharedFrameBuffer; from ipc.messages import *"` 오류 없음. IPC 정합성 테스트 통과.

---

## Phase 1 — Detection 프로세스 독립 실행 ✅
- [x] `detection/detection_state.py`: v1 이식
- [x] `detection/video_capture.py`: threading.Thread (QThread 제거)
- [x] `detection/audio_monitor.py`: threading.Thread (QThread 제거) + 장치 이름 기반 선택
- [x] `detection/detector.py`: v1 이식, Signal 제거, dict 반환
- [x] `detection/signoff_manager.py`: QTimer → time.sleep(1)
- [x] `detection/auto_recorder.py`: v1 이식
- [x] `detection/telegram_worker.py`: v1 이식, QObject 제거
- [x] `processes/detection_process.py`: 메인 루프 + heartbeat.dat + 기동 시 config 자체 로드 + DetectionReady 발행
- [x] **단위테스트** `tests/test_detector.py`: 13/13 PASS
- [x] **단위테스트** `tests/test_signoff_manager.py`: 11/11 PASS
- [x] **단위테스트** `tests/test_detection_state.py`: 9/9 PASS

**완료 기준**: `python -m processes.detection_process --test` 실행 시 30초 주기 DIAG 콘솔 출력. 캡처 포트 없이도 루프 생존. 단위테스트 전부 pass.

---

## Phase 2 — UI 프로세스 + IPC 연결 ✅
- [x] `ipc/shared_frame.py` 완성 (Phase 0-B에서 구현)
- [x] `ipc/shared_state.py` 완성 (Phase 0-B에서 구현)
- [x] `resources/styles/dark_theme.qss`: design/styles.css 기반, #D97757 primary accent
- [x] `resources/styles/light_theme.qss`: 라이트 변형
- [x] `ui/ui_bridge.py`: UIBridge QThread (result_queue 50ms 폴링 → 11종 Signal)
- [x] `ui/alarm.py`: AlarmSystem v1 이식 (QTimer 깜빡임, threading 사운드, Ack 상태)
- [x] `ui/video_widget.py`: v1 이식 + SharedFramePoller(QTimer 33ms, seq_no 변경 감지)
- [x] `ui/log_widget.py`: v1 이식
- [x] `ui/top_bar.py`: v1 이식 + 볼륨 debounce 100ms + L/R 레벨미터 SharedMemory 폴링
- [x] `ui/main_window.py`: 뼈대 (UIBridge+SharedFramePoller, 3분할, 재주입, 테마)
- [x] `main.py`: Launcher + faulthandler + SharedMemory 잔존 정리 + Watchdog spawn
- [x] `processes/watchdog_process.py`: heartbeat 감시 + Detection 재spawn + UI 생존 확인
- [x] cmd_queue 볼륨 슬라이더 debounce(100ms) 적용

**완료 기준**: 캡처 카드 연결 시 VideoWidget 영상 표시. main(UI)과 Detection, Watchdog 3개 PID 확인. 다크 테마가 design/styles.css 톤을 반영. L/R 레벨미터가 SharedMemory 경로로 갱신.

---

## Phase 3 — 알림 + 정파 + ROI 편집 ✅
- [x] AlarmSystem 연결 (UIBridge → trigger/resolve)
- [x] 알림확인 버튼 → AlarmSystem 내부 ack 상태만 갱신 (cmd_queue 전송 불필요)
- [x] 정파 버튼 → cmd_queue
- [x] 볼륨/Mute 버튼 → cmd_queue (`SetVolume` / `SetMute`, pycaw 제어는 Detection에서)
- [x] `ui/roi_editor.py`: v1 이식, 편집 완료 → cmd_queue RoiUpdate
- [x] `ui/settings_dialog.py`: 신규 작성 (7탭), 저장 → cmd_queue ApplyConfig/UpdateROIs — `design/settings.jsx` 참조
- [x] `ui/dual_slider.py`: v1 이식

**완료 기준**: 블랙/스틸/오디오/임베디드 감지 및 알림 정상. 정파 전환 정상. ROI 편집 후 즉시 반영.

---

## Phase 4 — Watchdog + Launcher 완성 ✅
- [x] `processes/watchdog_process.py`: heartbeat 감시 + Detection kill/재spawn + UI parent PID 감시 + shutdown_event 존중
- [x] Watchdog 직접 텔레그램 발송 경로 (`[SYSTEM]` prefix) — Detection 재spawn/heartbeat stale/UI 사망 3종
- [x] 재spawn 후 UI 측 런타임 상태 재주입 경로 통합 테스트 (`DetectionReady` → `ApplyConfig`/`UpdateROIs`/`SetDetectionEnabled`/`SetVolume`/`SetMute`/`SetSignoffState` 재송신 — `main_window.py:249` 구현 확인)
- [x] `main.py`: last_exit.json 기록 + Watchdog 비정상 종료 감지 텔레그램 + 종료 시 SharedMemory close+unlink try-finally
- [x] 예약 재시작: Launcher(`main.py`) 단독 관리, 날짜+시각(YYYY-MM-DD HH:MM) 조합으로 중복 방지, 30초 주기 QTimer

**완료 기준**: Detection 강제 kill 시 10초 내 재spawn + UI 상태 자동 복원(조작 불필요). `[SYSTEM]` 텔레그램 알림 수신. UI 강제 kill 시 Watchdog이 Detection 정리 후 자신 종료.

---

## Phase 5 — 통합 검증
- [x] DIAG 로그 6개 섹션 완전 이식 (SYSTEM-HB, DIAG-V, DIAG-ALARM, DIAG-SIGNOFF, DIAG-AUDIO, DIAG-TELEGRAM)
- [x] **DIAG-IPC 섹션** 추가 (queue drop/크기, frame drop, loop jitter)
- [x] DIAG 섹션 독립 try-except 보호
- [x] 채널당 메모리 버퍼 상한 검증 (auto_recorder)
- [x] **회귀 시나리오 테스트**: `tests/test_regression.py` 6/6 PASS (블랙/스틸/정파전환/억제/중복방지/동시알람)
- [ ] **Chaos 테스트**: `tests/test_chaos.py` — `python tests/test_chaos.py --rounds 3` 로 실행 (Detection 강제 kill → 재spawn 성공률 100% 목표)
- [ ] **24시간 연속 실행 테스트**: `tests/test_24h_monitor.py` — `python tests/test_24h_monitor.py` 로 실행 (앱 실행 중 별도 터미널에서, logs/monitor_24h_*.csv 기록)
- [x] 로그 분리 확인 (detection/ui/watchdog 각 파일)
- [x] **코드 검토 파트 1~5 완료** (IPC 계약·프로세스 생명주기·감지 엔진·정파 매니저·UI 브리지+알람): 총 9개 버그 수정 (P1-3 nodrop, P2-A DetectionReady 차단, P2-B AutoRecorder join, P3-A ROI update, P3-E dead var, P4-A group_id, P4-B 디버그 로그, P4-C dict 스냅샷, P5-4 잔류 AlarmTrigger 가드)
- [x] **코드 검토 파트 6 완료** (설정 다이얼로그 7탭): 4개 버그 수정 (P6-A _browse_sound 미반영, P6-B TelegramTestWorker race, P6-D ROI 내부 리스트 직접 변이, P6-E 미설정 색상 불일치)
- [x] **코드 검토 파트 7 완료** (텔레그램·자동녹화·DIAG): 6개 버그 수정 (P7-1 _last_sent 무한누적, P7-2 stop/ensure_worker_alive race, P7-3 429 블로킹+무한루프, P7-4+9 Watchdog tg() 블로킹→heartbeat 오판+shutdown 지연, P7-6 qsize NotImplementedError, P7-8 이중 JPEG 인코딩)

**완료 기준**: 24시간 무중단. 메모리 RSS 증가 < 5%. DIAG 전 섹션 정상. Chaos 테스트 재spawn 복원률 100%.
