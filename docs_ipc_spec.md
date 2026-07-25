# KBS Monitoring v2 — IPC 스펙 (프로세스 간 계약)

> 작성일: 2026-04-18
> 목적: Detection / UI / Watchdog 프로세스 간 모든 통신 계약을 고정하여 Phase 0-B 구현 전 인터페이스 불일치를 제거.
> 원칙: **이 문서와 `ipc/messages.py`·`ipc/shared_frame.py`·`ipc/shared_state.py` 구현은 1:1 대응**. 문서에 없는 필드·메시지를 구현에 추가 금지. 추가가 필요하면 이 문서를 먼저 갱신.

---

## 0. 프로세스 토폴로지

```
main (= UI 프로세스)
  │
  ├─ SharedMemory("kbs_frame_v2")  [Detection→UI 프레임]
  ├─ SharedMemory("kbs_state_v2")  [양방향 상태]
  ├─ multiprocessing.Queue result_queue  [Detection→UI]
  ├─ multiprocessing.Queue cmd_queue     [UI→Detection]
  ├─ multiprocessing.Event shutdown_event  [정상 종료 브로드캐스트]
  ├─ multiprocessing.Event cmd_event       [cmd_queue 도착 알림, Detection 폴링 지연 제거]
  │
  └─ Watchdog Process (main이 spawn)
       │   — Detection params / shm names / queue handles / shutdown_event 전달
       └─ Detection Process (Watchdog이 직접 spawn/respawn)
```

- **Watchdog이 Detection을 소유**한다(spawn/kill/respawn 주체). main은 UI와 SharedMemory 생명주기만 책임진다.
- Queue/SharedMemory 핸들은 main이 생성 후 Watchdog·Detection에 전달. 재spawn 시에도 **동일한 핸들 재사용** (drain 후 계속).

---

## 1. SharedMemory 레이아웃

### 1.1 `kbs_frame_v2` — Detection→UI 프레임 (고정 6,220,832 bytes)

| offset | size | 타입 | 필드 | 비고 |
|-------:|-----:|-----|------|------|
| 0  | 8 | uint64 LE | `seq_no` | 쓰기 중=홀수, 안정=짝수 (Lamport-style) |
| 8  | 8 | float64 LE | `timestamp` | `time.time()` |
| 16 | 4 | uint32 LE | `width` | 현재 프레임 가로 |
| 20 | 4 | uint32 LE | `height` | 현재 프레임 세로 |
| 24 | 4 | uint32 LE | `channels` | 3 (BGR) 고정 |
| 28 | 4 | uint32 LE | `flags` | bit0: scale 적용됨 / bit1: no-signal 상태 |
| 32 | 6,220,800 | uint8[] | `pixels` | BGR row-major, 실사용은 `width*height*3` 바이트 |

- 버퍼 총량은 1920×1080×3 최대치로 고정 할당(재할당 없음). scale_factor로 축소 시 상단 `width*height*3`만 유효.
- **Tearing 방지 (Lamport seq)**
  - Detection write: `s = seq_no; seq_no = s | 1; memcpy pixels; seq_no = (s & ~1) + 2`
  - UI read: `s1 = seq_no; if s1 & 1: return None; memcpy to local; s2 = seq_no; if s1 != s2: return None; return copy`
  - 최악 1프레임 스킵 허용(=CLAUDE.md "1프레임 지연" 규칙과 일치).
- UI는 반드시 `.copy()` 후 반환 (CLAUDE.md 규칙).

### 1.2 `kbs_state_v2` — 양방향 상태 (64 bytes)

| offset | size | 타입 | 필드 | 방향 | 비고 |
|-------:|-----:|-----|------|------|------|
| 0  | 4 | uint32 LE | `magic` | 고정 | `0x4B425332` ('KBS2') |
| 4  | 4 | uint32 LE | `version` | 고정 | 현재 1 |
| 8  | 8 | uint64 LE | `write_seq` | - | 어느 쪽이든 쓸 때 +1 (디버깅용) |
| 16 | 1 | uint8 | `detection_enabled` | 양방향 | 0/1 |
| 17 | 1 | uint8 | `mute` | 양방향 | 0/1 |
| 18 | 1 | uint8 | `volume` | 양방향 | 0~100 |
| 19 | 1 | uint8 | `reserved` | - | 정렬 패딩 |
| 20 | 4 | float32 LE | `level_l` | Detection→UI | dB, -60.0~0.0 |
| 24 | 4 | float32 LE | `level_r` | Detection→UI | dB, -60.0~0.0 |
| 28 | 4 | uint32 LE | `reserved` | - | 향후 확장 |
| 32 | 32 | bytes | `reserved` | - | 향후 확장 |

- 동시 쓰기 보호: `multiprocessing.Lock` 1개를 `SharedStateBuffer`에 부착(빈도 낮음). read는 lock-free 허용.
- **heartbeat 자체는 `data/heartbeat.dat` 파일 유지**(CLAUDE.md 규칙 존중). SharedMemory에 중복 저장하지 않음.
- 전원 온/오프 등으로 magic이 0이면 UI는 "state not ready"로 처리하고 Detection 초기화를 기다림.

---

## 2. Queue 메시지 계약

모든 메시지는 dataclass. 필드는 **기본 타입·bytes·dict·list만** 사용(Windows spawn pickle 호환). 공통 베이스:

```python
@dataclass(kw_only=True)
class BaseMsg:
    ts: float  # time.time()
```

### 2.1 `result_queue` (Detection → UI, maxsize=200)

| 메시지 | 필드 | 발행 시점 |
|--------|------|-----------|
| `DetectionResult` | `label:str`, `roi_type:str('video'\|'audio'\|'embedded')`, `media_name:str`, `detection_type:str('black'\|'still'\|'audio_level'\|'embedded')`, `active:bool`, `duration_sec:float`, `meta:dict` | 감지 상태 변화(진입/종료) 시 각 1회 |
| `AlarmTrigger` | `label:str`, `detection_type:str`, `roi_type:str`, `media_name:str`, `dark_ratio:float`, `snapshot_jpeg:bytes\|None` | 감지 지속 시간 초과로 실제 알람 발화. `dark_ratio`는 블랙 알람 시점의 어두운 픽셀 비율(%) — 임계값 튜닝 관측용(비-블랙은 -1.0) |
| `AlarmResolve` | `label:str`, `detection_type:str`, `duration_sec:float`, `media_name:str` | 감지 해제로 알람 종료 |
| `LogEntry` | `level:str('info'\|'debug'\|'black'\|'still'\|'audio'\|'embedded'\|'error')`, `source:str`, `message:str` | Detection 측 로그 (UI 로그 위젯용 통합 표시). `error`=시스템 장애(스트림/크래시/녹화/텔레그램), `black`=블랙 감지, `debug`=개발자 전용(로그창 기본 숨김, "개발자" 토글로 표시 — 파일 로깅에는 영향 없음) |
| `DiagSnapshot` | `section:str`, `payload:dict` | 30초 주기 6개 섹션 발행 |
| `SignoffStateChange` | `group_id:int(1\|2)`, `prev_state:str`, `new_state:str('IDLE'\|'PREPARATION'\|'SIGNOFF')`, `source:str('auto-time'\|'auto-detect'\|'auto-revert'\|'manual'\|'restore')`, `suppress_alarm_sound:bool` | 정파 상태 전환. `auto-revert`=해제준비 시각 전 오감지 SIGNOFF의 PREPARATION 조기복귀. `suppress_alarm_sound`=플래핑 묶음 모드 중 전환 → UI가 정파 알림음 억제(docs_signoff_운영.md §8) |
| `RecordingEvent` | `event:str('start'\|'end'\|'extend'\|'drop')`, `label:str`, `filepath:str\|None`, `reason:str\|None` | 녹화 시작/종료/버퍼 드롭 |
| `TelegramStatus` | `event:str('sent'\|'failed'\|'retry'\|'worker_dead'\|'worker_restart')`, `message:str\|None`, `queue_size:int` | 텔레그램 워커 이벤트 |
| `StreamError` | `source:str('video'\|'audio')`, `message:str`, `retry_count:int` | 캡처/오디오 장애 및 재연결 |
| `DetectionReady` | `pid:int`, `config_loaded:bool`, `roi_count:int`, `version:str` | Detection 기동 완료 (**최초 기동 및 재spawn 직후 각 1회**) |
| `DetectionCrashed` | `dead_pid:int`, `reason:str('process_dead'\|'heartbeat_stale')`, `stale_sec:float` | Watchdog이 Detection 비정상 종료 감지 시 재spawn 직전 발행 (**drop 금지**) |
| `PerfMeasurement` | `recommended_interval:int`, `recommended_scale:float`, `cpu_percent:float`, `ram_percent:float` | `RequestAutoPerf` 응답 |

- `FrameReady` 메시지는 **정의하지 않음**. UI는 `SharedFrameBuffer`를 약 33ms 주기로 폴링하고 `seq_no` 변경 시 화면 갱신.

### 2.2 `cmd_queue` (UI → Detection, maxsize=50)

| 메시지 | 필드 | 발행 주체 |
|--------|------|-----------|
| `ApplyConfig` | `config:dict`, `reason:str('user_save'\|'auto_perf'\|'restore')` | 설정 저장/자동 성능감지 결과/재spawn 후 UI 재주입 |
| `UpdateROIs` | `rois:list[dict]` | ROI 편집 완료 |
| `SetDetectionEnabled` | `enabled:bool` | 감지 ON/OFF 버튼 |
| `SetVolume` | `volume:int(0-100)` | 볼륨 슬라이더 (debounce 100ms) |
| `SetMute` | `muted:bool` | Mute 버튼 |
| `SetSignoffState` | `group_id:int`, `new_state:str`, `source:str='manual'\|'restore'`, `entered_at:float=0.0` | 정파 상태 직접 설정. **주 용도는 재spawn 후 UI 재주입**(`source='restore'`, `entered_at`=원본 SIGNOFF 진입 시각). `source='restore'`인 경우 Detection은 텔레그램 발송을 생략하고 `entered_at`>0이면 SIGNOFF 진입 시각을 복원해 elapsed_sec 정확도를 유지 |
| `CycleSignoffState` | `group_id:int` | 수동 정파 순환 버튼 클릭. Detection이 `SignoffManager.cycle_state()`로 라우팅 — **시간대 인지** 순환(IDLE→PREPARATION, PREPARATION→정파시간대면 SIGNOFF·아니면 IDLE, SIGNOFF→IDLE). raw `SetSignoffState` 순환과 달리 시간대 밖 강제 SIGNOFF 후 자동 되돌림(튕김)을 방지 |
| `PauseForRoiEdit` | `paused:bool` | ROI 편집 모드 진입/종료 (detection skip, heartbeat 유지) |
| `ClearAlarms` | — | 감지 OFF 전환 시 남은 알람 강제 resolve |
| `RequestAutoPerf` | `duration_sec:float` | 설정 탭 "자동 성능 감지" 버튼 |
| `RequestSnapshot` | — | ROI 편집 시 현재 프레임 요청 (Detection은 SharedMemory에 1장 즉시 write) |
| `Shutdown` | `reason:str` | 정상 종료 |

### 2.3 백프레셔 / 드롭 정책

- 모두 `put_nowait()`. Full 시: `get_nowait()` 1개 drop → 재시도 1회 → 실패면 로그.
- 드롭 카운터는 `DiagSnapshot.section='DIAG-IPC'`에 포함: `{result_dropped, cmd_dropped, result_qsize, cmd_qsize}`.
- `DetectionReady` / `DetectionCrashed` / `Shutdown` / `SignoffStateChange`는 **drop 금지** (최대 3회 재put + 지연).

---

## 3. 프로세스 생명주기

### 3.1 기동 시퀀스

1. `main.py` 진입 → `multiprocessing.freeze_support()` → `os.chdir(_ROOT)` (cwd 를 프로젝트 루트로 고정 — PC별 실행 방식 차이로 발생하는 상대경로 PermissionError 방지) → `faulthandler.enable(logs/fault.log)` → `sys.excepthook` 후킹(unhandled exception traceback 을 `logs/YYYYMMDD_ui.txt` 에 기록)
2. 기존 SharedMemory 이름 잔존 확인: 각 이름으로 `create=False` 시도 → 성공 시 `unlink()`.
3. SharedMemory `kbs_frame_v2`·`kbs_state_v2` create. state는 magic/version 초기화, 나머지 0.
4. `result_queue(maxsize=200)`, `cmd_queue(maxsize=50)`, `shutdown_event`, `cmd_event` 생성.
5. **Watchdog 프로세스 spawn** (Detection params + shm names + queue handles + shutdown_event 전달).
   - Watchdog은 시작 직후 **`[SYSTEM]` 텔레그램 "기동" 통보 1회** 발송(app 버전 + `platform.python_version()`) — 최초 부팅·크래시 재spawn·예약 재시작 공통, 원격에서 재기동 여부·실행 중인 파이썬 버전 확인용(`notify_system` 게이트 적용).
   - Watchdog은 Detection을 즉시 spawn 후 감시 루프 시작.
6. Detection 기동 절차 (Watchdog이 수행):
   - `config/kbs_config.json` 직접 로드 → 내부 설정/ROI 복원.
   - 작업자 스레드 start (video_capture, audio_monitor, signoff_manager, telegram_worker, auto_recorder, heartbeat_writer).
   - `result_queue.put(DetectionReady(pid, config_loaded, roi_count, version))` (drop 금지).
7. `main` 프로세스는 `QApplication` + `MainWindow` 기동.
8. UI는 `DetectionReady` 수신 후 런타임 상태 재주입(아래 3.3) 수행.

### 3.2 정상 종료 시퀀스

1. UI 창 닫기 → `MainWindow.closeEvent`
2. `shutdown_event.set()` + `cmd_queue.put(Shutdown(reason='user'))`
3. Watchdog은 `shutdown_event` set 감지 → "의도된 종료" 플래그 ON (false positive respawn 방지).
4. Detection은 `Shutdown` 수신 → 작업자 스레드 join(개별 타임아웃 3초) → 종료.
5. Watchdog은 Detection join(timeout=5s) → 실패 시 `terminate()`.
6. Watchdog 자신 종료.
7. `main`: Watchdog join(timeout=8s) → 실패 시 terminate.
8. `data/last_exit.json` 기록: `{"exit_time":ISO8601, "exit_code":0, "reason":"user", "pid":<main pid>}`.
9. SharedMemory `close()` + `unlink()` (try-finally 보장).
10. `QApplication.quit()`.

### 3.3 Detection 재spawn 복원 시퀀스 (하이브리드)

1. Watchdog: `heartbeat.dat` 10초 stale 감지 OR Detection 프로세스 exit 감지.
2. `shutdown_event` 미set → 비정상 이탈 판정. `result_queue.put(DetectionCrashed(dead_pid, reason, stale_sec))`.
3. 텔레그램 알림: "감지 루프 중단 감지, 재시작 중" (Watchdog 프로세스에서 직접 발송 — UI 없이도 알림 보장).
4. 이전 Detection 프로세스: `terminate()` → `join(3s)` → 실패 시 `kill()`.
5. `result_queue` / `cmd_queue` **drain 불필요** (기존 핸들 재사용). SharedMemory 동일.
6. 새 Detection spawn.
   - 자체적으로 `config/kbs_config.json` 로드 + ROI 복원 (**Fast start**).
   - 작업자 스레드 start.
   - `result_queue.put(DetectionReady(pid, ...))` 발행.
7. UI `ui_bridge`가 `DetectionReady` 수신 → 다음 "런타임 상태"만 재주입:
   - `ApplyConfig(config=<UI가 보유한 현재 설정 snapshot>, reason='restore')` (설정 덮어쓰기, config 파일과 다를 수 있는 미저장 변경 포함)
   - `SetDetectionEnabled`, `SetVolume`, `SetMute`
   - `SetSignoffState` × 2 (그룹1, 그룹2 — UI가 보유한 마지막 상태)
   - `UpdateROIs` (UI 보유본; config와 다를 수 있음)
   - 알람 ack 상태는 **UI에만 존재**하므로 재주입 없음. Detection은 재감지 시점부터 새 `AlarmTrigger` 발행 → UI 측 ack 로직으로 자연 필터링.
8. 텔레그램 알림: "감지 복구 완료 (N초)".
9. UI 상단바 "감지 중단" 뱃지 해제.

### 3.4 UI 크래시 대응

- UI 프로세스(=main) 크래시 시 Watchdog은 `shutdown_event` 미set 상태에서 `os.getppid()` (자신의 부모=main)가 사라짐을 감지 → Detection 정리 후 자신도 종료 + 텔레그램 "전체 프로그램 비정상 종료" 발송.
- Linux: `prctl(PR_SET_PDEATHSIG)` 대안 없음(Windows). 대신 30초 주기로 parent 존재 확인 (`psutil.pid_exists(parent_pid)`).

### 3.5 UI "생존하되 손상" 대응 — 파일 기반 통보 채널

§3.4는 UI가 **죽는** 경우다. 그런데 UI가 **살아 있으면서 내부만 손상**되는 사고가 4회 발생했다 — 창·프레임·로그는 정상인데 순수 파이썬 클래스의 `__init__`이 전부 실패해 설정창·알림음·모든 조작이 먹통이 된다. Watchdog의 `pid_exists`로는 **절대 감지되지 않는다**(프로세스는 멀쩡히 살아 있다). 배경: `fix/260526_설정다이얼로그_TypeError_재현불가.md` §12.

**채널** (Queue·SharedMemory가 아닌 **파일**인 이유: 손상된 UI가 쓸 수 있는 유일하게 검증된 수단)

| 항목 | 값 |
|---|---|
| 경로 | `data/ui_degraded.flag` |
| 생산자 | UI(`main.py`) — `_DEGRADED_FLAG` |
| 소비자 | Watchdog(`processes/watchdog_process.py`) — `_UI_DEGRADED_FLAG` |
| 내용 | 1행: onset 시각 `YYYY-MM-DD HH:MM:SS` / 2행: `psutil_err` 원문 |
| 폴링 | Watchdog 1초 루프 |

**계약**
1. UI는 기동 시 이 파일을 **삭제**한다(이전 세션 잔재로 인한 오탐 방지).
2. UI는 HEALTH 스냅샷에서 psutil 쿼리 실패로 *처음 전환*되는 순간 `open()+write()`로 파일을 쓴다. **`requests`·객체 생성이 필요한 어떤 수단도 쓰면 안 된다** — 손상 상태에서 전부 실패한다.
3. UI가 회복하면(psutil 재성공) 파일을 삭제한다.
4. Watchdog은 파일이 **새로 나타난 순간 1회만** `[SYSTEM]` 텔레그램을 보낸다. 파일이 사라지면 재무장한다.

⚠ **경로는 두 파일에 하드코딩된 계약이다.** 한쪽만 바꾸면 통보가 예외 없이 조용히 죽는다(테스트로도 안 잡힌다). 변경 시 반드시 동시 수정 + 경로 일치 검증.

---

## 4. 구현 체크리스트 (Phase 0-B)

- [ ] `ipc/messages.py`: 위 2.1 / 2.2의 **모든** 메시지 dataclass 정의 (누락 금지)
- [ ] `ipc/shared_frame.py`: `write_frame(ndarray)` / `read_frame() -> ndarray|None` / `close()` / `unlink()` + Lamport seq
- [ ] `ipc/shared_state.py`: 필드별 getter/setter + magic 검증 + `multiprocessing.Lock`
- [ ] `ipc/__init__.py`에서 이 문서의 모든 클래스를 re-export

구현 후 반드시: `python -c "from ipc.messages import *"` 오류 없음 + `docs_ipc_spec.md §2` 표와 필드명 1:1 일치 재확인.

---

## 5. 향후 변경 규칙

- **새 메시지 추가 시**: 이 문서의 2.1/2.2 표에 먼저 행 추가 후 구현.
- **SharedMemory 레이아웃 변경 시**: `version` 필드 +1, UI는 기동 시 version mismatch를 감지하면 즉시 로그 + 종료.
- **필드 삭제 금지** (deprecated로 유지, 이름 앞 `_` 접두사).
