# KBS Monitoring v2 — 작업 진행 체크리스트

> 마지막 업데이트: 2026-04-18
> 현재 단계: Phase 0-A 완료

---

## Phase 0-A — 저장소 초기화 ✅
- [x] git init
- [x] `.gitignore` 생성
- [x] `CLAUDE.md` 생성 (개발 규칙 + 아키텍처 원칙)
- [x] `PROGRESS.md` 생성 (이 파일)
- [x] `docs_기능_레퍼런스.md` 복사 (v1 → v2)

---

## Phase 0-B — 패키지 골격
- [ ] 디렉토리 구조 + 각 `__init__.py` 생성
- [ ] `ipc/messages.py`: Queue 메시지 dataclass 정의
- [ ] `ipc/shared_frame.py`: SharedMemory 프레임 버퍼 래퍼
- [ ] `ipc/shared_state.py`: SharedMemory 상태 버퍼 래퍼
- [ ] `core/roi_manager.py`: v1에서 복사
- [ ] `utils/config_manager.py`: v1 복사 + v2 신규 키 추가
- [ ] `utils/logger.py`: v1 복사
- [ ] `config/default_config.json`: v1 복사 + v2 키 추가
- [ ] resources/ 폴더 + 빈 파일 구조
- [ ] 첫 커밋: "chore: Phase 0 프로젝트 골격"

**완료 기준**: `python -c "from ipc.shared_frame import SharedFrameBuffer"` 오류 없음

---

## Phase 1 — Detection 프로세스 독립 실행
- [ ] `detection/detection_state.py`: v1 이식
- [ ] `detection/video_capture.py`: threading.Thread (QThread 제거)
- [ ] `detection/audio_monitor.py`: threading.Thread (QThread 제거)
- [ ] `detection/detector.py`: v1 이식, Signal 제거, dict 반환
- [ ] `detection/signoff_manager.py`: QTimer → time.sleep(1)
- [ ] `detection/auto_recorder.py`: v1 이식
- [ ] `detection/telegram_worker.py`: v1 이식, QObject 제거
- [ ] `processes/detection_process.py`: 메인 루프 + heartbeat.dat

**완료 기준**: `python processes/detection_process.py --test` 실행 시 30초 주기 DIAG 콘솔 출력. 캡처 포트 없이도 루프 생존.

---

## Phase 2 — UI 프로세스 + IPC 연결
- [ ] `ipc/shared_frame.py` 완성 + 멀티프로세스 테스트
- [ ] `ipc/shared_state.py` 완성
- [ ] `ui/ui_bridge.py`: UIBridge QThread
- [ ] `ui/video_widget.py`: v1 이식 (frame_updated Signal 연결)
- [ ] `ui/log_widget.py`: v1 이식
- [ ] `ui/top_bar.py`: v1 이식
- [ ] `ui/main_window.py`: 뼈대 (UIBridge 연결, 3분할 레이아웃)
- [ ] `main.py`: Launcher 기본 구조

**완료 기준**: 캡처 카드 연결 시 VideoWidget 영상 표시. 두 프로세스 분리된 PID 확인.

---

## Phase 3 — 알림 + 정파 + ROI 편집
- [ ] AlarmSystem 연결 (UIBridge → trigger/resolve)
- [ ] 알림확인 버튼 → cmd_queue
- [ ] 정파 버튼 → cmd_queue
- [ ] `ui/roi_editor.py`: v1 이식, 편집 완료 → cmd_queue RoiUpdate
- [ ] `ui/settings_dialog.py`: v1 이식, 저장 → cmd_queue ConfigUpdate
- [ ] `ui/dual_slider.py`: v1 이식

**완료 기준**: 블랙/스틸/오디오/임베디드 감지 및 알림 정상. 정파 전환 정상. ROI 편집 후 즉시 반영.

---

## Phase 4 — Watchdog + Launcher 완성
- [ ] `processes/watchdog_process.py`: heartbeat 감시 + kill/재spawn
- [ ] `main.py`: last_exit.json 비정상 종료 감지 + 텔레그램 알림
- [ ] 예약 재시작: MainWindow → Launcher 이관

**완료 기준**: Detection 강제 kill 시 10초 내 재spawn. 텔레그램 알림 수신.

---

## Phase 5 — 통합 검증
- [ ] DIAG 로그 6개 섹션 완전 이식
- [ ] DIAG 섹션 독립 try-except 보호
- [ ] 채널당 메모리 버퍼 상한 검증
- [ ] 24시간 연속 실행 테스트

**완료 기준**: 24시간 무중단. 메모리 안정. DIAG 전 섹션 정상.
