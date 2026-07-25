# KBS Monitoring v2 — 작업 진행 체크리스트

> 마지막 업데이트: 2026-07-25 (v2.8.6 — W17 UI 장기가동 손상 5차 대응: Round 1 부결 확정 + **Round 2 운영 PC 실배포 완료·판정 시계 가동 중**)
> 현재 단계: Phase 6 코드 작업 완료 (W0~W14 + W15 회귀/Chaos 완료 + W16·W17 현장 이슈 대응). 남은 것은 비-코딩 현장 검증뿐 — W15 24h 연속 테스트(웹캠 1h 스모크 PASS, 풀 24h는 현장) + 전주총국 실제 방송 운영 테스트 → 통과 시 타 총국 배포
> ⏳ **관찰 중**: W17 Round 2(Python 3.13 다운그레이드) — **2026-07-25 운영 PC 실배포 완료**(기동 알림·텔레그램 정상 확인). 다음 위험창 **~07-29~30까지 재발 없으면 유력**. 판정 전까지 **예약 재시작 OFF 유지 필수**.

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
- [x] `main.py`: Launcher + faulthandler + sys.excepthook(unhandled exception → ui 로그) + cwd 를 _ROOT 로 고정(os.chdir) + SharedMemory 잔존 정리 + Watchdog spawn
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
- [x] **설정 다이얼로그 UI/UX 개선 1단계** (탭1 영상설정·탭7 저장불러오기): commit d91e469
- [x] **설정 다이얼로그 UI/UX 개선 2단계** (탭6 알림설정): 시스템 알림 Chat ID (선택) 컬러 표기, 텔레그램 테스트 인라인 상태 라벨, 알림 옵션 2그룹 시각 구분, 제외 시간대 힌트 개선, 재시작 주기 사람 언어 표기
- [x] **설정 다이얼로그 UI/UX 개선 3단계** (탭4 감도설정): 움직임 블랙무시·블록변화·연속정상프레임 힌트 개선, HSV 프리셋 버튼 H행 인라인, HSV 픽셀비율 힌트 개선, 성능 자동감지 인라인 결과 라벨, 감지주기·해상도스케일 힌트 개선, 섹션 비활성화 시 헤더 dim 처리
- [x] **설정 다이얼로그 UI/UX 개선 4단계** (탭2·3 ROI 영역설정): 편집 버튼 활성 시 오렌지 배경+"편집 종료"/비활성 복원, 단축키 안내 인라인 카드(--bg-2+--border), 0개 카운터 --alert 색상+"등록된 영역 없음 — 감지 불가", 전체 지우기 QMessageBox 확인, 매체명 헤더 툴팁 추가
- [x] **설정 다이얼로그 UI/UX 개선 5단계** (탭5 정파설정): 시간 입력 필드 36px+시작/종료 레이블, 섹션 헤더 요약 라벨(HH:MM~HH:MM 요일), 요일 전체선택·전체해제 2버튼 분리, 감지영역 미설정 --text-2 회색, 준비 시각 "▶ HH:MM 부터"/0분 "준비 없음", 그룹명 헤더 인라인 QLineEdit, 알림음 placeholder 힌트
- [x] **설정 저장/불러오기 정합성 수정**: `_reload_all_tabs`가 `DEFAULT_CONFIG`로 초기화되던 버그 수정(`_apply_video/sensitivity/signoff/alert_widgets(cfg)` 분리), 알림설정 탭 누락 항목(system_chat_id·notify_image/black/still/audio/embedded/signoff/system·cooldown·예약 재시작 4개) `self._cfg`로 갱신, 음소거 토글(`sound_toggled`) 시 `self._cfg["alarm"]["sound_enabled"]` 동기화로 재시작 시 상태 복원, 임베디드 오디오 `embedded_recovery_seconds` UI 노출(감도설정 탭 임베디드 섹션 "복구 대기(초)")
- [x] **임베디드 오디오 음소거 영속화**: `ui_state.embed_muted` 신규 키 추가(3개 config 파일 동기), 상단바 임베디드 뮤트 토글 시 cfg 즉시 동기화, `_restore_ui_state`에서 `set_embed_mute_state()`로 버튼 시각 복원, Detection 측 mute는 기존 `_reinject_runtime_state` 경로(DetectionReady → SetMute)로 자동 전파

**완료 기준**: 24시간 무중단. 메모리 RSS 증가 < 5%. DIAG 전 섹션 정상. Chaos 테스트 재spawn 복원률 100%.

---

## Phase 6 — fire-and-forget 배포 하드닝
> 계획: `C:\Users\7make\.claude\plans\wobbly-herding-whale.md`
> 목표: 10여 개 총국으로 GitHub+자체Python 방식 배포 가능 수준. 한 번 배포 후 개발자 개입 불가 전제.

### P0 — 무인 자가복원력
- [x] **W0** 단일 인스턴스 가드 (Windows Local 뮤텍스 + 한국어 MessageBox) — `main.py`
- [x] **W1** 프레임 신선도 자가복원 (15s stale → `heartbeat.stop()` → Watchdog 재spawn) — `detection/video_capture.py`, `processes/detection_process.py`
- [x] **W2** 워커 자동재개 (audio_monitor 외부 init 실패 시 silent failure 갭 해소) — `detection/audio_monitor.py`
- [x] **W3** heartbeat 견고화 (쓰기 실패 로그화 + UI 크래시 감시 30s→10s) — `processes/detection_process.py`, `processes/watchdog_process.py`
- [x] **W4** Chaos 테스트 100% PASS (3라운드 × 3회 실행 — W0/W1/W2/W3/W7/W8 적용 후 회귀 없음 확인)

### P1 — 환경 이식성
- [x] **W5** requirements.txt 8개 패키지 == 버전 핀 + Python 3.11+ 명시
- [x] **W6** 캡처 포트 스캔·미리보기 도우미 — ~~v2.x에서 제거~~ (현장 검증 결과 활용도 낮음: 정작 보고 싶은 점유 포트(port 0)는 DSHOW 독점 오픈 때문에 미리보기 불가 + 대부분 외장 포트 미사용. `ui/settings_dialog.py`의 버튼·`PortScanDialog`·`_PortScanWorker` 삭제. 포트 번호 콤보박스 수동 변경은 유지)
- [x] **W7** config 손상 가시화 (`last_load_was_reset` 플래그 + 친화 메시지) — `utils/config_manager.py`
- [x] **W8** cv2/PySide6 부재 친화 메시지 (사전 점검 + MessageBox) — `main.py`
- [x] **W8b** 배포 산출물 정리 (.gitignore 정정, `실행.bat`·`디버그실행.bat` 이식 버전 재작성, `manual/`·`install_ffmpeg.bat` 포함)
- [x] **W8c** 재부팅 후 자동 시작 (옵션a '시작프로그램 바로가기' — `자동시작 등록.bat`/`자동시작 해제.bat`로 `shell:startup`에 `실행.bat` 바로가기 생성/제거 + 설치안내 §6)
- [x] **W8d** 최초 실행 부트스트랩 검증 (코드 검증: `kbs_config.json` 없을 시 DEFAULT 폴백 정상)

### P2 — 비기술 운용성
- [x] **W9** 설정 입력 검증 강화 (감사 완료. 정파 시간=`QIntValidator`+zfill, HSV=`DualSlider.set_range` 클램프+스왑으로 이미 견고 → 후보 기각. 실질 갭은 ROI 0개 → 영상 ROI 0개 시 `detection_process` 초기 로드·`UpdateROIs`에서 INFO 로그 1회 안내 — 키자마자 빨간 ERROR가 시선을 끌어 INFO로 톤 다운)
- [x] **W10** 에러 메시지 친화화 (감사 완료. traceback 노출은 전부 로그/result_queue 행이고 사용자 MessageBox raw 노출 없음. config 손상=W7·패키지 부재=W8에서 이미 친화화 → 추가 수정 불필요)
- [x] **W11** 정파 상태 가시성 + 수동해제 UI (시간대 인지 수동순환 `CycleSignoffState` 신규 — Detection `cycle_state()` 단일출처로 튕김 제거 / `auto_preparation` OFF=완전 수동 모드: `_tick_impl` PREP·SIGNOFF 분기 + `set_group` 즉시재평가에 가드 추가 → 수동 상태 유지·자동전환 0건 / 상단바 버튼 auto OFF여도 항상 활성+"· 수동" 표기+클릭 안내 툴팁 / `docs_signoff_운영.md §5` 신설)
- [x] **W12** 설치안내.txt 보강 (`실행.bat`, 이중실행 보호, 폐쇄망, 캡처 포트, 패키지 오류 Q5~Q7)

### P3 — 코어 감지 정확도
- [x] **W13** detector 엣지케이스 감사 (블록 경계=`block.size==0` 스킵·부분 블랙=`dark_ratio≥98%`+motion_suppress·임베디드=진입/복구 양방향 히스테리시스·ROI별 try-except 격리 → 모두 이미 견고. 후보 기각, 수정 불필요)
- [x] **W13-정정(v2.7.9)** 위 W13의 "motion_suppress 견고·수정 불필요" 판정은 오류였음. 블랙 경로를 단독으로만 감사해 '스틸 OFF' 교차 설정을 놓침 — 스틸 OFF 시 `changed_ratio`가 계산 안 돼 움직임 억제가 조용히 무력화되던 결함을 v2.7.9에서 수정(테스트 추가). 교훈: 감사 시 기능 간 커플링·토글 교차 케이스를 반드시 포함할 것.
- [x] **W14** 알람 상태머신 감사 (`AlarmSystem.resolve`는 `not _active_alarms`(전체 해제) 시에만 깜빡임/소리 중단 → 일부 resolve로 조기 OFF 없음. 집합 기반 다중 ROI 안전. 후보 기각, 수정 불필요)
- [ ] **W15** 회귀(`pytest tests/test_regression.py`)/24h(`tests/test_24h_monitor.py`) 테스트 실행 + 발견 케이스 추가
  - 회귀 실행: 6/6 PASS. **발견·수정**: `test_s3_signoff_transition`이 시각 의존(그룹 23:30~06:00 밖이면 PREPARATION→IDLE 강등으로 거짓 실패) → `datetime.now()`를 23:15로 mock해 시각 독립화 (SignoffManager 코드는 정상)
  - Chaos 재spawn: 3/3 (100%) — **W11 이후 재검증 3/3 (100%)**: `CycleSignoffState` import·cmd 라우팅 변경이 Detection 기동/재spawn 무영향 확인
  - 24h 테스트: 미완 (장시간 — 라이브 앱 필요). **하네스 버그 수정**(`test_24h_monitor.py _find_kbs_processes`): Windows spawn cmdline엔 detection/watchdog 키워드가 없고, 셸 래퍼(`bash.exe`)·conhost가 "main.py"를 포함해 오인되던 문제 → ① main=인터프리터 이름+`cwd==_ROOT` 확정 ② watchdog/detection=`parent_pid` 트리로 식별. 실측 검증 OK(main 181MB·detect 106MB·wd 62MB 정상 인식). 웹캠 소스 1h 스모크 진행 가능 확인 (감지 정확도는 전주 현장 몫)

### P0 추가 — 캡처 입력 상실 자동복구 (현장 이슈 대응, 2026-05-31) ✅
- [x] **W16** 캡처 입력 상실 자동복구 — 캡처보드가 신호 상실 시 "유효하지만 완전 검정인 프레임"(`ret=True`)을 계속 내보내 ROI 단체 블랙 + 무한 지속(사람 재시작 전까지)되던 현장 이슈 대응. **2층 분리 설계**: 기존 탐지·로그·녹화는 무수정·무억제(진짜 블랙이면 채널 알람 그대로 기록·녹화), 별도 워치독이 화면 *전체* "얼어붙은 검정"(전체 블랙 AND 정지, 원본 프레임 자체 계산 → 보드/설정 무관)을 `trigger_sec` 감지 시 **캡처 디바이스만 재오픈**(`force_reconnect`, 프로세스 재시작 아님)으로 자동 복구. 미복구 시 `max_attempts` 재시도 → 실패 시 에스컬레이션, `cooldown_sec` 플래핑 방지. 정파/감지비활성/ROI편집/파일모드 시 보류. 텔레그램은 상실+복구결과만. — `detection/capture_watchdog.py`(신규 순수 상태기계), `detection/video_capture.py`(`force_reconnect`), `processes/detection_process.py`(메인 루프 독립 try-except), `config/*`·`utils/config_manager.py`(`capture_recovery` 블록), `tests/test_capture_watchdog.py`. 기능 문서 §3.1-b 신설.
  - 검증: 상태기계 단위테스트 14/14 + 전체 회귀 65/65 PASS. 실기 캡처 상실 복구는 전주총국 운영 테스트에서 확인 예정.

---

### P0 추가 — UI 장기가동 손상 4차 대응 (v2.8.0, 2026-07-13) ⏳ 관찰 중
- [x] **W17** UI 손상 즉시 통보 + Round 1 제거 실험 — 장기 가동(~5일) 시 **UI 프로세스만** 힙이 손상되어 순수 파이썬 클래스의 `__init__`이 전부 실패하는 사고 **4차 발생**. 창·프레임·로그는 정상이라 겉보기엔 멀쩡하지만 **설정창·모든 알림음·모든 조작이 먹통**(4차 실측: 정파 알림음 9회 + 실제 블랙 경보음 1회 전부 무음, 42시간 방치). Detection/Watchdog은 4회 모두 완전 정상. 상세: `fix/260526_설정다이얼로그_TypeError_재현불가.md` §12.
  - **운영 완화**: onset 감지 → `data/ui_degraded.flag` 기록(UI) → Watchdog이 읽어 텔레그램 발송. ⚠ 손상된 UI는 `requests`를 못 쓰므로(파이썬 객체 생성 전면 실패) **통보 주체를 Watchdog으로 분리**한 것이 핵심. **42시간 블라인드 → 10분.** — `main.py`, `processes/watchdog_process.py`, `docs_ipc_spec.md §3.5` 신설.
  - **별개 버그 수정**: 패스스루 오디오 출력이 `except Exception: pass`라 스트림 사망 시 **로그도 복구도 없이 영구 무음**이던 문제 → 연속 실패 카운트·재오픈·로그(30초 rate limit). 4차 "소리 안 남"의 유력 원인. — `detection/audio_monitor.py`.
  - **Round 1 제거 실험 arm**(전부 비용 0): GPU 폴링 OFF(=`nvidia-smi` 프로세스 생성 5일 21만 회 → 0) / psutil 폴링 2초→10초 / `QImage` 버퍼 수명 고정(33ms×5일 = 260만 회 경로). — `ui/top_bar.py`, `ui/video_widget.py`, `config/*`·`utils/config_manager.py`(`sysmon_gpu_enabled`, `sysmon_interval_ms`).
  - **추적**: 기동 로그에 `SYSTEM - EXPERIMENT: ...` 한 줄로 arm 명시(5일 뒤 기억이 아니라 로그로 판정). 폐기 빌드는 태그 `v2.7.9-incident4`.
  - 검증: 컴파일 통과 / 플래그 경로 두 프로세스 일치 확인 / 구 운영 설정에서도 `_merge_defaults`로 arm 적용 확인 / SysMonitor 실측 **서브프로세스 0회**(대조군 `True`는 7회 → 진짜 차단됨) / VideoWidget 300프레임 정상 렌더.
  - ⚠ **미검증(프록시)**: onset→플래그→텔레그램 **실경로는 실제 손상 상태에서 미확인**. 다음 재발이 실조건 검증.
- [x] **Round 1 운영 PC 배포 (2026-07-13 11:00 기동)** — 4차와 **동일 PC**(하드웨어 변수 없음), Python **3.14.3**(4차는 3.14.2). 기동 로그 `SYSTEM - EXPERIMENT: sysmon_gpu=False sysmon_interval_ms=10000 qimage_buf_pinned=True` + 상단바 `GPU OFF` 실측 확인. 설정은 `260627 kbs_config_backup.json` 불러오기로 복원(ROI 8V+6A+1EA). 텔레그램 `연결 테스트` 성공 + **`시스템 이벤트 알림`(notify_system) 체크 확인** + **예약 재시작 OFF 확인**. 상세: `fix/260526_...md` §12-6-b.
- [x] **Round 1 판정 — 부결 (2026-07-24, 5차 발생)** — 07-20 09:45 v2.8.1 배포(독립 재기동)가 4.19일 만에 재발 → **arm 3개(GPU폴링·psutil주기·QImage버퍼) + Python 3.14.3 상승 + 하드웨어 전부 무죄** 확정. 남는 용의선은 PySide6 본체 또는 Python 3.14 계열 자체. 상세: `fix/260526_...md` §13-4.
- [x] **Round 2 사전점검 + dev PC 실조건검증 (2026-07-24~25)** — 7개 패키지 Python 3.13 wheel 지원 확인(PyPI 메타데이터) → dev PC 기동 스모크 PASS(§13-5-b) → 배포 원클릭화 스크립트 작성 후 재검증: `python313_전환.ps1`이 Python 3.13.14 설치 + `.venv313` 생성 + 패키지 설치까지 실제 실행 성공, 수정한 `실행.bat`으로 직접 기동해 `logs/20260725_ui.txt`에 `python=3.13.14` 기록 확인. 상세: `fix/260526_...md` §13-7.
  - **신규**: `python313_전환.ps1`/`.bat` (운영 PC 3.13 전환 원클릭), `실행.bat`(venv313 있으면 자동 사용, 없으면 기존과 동일 — 타 총국 무영향), `.gitignore`(`.venv313/`).
  - **함정(2라운드)**: `python313_전환.bat`이 사용자 PC에서 한글 깨짐+"명령 아님" 오류(`chcp 65001` 누락). 1차 수정(BOM 추가)은 dev PC에서 더 나쁜 결과(cmd.exe는 .bat의 UTF-8 BOM 미지원, `@echo off` 자체가 깨짐) → 2차(`chcp 65001` + BOM 없이 UTF-8 + CRLF)는 dev PC에선 통과했으나 **실제 운영 PC(Windows 11, 관리자 권한)에서 동일 증상 재발** — Windows 버전별로 `chcp`가 배치파일 자체 파싱에 적용되는 타이밍이 다른 것으로 추정. **최종(견고)**: `chcp` 신뢰를 접고 `.bat` 실행 줄의 한글 텍스트를 아예 제거 — `%~dp0<한글파일명>.ps1` 대신 `%~dpn0.ps1`(실행 중인 배치파일 자신의 경로에서 확장자만 교체, OS가 프로그램적으로 제공하므로 텍스트 재인코딩 문제 자체가 없음)로 교체 + echo 메시지도 영문화해 파일 전체를 순수 ASCII로. dev PC 재현→해결 확인(운영 PC 실증은 사용자 확인 대기). 상세: `fix/260526_...md` §13-7.
- [x] **기동(재기동) 알림 — 텔레그램 + 화면 로그 (2026-07-25)** — Round 2가 실제로 3.13으로 도는지 원격 확인할 방법이 없다는 지적에서 "재기동 통보"로 일반화. Watchdog 시작 직후 `[SYSTEM]` 텔레그램 1회(앱 버전 + `platform.python_version()`) + UI 화면 SYSTEM LOG에도 "기동 완료 (Python x.x.x)" 표시. 최초 부팅·크래시 재spawn·예약 재시작 공통. dev PC 실조건검증: 텔레그램 코드 경로 무오류 확인 + 화면 로그창에 실제 렌더된 것 스크린샷으로 직접 확인(`PrintWindow` 캡처). — `processes/watchdog_process.py`, `ui/main_window.py`, `docs_ipc_spec.md §3.1`, `docs_기능_레퍼런스.md §10.5`.
  - **연장**: "UI 손상 시에도 현장 화면에서 바로 알 수 있으면" 제안 → `main.py`의 onset 캡처에 `window._log_widget.add_log(...)` best-effort 추가. ⚠ 텔레그램 플래그 경로(`open()+write()`만 사용, 손상 상태 작동 실증됨)와 달리 이건 새 객체 생성이라 **손상 상태에서 실패 가능** — try/except로 무해하게 감쌌으나 실제 성공 여부는 재현 불가라 **미검증**(다음 발생 시 판정). 실패해도 텔레그램은 그대로 작동. — `main.py`, `CLAUDE.md`("UI 손상 통보" 절).
- [x] **Round 2 운영 PC 실배포 완료 (2026-07-25)** — `python313_전환.bat` 실행(도중 한글깨짐 2라운드 재발 → `%~dpn0.ps1` 수정판 재배포로 해결, 위 항목 참조) → 재기동 → 화면 로그·텔레그램 기동 알림 정상 확인(텔레그램은 사용자가 재사용 중이던 옛 백업 설정 재저장→재적용 후 수신 확인). **판정 시계 가동 시작 — 다음 위험창 ~07-29~30.** 상세: `fix/260526_...md` §13-8.
  - ⚠ **재발 시 재부팅 전에 로그부터 회수**: `logs/*_ui.txt`, `fault.log`, `stderr_debug.txt`, `logs/*_detection.txt`, `logs/*_watchdog.txt`, `data/ui_degraded.flag`.

---

### 최종 검증 — 전주총국 운영 테스트
- [ ] 위 모든 항목 완료 후, 해당 버전을 전주총국에 가져가 며칠간 실제 방송 영상으로 운영 테스트
- [ ] 통과 시 다른 총국 배포 시작

**완료 기준**: P0~P3 모두 완료 + Chaos 100% + 24h RSS<5% + 전주 운영 테스트 통과.
