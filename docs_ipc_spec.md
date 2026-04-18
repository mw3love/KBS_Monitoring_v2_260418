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
| `AlarmTrigger` | `label:str`, `detection_type:str`, `roi_type:str`, `snapshot_jpeg:bytes\|None` | 감지 지속 시간 초과로 실제 알람 발화 |
| `AlarmResolve` | `label:str`, `detection_type:str`, `duration_sec:float` | 감지 해제로 알람 종료 |
| `LogEntry` | `level:str('info'\|'error'\|'still'\|'audio'\|'embedded')`, `source:str`, `message:str` | Detection 측 로그 (UI 로그 위젯용 통합 표시) |
| `DiagSnapshot` | `section:str`, `payload:dict` | 30초 주기 6개 섹션 발행 |
| `SignoffStateChange` | `group_id:int(1\|2)`, `prev_state:str`, `new_state:str('IDLE'\|'PREPARATION'\|'SIGNOFF')`, `source:str('auto'\|'manual'\|'trigger')` | 정파 상태 전환 |
| `RecordingEvent` | `event:str('start'\|'end'\|'extend'\|'drop')`, `label:str`, `filepath:str\|None`, `reason:str\|None` | 녹화 시작/종료/버퍼 드롭 |
| `TelegramStatus` | `event:str('sent'\|'failed'\|'retry'\|'worker_dead'\|'worker_restart')`, `message:str\|None`, `queue_size:int` | 텔레그램 워커 이벤트 |
| `StreamError` | `source:str('video'\|'audio')`, `message:str`, `retry_count:int` | 캡처/오디오 장애 및 재연결 |
| `DetectionReady` | `pid:int`, `config_loaded:bool`, `roi_count:int`, `version:str` | Detection 기동 완료 (**최초 기동 및 재spawn 직후 각 1회**) |
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
| `SetSignoffState` | `group_id:int`, `new_state:str` | 수동 정파 순환 버튼 |
| `PauseForRoiEdit` | `paused:bool` | ROI 편집 모드 진입/종료 (detection skip, heartbeat 유지) |
| `ClearAlarms` | — | 감지 OFF 전환 시 남은 알람 강제 resolve |
| `RequestAutoPerf` | `duration_sec:float` | 설정 탭 "자동 성능 감지" 버튼 |
| `RequestSnapshot` | — | ROI 편집 시 현재 프레임 요청 (Detection은 SharedMemory에 1장 즉시 write) |
| `Shutdown` | `reason:str` | 정상 종료 |

### 2.3 백프레셔 / 드롭 정책

- 모두 `put_nowait()`. Full 시: `get_nowait()` 1개 drop → 재시도 1회 → 실패면 로그.
- 드롭 카운터는 `DiagSnapshot.section='DIAG-IPC'`에 포함: `{result_dropped, cmd_dropped, result_qsize, cmd_qsize}`.
- `DetectionReady` / `Shutdown` / `SignoffStateChange`는 **drop 금지** (최대 3회 재put + 지연).

---

## 3. 프로세스 생명주기

### 3.1 기동 시퀀스

1. `main.py` 진입 → `multiprocessing.freeze_support()` → `faulthandler.enable(logs/fault.log)`
2. 기존 SharedMemory 이름 잔존 확인: 각 이름으로 `create=False` 시도 → 성공 시 `unlink()`.
3. SharedMemory `kbs_frame_v2`·`kbs_state_v2` create. state는 magic/version 초기화, 나머지 0.
4. `result_queue(maxsize=200)`, `cmd_queue(maxsize=50)`, `shutdown_event` 생성.
5. **Watchdog 프로세스 spawn** (Detection params + shm names + queue handles + shutdown_event 전달).
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
7. `main`: Watchdog join(timeout=5s) → 실패 시 terminate.
8. `data/last_exit.json` 기록: `{"exit_time":ISO8601, "exit_code":0, "reason":"user", "pid":<main pid>}`.
9. SharedMemory `close()` + `unlink()` (try-finally 보장).
10. `QApplication.quit()`.

### 3.3 Detection 재spawn 복원 시퀀스 (하이브리드)

1. Watchdog: `heartbeat.dat` 10초 stale 감지 OR Detection 프로세스 exit 감지.
2. `shutdown_event` 미set → 비정상 이탈 판정. `result_queue.put(LogEntry(level='error', ...))`.
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
