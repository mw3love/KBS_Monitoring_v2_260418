# 설정 다이얼로그 TypeError (재현불가) — 260526

> **상태**: **4건 발생** (260526, 260620, 260706, 260711). 코드 버그 아님 — UI 프로세스 국소 런타임 손상 확정.
> **최신은 §12 (4차 + Round 1 제거 실험)**. 여기부터 읽는 게 빠르다.
> **버전**: 1차 v2.2.7 / 2차 v2.7.1 / 3차 v2.7.5 / 4차 v2.7.9. 동일 코드 베이스.
> **결론**: 근본 원인 **미규명**. 관측 기반 접근(§10 계측, §11 디버그 할당자)은 4회 모두 범인 특정에 실패 →
> §12에서 **제거 실험(bisect)** 으로 전환. 동시에 손상을 즉시 통보하는 운영 완화 도입.

---

## 1. 증상

- **장소**: 다른 PC (`C:\Users\user\Desktop\KBS_Monitoring_v2_260418-master_v2.2.7\`)
- **시점**: 2026-05-26 새벽 정파해제(`04:50:12`) 이후 ~ 사용자 인지 시점(아침)
- **현상**: 메인 창은 정상 가동, 감지·정파 모두 정상이었으나 **`설정` 버튼 클릭이 무반응**. py.exe 터미널에 동일 traceback 반복 출력.
- **조치**: 재부팅 → 재기동 후 즉시 정상 (재발 없음).

## 2. 콘솔 traceback (사용자 원문)

```
DIAG - ROI[V8] 스틸 타이머 리셋 (누적 11.8초 → 0, 3프레임 연속 모션)
DIAG - ROI[V7] 스틸 타이머 리셋 (누적 6.2초 → 0, 3프레임 연속 모션)
DIAG - ROI[V8] 스틸 타이머 리셋 (누적 6.2초 → 0, 3프레임 연속 모션)
Traceback (most recent call last):
  File "C:\Users\user\Desktop\KBS_Monitoring_v2_260418-master_v2.2.7\ui\main_window.py", line 531, in _open_settings
    self._settings_dlg = SettingsDialog(
  File "C:\Users\user\Desktop\KBS_Monitoring_v2_260418-master_v2.2.7\ui\settings_dialog.py", line 343, in __init__
    self._cfg_mgr = ConfigManager()
TypeError: __init__() should return None, not 'NoneType'
```
(같은 traceback 4회 반복 — 사용자가 설정 버튼을 여러 번 시도)

## 3. 26일 로그 파일 상태

| 파일 | 첫 줄 | 비고 |
|---|---|---|
| `logs/260526/20260526_ui.txt` | `00:30:00 [INFO] [signoff] 1TV 정파준비모드를 시작합니다` | **04:50:12 ~ 08:51:21 사이 약 4시간 공백** (정상 감지 중 INFO 로그 없음). 사용자가 설정 버튼 누른 시점도 이 공백에 포함. |
| `logs/260526/20260526_detection.txt` | `08:51:22 [INFO] shutdown_event 감지 → 종료` | 재부팅 직전 종료 시점부터 기록. **이전 세션 detection 로그는 존재하지 않음** (참고: 25일까지 이 PC에선 ui 로그만 생성됨 — 그 PC를 25일까지 한 번도 재시작하지 않았다는 뜻). |
| `logs/260526/20260526_watchdog.txt` | `08:51:22 [INFO] shutdown_event 감지 → 의도된 종료` | 동일. |

→ **TypeError 자체는 어떤 로그 파일에도 없음**. 원인은 §5 참조.

## 4. 코드 분석

### `utils/config_manager.py:127-140` (ConfigManager.__init__)

```python
class ConfigManager:
    CONFIG_DIR = "config"
    CONFIG_FILE = "kbs_config.json"
    DEFAULT_FILE = "default_config.json"

    def __init__(self):
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        self._default_path = os.path.join(self.CONFIG_DIR, self.DEFAULT_FILE)
        self._config_path  = os.path.join(self.CONFIG_DIR, self.CONFIG_FILE)
        if not os.path.exists(self._default_path):
            self._write_json(self._default_path, DEFAULT_CONFIG)
```

- `return` 문 없음 → 항상 암묵적 `None` 반환.
- git log 상 `phase0-b`(2026-04-18) 이후 `__init__` 시그니처/본문 구조 변경 없음 (수정 이력은 `DEFAULT_CONFIG` 딕셔너리 값 조정뿐).

### 다른 호출처 동일 세션 정상

| 위치 | 호출 | 동일 세션 결과 |
|---|---|---|
| `processes/detection_process.py:197` | `cfg_mgr = ConfigManager()` | 정상 (재부팅 전후 모두 detection 로그 "설정 로드 완료" 기록) |
| `ui/main_window.py:51` | `self._cfg_mgr = ConfigManager()` | 정상 (창이 떠있던 사실로 입증) |
| `ui/settings_dialog.py:343` | `self._cfg_mgr = ConfigManager()` | **여기서만 실패** (게다가 재부팅 후엔 같은 자리에서 정상 — 26일 ui 로그 22행 `08:51:44 ApplyConfig 적용 완료 (reason=settings_save)`) |

### 에러 메시지 자체의 비정상성

`TypeError: __init__() should return None, not 'NoneType'` 는 CPython 내부 `slot_tp_init`의 다음 분기에서만 발생:

```c
if (res != Py_None) {
    PyErr_Format(PyExc_TypeError,
        "__init__() should return None, not '%.200s'",
        Py_TYPE(res)->tp_name);
}
```

- 메시지에 보고된 타입명이 **`NoneType`** — 즉 반환값 `res`의 `type(res).__name__ == "NoneType"` 이지만 `res is not Py_None`.
- 정상 파이썬에서 `NoneType`의 인스턴스는 `None` 단 하나(싱글톤)뿐. **위 조건은 정상 상태에서 만족 불가능.**
- 발생 가능한 정황:
  - Py_None 포인터가 가리키던 메모리가 GC/refcount 오류로 동일 타입의 다른 객체로 교체됨
  - C 확장(opencv / numpy / sounddevice / PySide6 / pycaw)의 refcount 누락이 누적되어 None 싱글톤 영역 손상
  - 메모리 오류(하드웨어 수준의 비트 플립)
  - 서브인터프리터 / 멀티 Py 런타임 충돌 (본 프로젝트는 단일 프로세스 내 단일 인터프리터 — 해당 없음)

## 5. 로그가 비어있는 이유

`TypeError`는 Qt 슬롯(`_open_settings`)에서 발생 → PySide6 기본 동작상 **stderr로 직접 traceback 출력**되고 슬롯에서 swallow됨. 본 프로젝트의 `AppLogger`는 `logger.info/error()` 호출로만 파일에 기록하므로 unhandled exception은 파일에 남지 않음.

→ 사용자가 콘솔(py.exe 터미널)을 닫는 순간 traceback도 사라짐. 사후 분석 불가.

## 6. 이번 세션 조치

### 6-1. 코드 변경 (단 1건)

- `main.py` 에 `sys.excepthook` 후킹 추가 → unhandled exception 발생 시 `logs/YYYYMMDD_ui.txt` 에 traceback째로 기록.
- `ConfigManager` / `SettingsDialog` 자체는 **변경하지 않음** (코드에 결함 없음).

### 6-2. 본 문서 작성

재발 시 본 문서 §2 traceback과 새 로그의 traceback을 직접 비교 → 동일 손상인지 / 다른 호출처에서도 발생하는지 / 어떤 C 확장이 직전에 활동했는지 단서 확보.

## 7. 재발 시 확인 체크리스트

발생 즉시 또는 가능한 한 빨리 다음을 수집/확인:

- [ ] `logs/YYYYMMDD_ui.txt` 의 `UNHANDLED EXCEPTION` 블록 traceback 원문
- [ ] 발생 시점의 가동 누적 시간 (재부팅 후 얼마나 지난 시점인가)
- [ ] `logs/fault.log` 에 faulthandler 출력 있는지 (있으면 C 레벨 segfault — 별개 문제)
- [ ] 같은 세션에서 다른 클래스 생성에도 비슷한 `should return None, not '...'` 가 발생하는지
- [ ] 그 PC의 `__pycache__/` 상태(혹시 모를 stale .pyc — 의심 시 전체 삭제 후 재기동)
- [ ] 메모리 진단(`mdsched.exe`) 결과 (1회 이상 발생 시 권장)
- [ ] 해당 PC에서 동시 가동 중이던 외부 프로세스 (백신 실시간 스캔 등)
- [ ] 설치된 Python / PySide6 / opencv-python / numpy / sounddevice 버전이 본 PC와 일치하는지

## 8. 운영적 완화 (현재 가능한 옵션)

- `system.scheduled_restart_enabled` (설정 다이얼로그 §탭 6) 를 켜면 장기 가동 누적 손상을 회피 가능. 기본값은 `false`.
- 본 문서가 누적되어 2건 이상 동일 패턴이 보이면, 그 시점에 코드/환경 차원의 근본 조치 검토.

## 9. 미해결 결정사항

- 본 1건만으로는 코드/환경 어느 쪽이 원인인지 단정 불가 → **추가 발생 시점까지 코드 수정 보류**.
- excepthook 외에는 어떠한 방어 코드도 추가하지 않음(원인 미상 상태에서 try/except 둘러싸기는 진단을 더 어렵게 함).

## 10. 2차 발생 (2026-06-20, v2.7.1) + 계측 보강

### 10-1. 증상·신규 증거
- **장소**: 운영 PC(전주). 6/15 16:49 기동 후 **약 4.7일 연속 가동**(무재시작) → 6/20 **08:10경 손상 시작**, 09:03 설정 클릭 시 표면화.
- **1차 때 없던 결정적 증거** (UI HEALTH 스냅샷 + excepthook 덕분):
  - `20260620_ui.txt` 08:00 `RSS=292MB handles=1308`(정상) → **08:10 `RSS=-1 handles=-1`** 로 전환. `threads=2`(순수 파이썬 `threading.active_count`)는 정상 → **C 확장(psutil)·네이티브 호출만 죽고 파이썬 바이트코드는 생존**.
  - 09:03 excepthook: `TypeError("__init__() should return None, not 'NoneType'")` + **`traceback` 표준 모듈 자체가 `'NoneType' object has no attribute 'partition'`로 포매팅 실패** → 인터프리터/네이티브 레벨 손상.
  - `fault.log` **0바이트** → faulthandler가 C레벨 segfault/abort를 못 잡음 = **하드 크래시 없이 "절뚝거린" 상태**(별개 segfault 문제 아님).
- **패턴 공통점**: 1차도 "장시간 무재시작", 2차도 4.7일 연속 → **장기 가동 누적 손상**이 가장 강한 공통 변수.

### 10-2. 관측 공백 발견
- detection/watchdog는 자기 건강상태(rss)를 **큐로만 UI에 보내고 파일엔 영속 안 함** → 손상 창에서 detection이 같이 망가졌는지 **사후 확인 불가**. ("UI 국소 손상 vs 시스템 전체"를 가를 데이터가 없음.)
- detection 파일 로거(`AppLogger`)는 날짜 로테이션 정상이나, detection은 기동·캡처상실·에러만 파일 기록 → 6/16~6/20 무사건이라 일별 파일 자체가 안 생성됨(정상 동작, 손상 무관).

### 10-3. 계측 보강 (코드 변경, "블랙박스 3개로 통일")
> 재현 전략은 유지(예약재시작 끈 채 자연 발생 대기 — [[settings-dialog-corruption-repro]] 합의). **막지 않고 카메라만 증설**.
- **UI(`main.py`)**: HEALTH 스냅샷이 지금까지 `except: pass`로 버리던 **psutil 예외 원문을 기록**. psutil 실패(RSS=-1)로 *첫 전환*되는 순간 1회 **onset 심층덤프**: 인터프리터 무결성 프로브(None 싱글톤·객체생성·gc) + `faulthandler.dump_traceback(all_threads)` → `logs/fault.log`.
- **detection(`processes/detection_process.py`)**: 10분 주기 `HEALTH DETECTION` 줄을 **자기 파일에 영속**(RSS/threads/handles/loop). onset 시 동일 프로브 + 스레드덤프 → `logs/fault_detection.log`(UI와 분리, 동시쓰기 충돌 방지).
- **watchdog(`processes/watchdog_process.py`)**: 10분 주기 `HEALTH WATCHDOG` + onset 프로브/덤프 → `logs/fault_watchdog.log`.
- 효과: **다음 재현 때 세 프로세스를 08:10 시점에 나란히 비교** → "UI만 vs 시스템 전체" 확정. onset의 `none_singleton_ok=False` 나 `fault_*.log` 스레드덤프로 손상 부위 특정. (객체생성 프로브는 손상 상태 SIGSEGV 위험·try/except 무력이라 제외 — 객체 init 손상 신호는 설정 클릭 시 excepthook TypeError로 어차피 포착.)
- 검증: 3파일 `py_compile` 통과 + onset 경로 정상상태 스모크(프로브 기대값·스레드덤프 기록 확인). **실손상 캡처는 미검증(프록시) — 운영 PC 재발 시 실조건 확인.**

### 10-4. 남은 권장(미실행)
- **환경 진단**(운영 PC): `mdsched`(RAM), 패키지 버전 dev 대조, 백신 실시간스캔. RAM 불량이면 이 경로로 종결 가능.
- **예약 재시작**: 근본원인 규명 후로 보류(최후의 보루). 켜면 재현 기회 소멸.
- **가속재현(dev)**: 보류 — dev≠운영 환경이라 false-negative 오진 위험(재현 실패=무죄 아님).

## 11. 3차 발생 (2026-07-06, v2.7.5) + PYTHONMALLOC=debug 배포

> **상태 갱신**: **3건 발생**. 이번에 §10-3 계측이 결정적 데이터를 잡음 → **UI 프로세스 단독 손상 확정**. 관찰 전략은 소임 완수, 여기서 **범인 특정을 위해 디버그 할당자로 접근 전환**.

### 11-1. 결정적 증거 — UI 프로세스 국소 손상 확정
- **장소/가동**: 운영 PC(전주). 07-01 13:41 기동 → 07-06 16:41 손상 시작 = **약 5.1일 연속 가동**. (1차 장기 / 2차 4.7일 / 3차 5.1일 → **~5일 누적 패턴 3회 일관**.)
- **§10-3에서 증설한 3프로세스 HEALTH 계측이 처음으로 나란히 비교 데이터 확보**:
  | 프로세스 | 손상 창(16:41~19:14) 상태 | 판정 |
  |---|---|---|
  | UI(main) | 16:31 `RSS=274MB`(정상) → **16:41 `RSS=-1` + `psutil_err=TypeError("__init__() should return None, not 'NoneType'")`**, 이후 고정. onset 프로브도 동일 에러로 실패. | **손상** |
  | Detection | 내내 `RSS~230MB threads=8 handles=798`, 에러 0 | **완벽 정상** |
  | Watchdog | 내내 `RSS=66MB threads=1 handles=329`, 에러 0 | **완벽 정상** |
  - → **손상은 UI 프로세스에 국소**. Detection/Watchdog 무사 → **시스템 전체(RAM 하드웨어) 가설 크게 약화**(비트플립이 2.5시간+ 동안 오직 UI만 선택적으로 오염시키는 건 RAM 고장 양상이 아님).
- **`fault.log` 이번엔 내용 있음**(§10-3 onset 덤프 작동): `QueueFeederThread`/`UIBridge`/`main` 정상 스택, 행·데드락 없음 → **힙/None 싱글톤 손상**과 일치. faulthandler `dump_traceback`일 뿐 크래시 핸들러 아님 = **세그폴트 아닌 "절뚝거림"**.
- 19:13~19:14 설정 클릭 → excepthook에 동일 `TypeError` 4회 + `traceback` 표준모듈 자체가 `str.partition` None 반환으로 포매팅 실패(§10-1 2차와 동일 서명).
- **환경**: dev·운영 **둘 다 Python 3.14.2** → 파이썬 버전은 두 PC 간 차이 아님(단 3.14는 양쪽 다 최신예 → C 확장 안정성은 공통 리스크). `pycaw`는 dev 미설치/운영 설치 → UI 고유 네이티브 표면(**PySide6 / pycaw(COM) / psutil / GPUtil**) 중 후보.

### 11-2. 접근 전환 — 관찰만으론 범인 특정 불가 (구조적 한계)
- HEALTH 스냅샷·excepthook은 **"언제 표면화됐나"만** 알려줄 뿐, **"어느 확장이 언제 힙을 깼나"는 구조적으로 못 잡음**(관찰 시점엔 이미 오염이 몇 시간 전 종료). 3번째 계측 추가 후 4번째 발생 대기 = 같은 막다른 길(스턱-루프).
- → **다른 메커니즘: `PYTHONMALLOC=debug`(CPython 디버그 할당자).** 모든 할당 앞뒤 가드바이트(`0xFD`), 매 `malloc`/`free` 검사 → wild write를 **오염 직후** fatal 검출 + faulthandler 덤프. "조용한 5일 절뚝거림" → "오염 지점 근처 즉시 큰 소리로 죽음". 오염이 연속적이면 5일 안 기다리고 조기 검출 가능성.
- **안전망(onset 자가치유)·예약재시작 모두 OFF 결정**: 손상된 프로세스 자체가 해부할 표본 → 재시작하면 증거 소멸·디버그 할당자 fatal과 충돌. 운영 연속성은 이 시점 목표 아님(**테스트 기간, 사용자 명시** — [[settings-dialog-corruption-repro]]).

### 11-3. 코드 변경 (런처만, 앱 코드 무변경)
- **`실행.bat`**: `set PYTHONMALLOC=debug` + main.py stderr를 `logs\stderr_debug.txt`에 캡처(디버그 할당자의 C 위반 메시지·주소는 stderr로 나오므로 보존). **자동시작이 `실행.bat`을 등록**하므로 운영 PC 자동 적용.
- **`디버그실행.bat`**: `PYTHONMALLOC=debug` 추가(로컬 디버그 일관성).
- `PYTHONDEVMODE`는 **배제**(경고 stderr 스팸이 핵심 위반 메시지를 파묻음). `ConfigManager`/`SettingsDialog`/main.py 등 앱 코드 무변경.
- **검증(프록시)**: `PYTHONMALLOC=debug` 인터프리터 정상 기동(3.14.2), `bogus` 값은 `preconfig_init_allocator` fatal → 변수 파싱 확인. **실손상 fatal 경로는 운영 재발 시 실조건 확인(미검증).**

### 11-4. 다음 재발 시 (체크리스트)
- [x] `logs\fault.log`(파이썬 스택) + `logs\stderr_debug.txt`(C 위반 종류·블록 주소) 두 파일 = **범인 특정 단서**.
- [x] **배포 필수**: 운영 PC 로컬 복사본(`C:\Users\user\Desktop\...`)에 `실행.bat` 덮어쓰기 + **재기동**.
- [ ] 디버그 할당자 덤프가 파이썬 스택까지만 주고 확장 특정이 애매하면 **에스컬레이션: Windows PageHeap(gflags/Application Verifier) on python.exe** → wild write 인스트럭션에서 C 레벨 스택.

---

## 12. 4차 발생 (2026-07-11 onset, v2.7.9) — 관측 노선 종료, 제거 실험으로 전환

> **이번의 핵심**: ⓐ `PYTHONMALLOC=debug`가 **아무것도 잡지 못했다**(§11의 계획 실패). ⓑ 대신 증상의 정체가
> 처음으로 정확히 규명됐다 — **"순수 파이썬 클래스의 `__init__` 호출만 골라서 실패"**. ⓒ 그 결과 피해가
> 설정창에 그치지 않고 **모든 알림음**에 미쳤음이 드러났다(운영 안전 문제).

### 12-1. 타임라인 — 42시간 블라인드

| 항목 | 값 |
|---|---|
| 기동 | 07-07 12:00:32 |
| **onset** | **07-11 15:30~15:40** (HEALTH 10분 해상도) — 가동 **4.15일** |
| 사용자 인지 | 07-12 23:14 (원격접속해 설정 버튼 클릭) |
| 복구 | 07-13 09:27 재부팅 |
| **손상 창** | **약 42시간** |

가동 누적 ~5일 패턴 **4회 일관** (1차 장기 / 2차 4.7일 / 3차 5.1일 / 4차 4.15일).

### 12-2. 증상의 정체 — "순수 파이썬 `__init__`만 실패"

stderr의 예외 **20건 전부**를 UI 로그의 `UNHANDLED EXCEPTION` **20건과 1:1 대조**해 완전 계상했다. 발생 지점은 **정확히 3곳**:

| 발생 지점 | 횟수 | 운영상 의미 |
|---|---|---|
| `ui/alarm.py:187` `play_signoff_sound` (`threading.Thread()`) | 9 | **정파 진입·해제 알림음 9회 전부 무음** |
| `ui/settings_dialog.py:353` (`ConfigManager()`) | 10 | 설정창 클릭 10회 전부 실패 |
| `ui/alarm.py:256` `_play_sound` (`threading.Thread()`) | 1 | **07-13 00:42 실제 블랙 경보 알림음 무음** |

07-13 `00:41:53` 예외 → `00:42:00` 「블랙 알림 전송 완료 (V7 모악 2UHD ON-AIR)」.
**진짜 블랙 장애에 현장 경보음이 안 울리고 텔레그램만 나갔다.** Detection이 텔레그램을 직접 보내므로
**정파 텔레그램이 정상 도착한 사실이 오히려 손상을 은폐했다.**

→ **작동한 것**: 창 렌더·프레임 갱신(Qt C++ 객체), 파일 로깅, CPU/RAM 표시, `datetime`, `threading.active_count()`.
→ **실패한 것**: `ConfigManager()`, `threading.Thread()`, `threading.Event()`, `psutil.Process()`, `import gc` — 전부 **파이썬 레벨 `__init__`**(C 타입은 `tp_init`이 C라 무사).
→ 그래서 **창은 멀쩡해 보였고**, 조작·경보만 죽은 "좀비" 상태였다.

### 12-3. 3프로세스 비교 — UI 국소 재확인

| 프로세스 | 손상 창(42h) 상태 | 판정 |
|---|---|---|
| UI(main) | `RSS=-1` 고정 + `psutil_err=TypeError(...)`. onset 프로브도 `import gc`에서 동일 실패. | **손상** |
| Detection | RSS·threads=8·handles~796 미동, 에러 **0건** | **완벽 정상** |
| Watchdog | RSS=75MB·threads=1·handles=329 미동, 에러 **0건** | **완벽 정상** |

- **RSS 329MB·handles 1344가 4일간 완전히 평평** → 누수·자원고갈이 아니라 **단발성 손상**.
- RAM 하드웨어 가설 사실상 배제(비트플립이 42시간 동안 오직 UI만 선택적으로 오염시킬 수 없다).

### 12-4. `PYTHONMALLOC=debug` 결과 — **무소득** (§11 계획 실패)

`stderr_debug.txt`(423KB) 전수 검색: **가드바이트 위반·`Debug memory block` 계열 메시지 0건.**
잡힌 건 전부 손상 *이후*의 하류 증상뿐 —
`ValueError: concurrent send_bytes()`(QueueFeederThread 사망), `SharedMemory.__del__`의 `self._buf.release()` AttributeError(= `__init__` 실패의 잔해).

→ **malloc 블록 경계를 침범하는 전형적 wild write가 아니다**(디버그 할당자는 자기 블록 경계만 지킨다).
→ **§11이 걸었던 유일한 능동적 카드가 빗나갔다.** 관측 증설 노선은 여기서 소진.

### 12-5. 접근 전환 — 관측 → 제거(bisect)

**구조적 한계**: HEALTH·excepthook·디버그 할당자는 모두 **수동 관측**이라 "언제 표면화됐나"만 알려줄 뿐
"무엇이 힙을 깼나"는 원리적으로 못 잡는다. **4회 발생 · 4회 확인 · 범인 0명.**
5번째 계측을 추가하고 5차를 기다리는 것은 같은 막다른 길(스턱루프).

**제거 대상 후보** — UI 프로세스만 가진 고빈도 네이티브 활동(Detection·Watchdog엔 없음):

| 후보 | 5일간 횟수 | 제거 비용 |
|---|---|---|
| `SysMonitorWidget` GPU 조회 → **nvidia-smi 새 프로세스** (2초 주기) | 약 **21만 회** | GPU % 표시만 잃음 |
| `SysMonitorWidget` psutil (2초 주기) | 약 21만 회 | 갱신 주기만 느려짐 |
| `video_widget._display_numpy` → `QImage(rgb.tobytes(), ...)` (33ms) | 약 **260만 회** | 없음 (버퍼 고정만) |

- **GPUtil도 서브프로세스를 띄운다** (`GPUtil.py:81` `Popen([nvidia_smi, ...])`) — 순수 파이썬 래퍼가 아니다. 운영 PC는 GPU % 표시가 뜨므로 이 경로가 **실제로 돌고 있었다**.
- `QImage(rgb.tobytes(), ...)`는 **이름 없는 임시 bytes**를 넘긴다. QImage는 버퍼를 복사하지 않으므로 다음 줄 `fromImage()`가 해제된 메모리를 읽을 위험(PySide6 대표 함정). 다만 화면이 며칠씩 정상이었으므로 PySide6가 참조를 잡아줄 가능성이 크다 — **확정 아님, 그러나 고치는 비용이 0이라 arm에 포함**.

⚠ **어느 후보도 로그 증거로 지목된 게 아니다.** "UI에만 있고, 제거 가능하고, 빈도가 압도적"이라는 소거법상의 추론일 뿐이다.

### 12-6. Round 1 (v2.8.0) — 공짜 변경은 전부 묶는다

> **원칙 수정**: "라운드당 변수 하나"는 교조적이었다. **비용 0인 변경끼리는 묶는 게 유리하다** —
> 안 죽으면 그대로 두면 되고(어느 게 범인인지 몰라도 잃는 게 없다), 또 죽으면 **한꺼번에 무죄 처리**된다.
> 하나씩 분리해야 하는 건 **되돌리고 싶어질 대가 있는 변경**뿐이다(→ Python 3.13은 Round 2).

**운영 완화 (실험과 무관, 근본원인 규명을 방해하지 않음 — 덤프·표본은 그대로 남긴다)**

1. **onset → 텔레그램 즉시 통보.** ⚠ **단, UI가 직접 보내면 안 된다** — 손상된 UI는 `requests`를 쓸 수 없다
   (파이썬 객체 생성 전면 실패. 4차 로그에서 onset 프로브가 `import gc`에서 이미 실패했다).
   → **UI는 `data/ui_degraded.flag`에 `open()+write()`로 플래그만 떨어뜨리고**(손상 상태에서 42시간 작동이
   실증된 유일한 경로), **Watchdog(1초 루프, 4회 모두 건강)이 읽어 대신 발송**한다.
   `main.py`: `_DEGRADED_FLAG` 기록 + 기동 시/회복 시 제거. `watchdog_process.py`: `_check_ui_degraded()` 1회 통보·회복 시 재무장.
   → **42시간 블라인드 → 10분.**

2. **패스스루 출력 침묵 실패 제거** (`detection/audio_monitor.py`). 기존 `output_stream.write()`가
   `except Exception: pass` 라 출력 스트림이 죽어도 **로그도 복구도 없이 영구 무음**이었다.
   → 연속 실패 카운트 → 재오픈 → 로그. `output_stream is None`이면 30초마다 재오픈 재시도.
   재오픈·로그 모두 30초 rate limit(청크가 초당 ~43개라 없으면 로그 폭주).
   ⚠ **4차의 "패스스루 무음"은 이 버그가 원인일 가능성이 높다** — §12-2의 예외 20건이 3곳으로 완전 계상되어
   **스피커 아이콘 클릭(`main_window.py:225` `SetMute()`)에서 나온 예외는 한 건도 없다.**
   즉 **UI 손상과 같은 원인이라는 증거가 없다.** (프록시 추론 — 실조건 미확인)

**실험 arm (전부 비용 0)**

3. `system.sysmon_gpu_enabled = false` → **nvidia-smi 프로세스 생성 완전 차단**.
4. `system.sysmon_interval_ms = 10000` → psutil 폴링 2초 → 10초.
5. `video_widget.py`: `buf = rgb.tobytes()` 지역변수로 **버퍼 수명 고정** 후 `QImage(buf, ...)`.

**추적**

6. 버전 **v2.8.0**. 기동 로그에 **실험 arm 명시**:
   `SYSTEM - EXPERIMENT: sysmon_gpu=False sysmon_interval_ms=10000 qimage_buf_pinned=True python=3.14.2`
   → 5일 뒤 "어느 빌드가 돌았나"를 **기억이 아니라 로그**로 확인한다. (git 브랜치는 쓰지 않는다 —
   운영 PC는 git 체크아웃이 아니라 손으로 복사한 폴더라 브랜치가 거기까지 가지 않는다.)
7. 폐기 빌드는 태그 **`v2.7.9-incident4`** 로 영구 고정.

**검증 (실측)**
- 9개 파일 `py_compile` 통과.
- `_DEGRADED_FLAG` 경로가 main/watchdog 두 프로세스에서 **동일 파일로 해석됨** 확인(오타 시 통보가 조용히 죽음).
- `ConfigManager._merge_defaults` 검증: 운영 PC의 구 `kbs_config.json`(gitignore 대상이라 새 키 없음)에서도
  `DEFAULT_CONFIG`가 병합돼 **실험 arm이 적용됨**.
- SysMonitorWidget 실측: `gpu_enabled=False` → **서브프로세스 호출 0회**, CPU/RAM 정상. **대조군**(`True`) → 7회 호출
  → "0회"가 테스트 둔감이 아니라 **실제 차단**임을 확인.
- VideoWidget 300프레임 렌더 → 예외 없음, 픽스맵 정상.
- ⚠ **미검증(프록시)**: onset→플래그→텔레그램 **실경로는 실제 손상 상태에서 미확인**. 다음 재발이 실조건 검증이다.

### 12-6-b. Round 1 배포 기록 (실측 — 판정의 기준점)

> 7일 뒤 판정할 때 **기억이 아니라 이 표**를 본다.

| 항목 | 값 |
|---|---|
| **기동 시각 (5일 카운터 시작점)** | **2026-07-13 11:00:00** |
| 판정 시점 | 5일 ≈ **2026-07-18** / 7일 ≈ **2026-07-20** |
| 운영 PC | **4차와 동일 PC** (하드웨어 변수 없음) |
| Python | **3.14.3** (4차 사고 때는 3.14.2 — 패치 1단계 상승, 의도치 않은 변수) |
| 기동 로그 | `SYSTEM - KBS On-Air Monitoring v2.8.0 시작` + `SYSTEM - EXPERIMENT: sysmon_gpu=False sysmon_interval_ms=10000 qimage_buf_pinned=True python=3.14.3` |
| 상단바 GPU | `GPU OFF` (실측 확인) |
| 설정 복원 | `260627 kbs_config_backup.json` 불러오기 (11:00:31 `ApplyConfig reason=settings_save`). ROI 8V+6A+1EA 복원 확인 |
| 텔레그램 | `enabled` ✓ / `연결 테스트` 성공 ✓ / **`notify_system`(시스템 이벤트 알림) 체크 ✓** |
| 예약 재시작 | **OFF** ✓ (하위 필드 비활성 확인) |

⚠ **배포 시 반드시 확인할 함정 — 「연결 테스트 성공」은 손상 통보를 보장하지 않는다.**
onset 통보는 `notify_system` 게이트를 통과해야 나간다(`watchdog_process.py`: `if not tg.get("notify_system", True): return False`).
그런데 설정창의 **`연결 테스트` 버튼은 토큰·chat_id로 직접 쏘므로 이 게이트를 우회한다**(`settings_dialog.py:48`).
→ **테스트는 성공하는데 실제 손상 통보는 안 나가는 상태가 성립한다.** 두 가지를 따로 확인할 것:
1. `알림설정` 탭 → `시스템 이벤트 알림 (재spawn, 비정상종료 등)` 체크 = `telegram.notify_system`
2. `연결 테스트` 성공

⚠ **`config/kbs_config.json`은 gitignore 대상이라 새 빌드에 안 따라온다.** 신규 clone 후 첫 기동은 항상
ROI 0개·텔레그램 OFF 상태로 뜬다(정상). `저장/불러오기` 탭에서 백업을 불러와야 운영 설정이 복원된다.
→ 기동 로그의 `영상 감지영역(ROI) 0개` 경고는 **불러오기 전 과도기 상태**일 뿐, 그 뒤 `ApplyConfig (reason=settings_save)`가
찍혔다면 정상이다. (이 줄만 보고 "설정 유실"로 오판하지 말 것.)

### 12-7. Round 1 판정 기준 (5일 뒤)

⚠ **예약 재시작(`scheduled_restart_enabled`)은 반드시 OFF여야 한다.** 켜져 있으면 매일 재시작되어
5일 시계가 절대 도달하지 않고, "안 죽었다"가 실험 arm 덕분인지 재시작 덕분인지 **구분 불가**가 된다.
→ 2026-07-13 배포 시 **OFF 확인 완료**(§12-6-b).

**판정 (기준점: 2026-07-13 11:00 기동)**

- **~7일 넘게 무사 (≥ 07-20)** → arm 3·4·5 중 하나가 범인. 셋 다 없어도 되는 것들이므로 **그대로 두고 종결**.
  단 Python 3.14.2 → 3.14.3 상승이 함께 일어났으므로(§12-6-b) **"우리 arm 덕분"이라고 100% 단정할 수는 없다.**
  운영상으로는 무해하나, 기록할 땐 이 한계를 명시할 것.
- **또 ~5일에 죽음 (≈ 07-18)** → **arm 3개 다 무죄** + **Python 3.14.3도 무죄** + **하드웨어 무죄**(동일 PC).
  남는 것은 PySide6 본체 / Python 3.14 계열 자체 → **Round 2: Python 3.13 다운그레이드**(코드 무변경).
- 어느 쪽이든 **onset 텔레그램 덕분에 10분 안에 알게 된다** — 4차의 42시간 블라인드는 재발하지 않는다.
- ⚠ **재발 시 즉시 회수할 것**: `logs/YYYYMMDD_ui.txt`(HEALTH·onset·excepthook), `logs/fault.log`,
  `logs/stderr_debug.txt`, `logs/*_detection.txt`, `logs/*_watchdog.txt`, `data/ui_degraded.flag`.
  **재부팅 전에 복사**할 것 — 재부팅하면 손상 표본이 사라진다.

### 12-8. 남은 권장 (미실행)
- **Round 2**: Python 3.13 다운그레이드 (유일하게 대가 있는 변경 → 분리).
- **에스컬레이션**: Windows PageHeap / Application Verifier (무겁고 성능 타격 — 최후수단).
- **환경 진단**: 운영 PC `mdsched`(RAM) — 우선순위 낮음(UI 국소 손상이라 하드웨어 가설은 약해졌다).

### 12-9. Round 1 판정 결과 (2026-07-20, 운영 PC 로그 전수 검토)

**상태: 손상 재발 0건 — 잠정 통과.** 운영 PC의 07-13~07-20 로그(3프로세스 전부)를 회수해 검토.

**타임라인 (재부팅 confound 발생)**

| 구간 | 기간 | 결과 |
|---|---|---|
| Run 1 | 07-13 11:00 → **07-18 22:37 (사용자 수동 재부팅)** = **5.48일** | 무손상 |
| Run 2 | 07-18 22:37 재기동 → 07-20 08:07(로그 끝) = 약 1.4일 | 무손상 (진행 중) |

- 재부팅 직전 사용자가 로그창 정상 조작 육안 확인(= UI 손상 아님).
- 손상 지표 전수 0건: `RSS=-1`(onset) / `UNHANDLED EXCEPTION`·`TypeError` / `ui_degraded.flag`(미생성). UI HEALTH RSS 190~221MB 평탄, threads=2 고정.

**판정 근거** — 과거 4회 온셋은 누적 **4.15~5.1일**(3차 5.1 / 4차 4.15). Run 1은 그 창 전체를 넘겨 **5.48일 무손상 통과** → 재부팅은 위험 구간이 닫힌 *뒤*라 표본 유효. §12-7의 `또 ~5일에 죽음`은 **미발생**.

⚠ **미확정으로 남는 것 2가지** (정직 표기):
1. §12-7이 confidence bar로 잡은 **7일 연속**은 수동 재부팅으로 끊겨 미완성. → Run 2를 손대지 말고 새 7일(≈**07-25**)까지 관찰 후 최종 종결.
2. Python `3.14.2→3.14.3` 상승이 arm과 동반(§12-6-b) → "arm 덕분"이라 100% 단정 불가. 운영상 무해하나 기록 시 명시.

**결론**: 잠정 통과로 arm 유지. Run 2 07-25 무손상 시 종결, 재발 시 Round 2(§12-8).
