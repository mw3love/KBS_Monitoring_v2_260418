# 설정 다이얼로그 TypeError (재현불가) — 260526

> **상태**: **6건 발생** (260526, 260620, 260706, 260711, 260724, 260811). Round 2(Python 3.13) 결론(범인은 Python 3.14 계열)은 **유지·재확증**됐으나, §13-10의 "해결 확정"은 **운영 사각지대였음이 드러났다** — 2026-08-07 재배포가 `.venv313`을 조용히 지워 08-07~08-12 닷새 내내 아무도 모르게 3.14로 돌고 있었다(§14).
> **최신은 §14 (6차 발생 — 배포가 Round 2 픽스를 조용히 무효화한 경위 + 재확증된 onset traceback)**. §13-10~11은 그 자체로는 유효한 13일 표본이지만 "이후로도 3.13이 돈다"는 전제가 §14에서 깨졌으니 함께 읽을 것.
> **버전**: 1차 v2.2.7 / 2차 v2.7.1 / 3차 v2.7.5 / 4차 v2.7.9 / 5차 v2.8.1. 동일 코드 베이스.
> **결론**: 근본 원인 **미규명**. 관측 기반 접근(§10 계측, §11 디버그 할당자)은 4회 모두 범인 특정에 실패 →
> §12 제거 실험(Round 1: GPU폴링·psutil주기·QImage버퍼)도 **5차 재발로 부결** → §13에서 **Round 2(Python 3.13 다운그레이드)** 로 전환.
> 단, §12의 운영 완화(onset→텔레그램 즉시통보)는 5차에서 **최초로 실조건 검증 — 완벽 작동**(42시간 블라인드 → 2초).

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

## 13. 5차 발생 (2026-07-24, v2.8.1) — Round 1 부결 + 텔레그램 완화 실조건 검증 성공 + Round 2 진입

> **판정 트리거**: §12-7이 사전등록한 두 갈래 중 **"또 ~5일에 죽음"** 갈래가 실현됐다(§12-9의 07-25 판정일 하루 전).
> **동시에 벌어진 것**: §12-6 운영 완화(onset→텔레그램)가 **최초로 실손상 상태에서 작동**해, 이번 회차는
> 관측 공백 없이(42시간 → 2초) 전 과정이 로그로 재구성됐다.

### 13-1. 타임라인 — 관측 공백 사실상 0

| 항목 | 값 |
|---|---|
| 기동 | **07-20 10:37:40** (v2.8.1, §12-9 Run 2의 연속이 아니라 **v2.8.1 배포로 인한 새 재기동**) |
| 실험군 유지 확인 | `SYSTEM - EXPERIMENT: sysmon_gpu=False sysmon_interval_ms=10000 qimage_buf_pinned=True python=3.14.3` (기동 로그 원문, Round 1과 동일 설정) |
| onset | **07-24 15:17:55** |
| **가동 누적** | **4.19일** — 1~4차(장기 / 4.7 / 5.1 / 4.15일)와 같은 위험창 재확인 (5회 일관) |
| 플래그 기록 → Watchdog 감지 → 텔레그램 발송 | 15:17:55 → 15:17:56 → **15:17:57 (2초)** |
| 사용자 실인지 (원격 설정 클릭 재현) | 16:23~16:24 (excepthook `TypeError` 2회, 4차와 동일 서명) |

- v2.8.1은 07-20 09:13/09:45 두 커밋(`4f18cea`/`794931f`)으로 푸시됐고 실제 코드 변경분은 `processes/detection_process.py`의 진단 로깅(블랙 복구 누락 추적)뿐 — **`ui/` 코드는 4차와 완전히 동일**. 이번 재발이 새 코드 때문일 가능성은 배제.
- 이 기동은 §12-9가 관찰하던 Run 2(07-18 22:37~)의 연속이 아니라 **독립된 새 재기동**이다. 즉 Round 1 실험군은 **서로 다른 두 부팅에서** 위험창에 도달했고, 두 번째 부팅은 실제로 재발했다 — 우연이 아니라 패턴이 강화된 것으로 판단.

### 13-2. 3프로세스 비교 — 5회째 동일 패턴

| 프로세스 | 손상 창 상태 | 판정 |
|---|---|---|
| UI(main) | `RSS=-1` 고정 + `psutil_err=TypeError("__init__() should return None, not 'NoneType'")`, `traceback.partition` 포매팅 실패까지 동일 서명 | **손상** |
| Detection | RSS 230~250MB대 평탄, 에러 0건 | **완벽 정상** |
| Watchdog | RSS 74~78MB대 평탄, 에러 0건, 플래그 감지·발송 정상 수행 | **완벽 정상** |

`stderr_debug.txt`(`PYTHONMALLOC=debug`) 가드바이트 위반 **0건** — 3차(§11)·4차(§12-4)와 동일하게 이 경로는 추가 단서 없음. 손상 창에 블랙/정파 등 알림음이 필요한 이벤트는 없었음(직전 14:12 블랙·복구 알림 정상 완료 후 발생) — 이번엔 무음 경보로 인한 운영 공백은 없었다.

### 13-3. 운영 완화 실조건 검증 — 성공

§12-6에서 설계만 하고 "미검증(프록시)"로 남겨뒀던 onset→플래그→Watchdog→텔레그램 경로가 **이번에 최초로 실손상 상태에서 검증**됐다. 결과: 설계대로 정확히 작동(플래그 기록 1초 이내 감지, 텔레그램 2초 발송). **상태 갱신: 미검증 → 실조건검증.** 4차의 "42시간 블라인드"는 재발하지 않았다 — 사용자는 텔레그램으로 즉시 인지했다(실제 설정창 클릭 재현은 66분 뒤였지만, 그건 사용자 대응 타이밍이지 통보 지연이 아니다).

### 13-4. Round 1 판정 — 부결

§12-7 사전등록 기준 적용:

- Run 1(5.48일, §12-9)은 위험창을 넘겼으나 재부팅으로 7일 표본 미완성 → **미확정으로 유보**했던 사안.
- 이번 독립 재기동(07-20)이 **4.19일 만에 재발** → §12-7의 "또 ~5일에 죽음" 갈래 그대로 실현.
- 판정: **arm 3(GPU폴링 차단)·4(psutil 10초)·5(QImage 버퍼 고정) 모두 무죄. Python 3.14.2→3.14.3 상승도 무죄**(그 버전으로 재발). **하드웨어(RAM) 무죄** — 근거는 "PC가 같다"가 아니라 **매 발생마다 같은 머신의 Detection·Watchdog는 완벽 정상인데 UI만 몇 시간씩 선택 오염**됐다는 사실이다(비트플립이 3프로세스 중 하나만 골라 오염시킬 수 없다). 운영 PC(전주)만 2~5차 4회 재발했다(1차는 §1에 `다른 PC`로만 적혀 머신 동일 여부는 문서상 미확정 — 하드웨어 논거는 여기에 의존하지 않는다).
- 남는 용의선: **PySide6 본체** 또는 **Python 3.14 계열 자체**. §12-8 계획대로 **Round 2: Python 3.13 다운그레이드**로 진입.
- arm 자체는 무해하므로 유지(되돌릴 이유 없음) — Round 2와 병행 가능.

### 13-5. Round 2 사전 점검 — 패키지 3.13 호환성 (실측, PyPI 배포 메타데이터 기준)

다운그레이드 전 필수 확인: 이 프로젝트가 쓰는 7개 외부 패키지가 Python 3.13 wheel/설치를 지원하는지. PyPI JSON API로 최신 배포의 wheel 태그를 직접 확인했다(2026-07-24 실측).

| 패키지 | 현재 버전(dev PC) | 확인 결과 |
|---|---|---|
| PySide6 | 6.10.2 (PyPI 최신 6.11.1) | `cp310-abi3` 안정 ABI wheel → 3.13 포함 3.10+ 전체 지원 |
| opencv-python | 4.13.0.90 | `cp37-abi3` 안정 ABI wheel → 3.13 포함 3.7+ 전체 지원 |
| numpy | 2.4.2 (PyPI 최신 2.5.1) | `numpy-2.5.1-cp313-cp313-win_amd64.whl` 존재 확인 |
| psutil | 7.2.2 | `cp37-abi3` 안정 ABI wheel(win_amd64) 존재 → 3.13 지원. 별도 `cp313-cp313t` free-threaded 빌드도 존재(미사용) |
| sounddevice | 0.5.5 | `py3-none-any` 범용 wheel(cffi 런타임 바인딩) → 버전 무관 |
| pycaw | 20251023 | `py3-none-any` 순수 파이썬 wheel → 버전 무관 |
| GPUtil | 1.4.0 | wheel 없음, sdist만(순수 파이썬 `.py`, 컴파일 요소 없음) → 버전 무관 |

**결론: 7개 전부 Python 3.13 설치 경로 확인됨 — 다운그레이드를 막는 패키지 호환성 문제 없음.**

⚠ **이 표의 성격**: 위 버전·근거는 **PyPI 최신 배포 기준의 이론 확인**이다(numpy 2.5.1·sounddevice 0.5.5·pycaw 20251023 등). 실제 배포는 `requirements.txt`의 **고정본**(numpy 2.4.2·sounddevice 0.5.1·pycaw 20240210·opencv 4.13.0.92)을 쓰며, **그 고정본이 3.13에 실제로 설치·기동되는지는 §13-5-b 스모크가 실증**한다(표는 방향 확인, 스모크가 증거). abi3·py3-none 계열이라 고정본에도 근거가 그대로 전이된다.
⚠ **또 하나의 한계**: 설치 가능성만 보증하며 **런타임 동작 동일성은 미확인**이었다 → 13-5-b에서 실제 기동으로 보강.

### 13-5-b. dev PC 기동 스모크 (실측, 2026-07-24)

dev PC(이 PC)는 캡처보드·장기가동 환경이 아니므로 **"힙손상이 해소되는가"는 원천적으로 검증 불가** — 이 스모크가 증명하는 건 **"3.13 전환 자체가 즉시 뭔가를 깨뜨리지 않는가"** 하나뿐이다(범위를 좁혀서 실행).

- `winget install Python.Python.3.13` → 3.13.14 설치, `.venv313` 신규 생성, `requirements.txt` 고정 버전 그대로 설치 성공(7개 전부 wheel 설치, 빌드 에러 0).
- `main.py` 기동 → 로그 실측:
  - `SYSTEM - EXPERIMENT: ... python=3.13.14` — 버전 배너 정상 기록(운영 배포 후 실행 로그로 버전 확인 가능한 경로 그대로 작동)
  - Watchdog spawn → Detection spawn 정상 (Windows `freeze_support` 멀티프로세싱 경로 3.13에서도 무사)
  - SharedMemory 연결 성공, 워커 스레드 전체 시작, `DetectionReady` 발행, `ApplyConfig(reason=restore)` 적용 — 전부 정상
  - 오디오 패스스루 스트림 시작 정상, 영상 포트 0(이 PC 웹캠) 연결 성공
  - 임포트 에러·API 불일치·크래시 **0건**
- 정상 동작 확인 후 프로세스 트리 종료(taskkill), 이 PC엔 장기가동 목적이 없으므로 스모크 종료.
- ⚠ **미실행(정직 표기)**: 버그 발현 지점인 **설정창 열기(`SettingsDialog.__init__` → `ConfigManager()`)는 클릭이 필요해 이번 스모크에서 실행하지 않았다.** MainWindow는 정상 구성됐고(같은 PySide6+순수파이썬 패턴) 3.13에서 SettingsDialog만 구성 실패할 위험은 낮으나 미검증 — 운영 배포 후 설정창 1회 열어 확인 권장.

**결론: 3.13 전환 자체로 인한 즉각적 파손 없음.** 다운그레이드가 실제로 힙손상을 막는지는 여전히 **운영 PC 배포 후 다음 위험창(~4~5일)에서만** 판정 가능 — 이 스모크는 그 배포를 가로막을 이유가 없다는 것만 확인한 것.

### 13-6. 남은 권장 (미실행)

- **Round 2 실 배포**: `.venv313` 방식 그대로 운영 PC에 Python 3.13 설치 → venv 재생성 → `requirements.txt` 설치 → 실행 경로(`실행.bat`) 전환 → 재기동. 이건 되돌리고 싶어질 수 있는 변경이자 며칠짜리 판정 시계가 다시 도는 조치이므로 **배포 시점은 사용자 승인 필요**.
- **병행 가능(비용 0, 5회 동안 미실행)**: 운영 PC `mdsched`(RAM 진단), 백신 실시간스캔 설정 확인(§7 체크리스트, 아직 한 번도 실행 안 됨) — Round 2와 무관하게 지금 해도 됨.
- Round 2도 재발하면: 남는 후보는 PySide6 자체(버전 다운그레이드) 또는 Windows Application Verifier/PageHeap 에스컬레이션(§10-4·§11-4에서 이미 다음 후보로 지목됨).

### 13-7. Round 2 배포 준비 — dev PC 실조건검증 완료 (2026-07-25)

§13-6의 "Round 2 실 배포" 절차를 **원클릭화**했다. 운영 PC에서 반복해야 할 3단계(Python 3.13 설치 → venv 생성 → 패키지 설치)를 한 스크립트로 묶고, 런처는 venv 유무로 자동 분기하게 해 **다른 총국은 무변경**으로 남긴다.

- **`python313_전환.ps1`/`.bat`(신규)**: `py -3.13` 없으면 winget으로 설치 → `.venv313` 생성 → `requirements.txt` 고정 버전 그대로 설치.
- **`실행.bat`(수정)**: `.venv313\Scripts\python.exe` 존재 시 그걸 `PYEXE`로 사용, 없으면 기존과 동일(시스템 `python`/`py`) — 즉 이 변경만으로는 다른 어떤 PC의 동작도 안 바뀐다.
- **`.gitignore`**: `.venv313/` 추가 (커밋 안 됨, PC별 로컬 산출물).

**dev PC 실증(실조건검증, 프록시 아님)**:
- `python313_전환.ps1` 실제 실행 → Python 3.13.14 설치 + `.venv313` 생성 + 7개 패키지 전부 설치 성공(빌드 에러 0, §13-5 표 예측과 일치).
- `.venv313\Scripts\python.exe main.py` 직접 실행 → Watchdog spawn 정상, 영상 캡처 워커 정상 루프(카메라 없는 dev PC라 DSHOW 재시도는 예상된 동작).
- **`실행.bat` 자체를 통한 기동도 별도로 확인** — `logs/20260725_ui.txt`에 `SYSTEM - EXPERIMENT: ... python=3.13.14` 기록됨(§13-5-b가 못 했던 "실행.bat 경로 자체"까지 검증 범위 확장). 이후 taskkill로 정리, dev PC엔 장기가동 목적 없으므로 종료.

⚠ **여전히 미실행(정직 표기, 당시)**: 이건 dev PC 준비·검증이고, **운영 PC(전주) 실배포는 아직 안 함** — §13-6 그대로 사용자 승인 대기 상태. 운영 배포 시 `python313_전환.bat` 더블클릭 1회 + 재기동이면 끝(추가 코드 변경 불필요). 배포 후 판정 시계(~4~5일)가 다시 도는 것도 §13-6과 동일.

### 13-8. Round 2 운영 PC 실배포 완료 — 실조건검증 (2026-07-25)

**상태 갱신: 미배포 → 배포 완료, 실조건검증.** 운영 PC(Windows 11)에서 `python313_전환.bat` 실행 → 이 과정에서 §13-7의 한글깨짐 버그가 실제로 재현됐고(2라운드, 아래 별도 항목), `%~dpn0.ps1` 방식으로 재수정한 버전을 재배포해 최종 성공.

- **기동 알림(§부가 항목) 실배포 확인**: 화면 SYSTEM LOG에 `기동 완료 (Python 3.13.14)` 표시 확인(사용자 스크린샷 없이 텍스트 보고, 앞서 dev PC에서 동일 항목 스크린샷 검증 완료된 것과 같은 코드 경로).
- **텔레그램 기동 알림 최초 무응답 → 해결**: 처음엔 텔레그램이 안 옴. 설정을 다시 저장→불러오기 후 재기동 → **텔레그램 정상 수신 확인**(현재까지 계속 정상).
  ⚠ **당시 적어 둔 원인("옛 백업에 신버전 새 키가 없었을 가능성")은 2026-07-26 코드 검토로 반증됐다** — 아래 "설정파일 이월" 항목 참조. 같은 가설을 다시 물지 말 것.
- **`python313_전환.bat` 최종 수정판(`%~dpn0.ps1`, 순수 ASCII)도 이 배포로 실조건검증 완료** — dev PC뿐 아니라 실제로 실패했던 그 PC에서 재현→해결까지 확인(위키 기록: `~/.claude/wiki/KBS_Monitoring-bat-korean-encoding.md`).
- **Round 2 판정 시계 공식 시작**: 2026-07-25 기준. 다음 위험창(~4~5일, ~07-29~30) 무사 통과 시 arm 유력, 그 전에 재발하면 Python 3.14 계열도 무죄로 확정되고 남는 용의선은 PySide6 본체뿐(§13-6 마지막 항목).
- ⚠ **재발 시 재부팅 전에 로그부터 회수**(§7 체크리스트와 동일): `logs/*_ui.txt`, `fault.log`, `stderr_debug.txt`, `data/ui_degraded.flag`.

**함정 — `python313_전환.bat` 한글 깨짐 (2026-07-25, 사용자 PC 실제 재현)**: 첫 배포본은 `chcp 65001` 없이 UTF-8로 저장돼, 사용자 PC(기본 코드페이지 CP949 추정)에서 `powershell ... "%~dp0python313_전환.ps1"` 줄의 한글 파일명이 깨져 "내부 또는 외부 명령이 아닙니다"로 실패(cmd 창이 순식간에 닫혀 원인 파악도 안 됨). dev PC에서는 재현 안 됨(코드페이지 차이). 1차 수정 시도(`chcp 65001` 추가 + BOM 첨부)는 dev PC에서 **더 나쁜 결과**(BOM이 `@echo off` 자체를 깨서 전체 라인이 에코됨) — cmd.exe는 PowerShell과 반대로 **.bat의 UTF-8 BOM을 지원하지 않는다.** 최종 해법: `chcp 65001` 유지 + **BOM 없이** UTF-8 저장 + CRLF — `실행.bat`이 이미 쓰던 조합 그대로. 최종본은 dev PC에서 실제로 재현(BOM 버전)→해결(BOM 제거)까지 확인. **교훈(1차, 틀림으로 판명)**: 이 프로젝트에서 한글 포함 `.bat`은 반드시 `chcp 65001` + **BOM 없는** UTF-8 + CRLF 조합이어야 한다(`.ps1`은 반대로 BOM이 있어야 함 — install.ps1·python313_전환.ps1 전례).

**2차 재발 — 운영 PC(Windows 11, 관리자 권한 실행)에서 동일 증상 (2026-07-25)**: 위 "최종 해법"(`chcp 65001` + BOM 없음 + CRLF)을 배포했는데도 사용자의 실제 Windows 11 PC에서 **완전히 동일한 mojibake로 재발**(관리자 권한 실행도 동일). dev PC(Windows 10)에서는 여전히 재현 안 됨 — Windows 버전 간 `chcp 65001`이 배치파일 자체 파싱에 적용되는 타이밍이 다른 것으로 추정(문서화된 근본원인은 못 찾음, 여러 스레드에서 "일부 빌드는 chcp 실행 전에 이후 줄을 미리 읽어들인다"는 보고가 있음 — 미확정). **`실행.bat`이 이미 남긴 경고 주석("ASCII-only comments: non-ASCII REM lines break batch parsing on some PCs under chcp 65001")을 `python313_전환.bat`엔 처음부터 안 지켰던 게 근본 실수** — `chcp`로 해결하려 하지 말고 애초에 피했어야 했다.
**최종 해법(견고, 코드페이지 무관)**: `.bat` 파일 안의 실행 줄에서 **한글 텍스트 자체를 완전히 제거**. `%~dp0python313_전환.ps1`(파일명을 텍스트로 타이핑) 대신 **`%~dpn0.ps1`**(현재 실행 중인 배치파일 자신의 경로에서 확장자만 바꿔치기 — cmd가 OS 경로 정보에서 프로그램적으로 가져오므로 텍스트 재인코딩 문제 자체가 발생 안 함) 사용. echo 메시지도 영어로 교체해 `.bat` 파일 전체를 순수 ASCII로 만듦(`file` 명령으로 확인: "ASCII text"). dev PC 실조건검증: 전체 절차(3.13 확인→venv 재생성→패키지 설치→"전환 완료!") 재현 없이 정상 통과.
**교훈(최종)**: `chcp 65001`을 신뢰하지 말 것 — Windows 빌드마다 배치파일 자체 파싱에 적용되는 타이밍이 다를 수 있다. **가장 견고한 해법은 코드페이지에 의존하지 않는 것**: `.bat`의 실행 줄(REM 아닌 실제 명령)엔 비-ASCII 텍스트를 아예 안 넣는다. 같은 이름의 `.bat`/`.ps1` 쌍이면 `%~dpn0.<ext>`로 항상 상호 참조 가능.

### 13-9. 설정파일 이월 검토 — 기동 알림 무응답 원인 재판정 (2026-07-26)

§13-8이 "옛 백업에 신버전 새 키가 없었을 가능성"으로 적어 둔 원인을 코드로 검증한 결과 **반증**. 사용자의
"설정파일도 주기적으로 업데이트해야 하나 / UI 손상도 이것과 연관 아닌가"라는 물음에서 출발한 검토다.

**ⓐ 옛 설정파일은 기동 알림을 막을 수 없다.** `_send_system_telegram`의 관문 중 **키가 없을 때 막는 것은
`telegram.enabled`(기본 False) 하나뿐**이고, `notify_system`은 없으면 **True로 통과**한다. 그런데
`enabled`·`bot_token`·`chat_id`·`notify_system`은 전부 **최초 커밋 `d249be3`(2026-04-18)부터 존재** —
6/27 백업에 없을 수가 없다. 사용자도 "토큰·chat ID는 파일 생성일과 무관하게 항상 활성 상태였다"고 확인.
`system_chat_id`가 stale이었다는 가설도 배제된다 — 설정창에 입력칸이 있어 **재저장해도 값이 보존**되므로,
"재저장으로 고쳐졌다"는 사실과 모순된다.

**ⓑ 남는 원인**: 신규 설치 폴더에 `config/kbs_config.json`이 **놓이기 전에** Watchdog이 기동한 것.
이 파일은 gitignore라 새 clone에 없고, Watchdog은 기동 직후 1회만 읽는다 → 프로그램을 띄운 뒤 설정을
불러온 그 세션에서는 알림이 원리적으로 안 나간다(다음 재기동부터 정상). 실제로 현재는 정상 수신 중.

**ⓒ `_merge_defaults`는 2단계까지만 병합한다**(`config_manager.py:211`). 최상위·2단계 키는 자동 보완되지만
**3단계(`signoff.groupN.*`)와 리스트 안 딕트(`rois.video[]`)는 보완되지 않는다.** 현재 백업엔 해당 없음
(정파 하위 키는 마지막 추가가 `exit_prep_start_time` 2026-06-07로 6/27 백업보다 앞서고, ROI는
`ROI.from_dict`가 모든 필드를 `.get(기본값)`으로 읽어 방어). **향후 정파·ROI
스키마에 키를 추가하는 순간 조용히 터질 자리**다. 또한 `config_version`은 로그 출력에만 쓰이고 마이그레이션
로직이 없다.
⚠ **"주기적 재저장" 의식은 실효가 거의 없다** — 재저장은 현재 값을 다시 쓸 뿐 **바뀐 기본값을 채택하지 않고**,
없는 키 보완은 불러오기마다 이미 자동으로 일어난다.

**ⓓ UI 손상과는 무관**하다고 판단. ⑴ 같은 설정파일을 읽는 Detection·Watchdog는 5회 모두 정상이고 UI만
오염됐다(설정이 원인이면 셋 다 영향받아야 한다). ⑵ Round 1 arm은 **설정값으로 켜고 끄는** 실험이었는데,
운영 PC가 **6/27 백업을 복원한 상태에서** 기동 로그에 `EXPERIMENT: sysmon_gpu=False …`를 찍었고 상단바
`GPU OFF`도 실측됐다(§12-6-b) — 낡은 설정이 뭔가를 조용히 되돌리고 있었다면 거기서 드러났을 것. ⑶ 손상은
객체 생성 자체가 실패하는 힙 수준 사고이지, 숫자·불리언 설정값이 만들 수 있는 고장이 아니다.
남는 연관은 **설정 *내용*(ROI 8V+6A+1EA·텔레그램·녹화)이 운영 PC와 dev PC의 부하 차이를 만든다**는 것뿐인데,
이건 "신선도"가 아니라 "실행 경로"의 문제다.

**ⓔ 취소된 계획(기록)**: `ConfigManager.CONFIG_DIR="config"`·`AppLogger.LOG_DIR="logs"`가 상대경로라
cwd에 따라 설정·로그가 두 벌로 갈릴 수 있다고 보고 절대경로 전환을 계획했으나, **`main.py:55`가
`os.chdir(_ROOT)`로 이미 고정**하고 있음을 확인해 철회(v2.2.10, 2026-05-26에 같은 이유로 도입).
Detection·Watchdog는 spawn 시 부모 cwd를 상속하므로 세 프로세스 모두 안전. **상대경로 자체는 무해 —
다시 "결함"으로 판단하지 말 것.**

**조치**: 유일한 실제 결함은 **차단 사유가 로그에 안 남는 것**이었다(이번 조사가 어려웠던 직접 원인).
`watchdog_process._send_system_telegram`은 logger로, `main._send_system_telegram_main`은 stderr로
미발송 사유(설정 미배치 / `enabled=false` / `notify_system=false` / 토큰 공백)를 남기도록 수정.
실조건검증: 실제 기동 시 `[SYSTEM] 텔레그램 미발송(...bot_token+chat_id 없음...)`이 watchdog 로그에 기록됨(dev PC).

**부수 발견 — 기동 알림의 앱 버전이 틀렸다**: `main.py`가 Watchdog에 `"2.8"`을 **하드코딩**해 넘기고 있어,
원격 텔레그램이 `v2.8 기동`으로 찍혔다(실제 2.8.6). Round 2가 "어느 빌드로 도는지" 원격 확인하려고 만든
기능인데 앱 버전만 무의미했던 셈(파이썬 버전은 정상이라 Round 2 확인 자체는 성립했다).
→ `ui.main_window.VERSION` 단일 출처에서 가져오도록 수정, 기동 로그에서 `v2.8.6` 확인.

**부가 — 기동 알림 + onset 화면 로그 (2026-07-25)**: Round 2가 실제 3.13으로 도는지 원격 확인할 방법이 없다는 지적에서 "재기동 통보"로 일반화(Watchdog 기동 시 `[SYSTEM]` 텔레그램 1회 + 화면 SYSTEM LOG). 이어서 "UI 손상 시에도 화면에 보이면 좋겠다"는 제안 → `main.py`의 onset 캡처(§12-6 이후 확립된 플래그→텔레그램 경로)에 `window._log_widget.add_log(...)` best-effort 시도를 추가(§CLAUDE.md "UI 손상 통보" 참조). ⚠ **이건 텔레그램 플래그 경로와 근본적으로 다르다** — 플래그는 `open()+write()`만 써서 손상 상태에서도 작동이 실증됐지만(42시간 사례), 화면 로그 추가는 새 객체 생성이라 **손상 상태에서 이 자체가 실패할 가능성이 있다.** try/except로 무해하게 감쌌지만, 실제 성공 여부는 텔레그램 플래그 경로와 마찬가지로 **재현 불가 — 다음 실제 발생 때만 판정 가능**(미검증 상태로 남김).

### 13-10. Round 2 판정 — 통과 확정 (2026-08-07, 운영 PC 로그 전수 검토)

> **판정 트리거**: 사용자가 "07-25부터 지금(08-07)까지 별문제 없이 돌아간다"고 보고 → §13-8이 사전등록한 위험창(~07-29~30)을 훨씬 넘긴 상태라, 로그를 직접 회수해 재발 여부를 실측 확인.

**회수 대상**: `logs/2026072[5-9]_{ui,detection,watchdog}.txt`, `2026080[1-7]_{ui,detection,watchdog}.txt`, `fault*.log`, `stderr_debug.txt` (`H:\내 드라이브\logs`로 사용자가 통째 복사).

**확인 결과**:

| 항목 | 결과 |
|---|---|
| UI/Watchdog 재시작 | 07-25 11:56~12:01 설정 확정 과정 중 3회뿐, 이후 08-07까지 **0회**(PID 유지, 같은 프로세스 계속 실행) |
| Detection 재spawn | 0회 |
| `ui_degraded.flag` / 손상 통보 | 0건 |
| Heartbeat 무응답(10초) | 0건 |
| ERROR/CRITICAL 로그 | 0건 (14일치 전체) |
| `fault*.log` | 전부 0바이트 |
| HEALTH 스냅샷 | 하루 144개(10분 주기) 누락 없이 정상 |

07-25 12:01:04(마지막 설정 재시작) 기준 **13일 연속가동** — 과거 5회 온셋(3차 5.1일 / 4차 4.15일 / Round1 5.48일)을 전부, 그것도 큰 폭으로 넘겼다.

**판정**: Round 2(Python 3.13 다운그레이드) **통과 확정**. §13-4에서 좁혀둔 "PySide6 본체 또는 Python 3.14 계열 자체" 중 **Python 3.14 계열(및 그 위에서 빌드된 PySide6 6.10 wheel 조합)이 범인**이었던 것으로 결론짓는다 — PySide6 자체 다운그레이드(Round 3)는 불필요.

⚠ **범위 한정**: 이 13일간 **실제 알람이 0건**(전부 정파 시간대 억제된 still/black)이라, 힙손상 부재 판정은 "평상 대기 상태"에 대해서만 유효하다. 알람 발생·녹화 트리거 경로(v2.8.8 A/V 어긋남 수정 포함)는 이 기간으로 검증되지 않는다.

### 13-11. 부수 발견 — UI 프로세스 완만한 메모리 증가 (별개 버그, 2026-08-07 수정)

Round 2 판정을 위해 HEALTH 로그를 전수 비교하던 중, Detection(212~228MB 노이즈)·Watchdog(항상 정확히 73MB)은 평평한데 **UI만** 13일간 RSS가 198→373MB(+88%), handle이 988→1092로 증가한 것을 발견했다. 힙손상과는 무관한 **일반적인 Qt 객체 미해제 누수**로 판명:

- 증가 양상이 시간 비례가 아니라 **계단식**(평일 낮 시간대에 한 번 점프 후 그대로 유지) — 07-28 09~12시, 08-05 10~15시 구간에 집중 점프.
- 코드 확인: `ui/main_window.py:_open_settings()`가 열 때마다 새 `SettingsDialog`를 생성해 `self._settings_dlg`에 덮어쓰지만, 이전 인스턴스를 한 번도 해제하지 않음 — `Qt.WA_DeleteOnClose` 미설정, `closeEvent`(`settings_dialog.py:2444`)에도 `deleteLater()` 없음. Qt에서 `parent=self`(MainWindow)가 있는 위젯은 `close()`만으로는 C++ 객체가 죽지 않고 **숨겨진 채 부모에 계속 매달려 산다** — 안의 7탭 위젯·ROI 테이블·오버레이까지 통째로. 관측된 계단식 패턴(설정창을 연 시점에만 증가)과 정확히 일치.
- **수정**: 새 인스턴스 생성 직전 이전 인스턴스에 `deleteLater()` 호출 + 열림/닫힘 로그(`[settings] 설정창 열림/닫힘`) 추가 — `ui/main_window.py` `_open_settings()`.
- **검증(프록시)**: 독립 하네스로 열기/닫기 6회 반복 — 자식 위젯 수가 무한 증가하지 않고 800(기준)→1599(과도기, deleteLater 처리 전이라 신구 공존)→종료 후 800(기준선 복귀)로 수렴 확인, 로그 열림/닫힘 쌍 정상 기록.
- ⚠ **미검증(실조건)**: dev PC 하네스는 실제 MainWindow 전체 없이 `_open_settings()` 패턴만 재현한 것 — 운영 PC에서 수개월 단위로 HEALTH RSS가 실제로 평평해지는지는 다음 로그 회수가 실조건검증.

## 14. 6차 발생 (2026-08-11, v2.8.9) — 원인: 배포가 Round 2 픽스를 조용히 무효화

> **조사 방식 전환**: 이번엔 로그파일을 개발 PC로 복사해 추측하지 않고, **운영 PC(이 PC 자체) 위에서 직접** 실행 중 프로세스·파일시스템·`git reflog`·런처 체인을 조사했다(2026-08-12, 사용자 지시).

### 14-1. 증거 — 실제로는 3.13이 아니라 3.14로 돌고 있었다

| 확인 항목 | 결과 |
|---|---|
| 사고 당시 UI 프로세스 커맨드라인 | `Python314\python.exe main.py` |
| 런처 체인 | `cmd.exe /c 실행.bat` → `py` → **3.14.3** |
| `.venv313\Scripts\python.exe` 존재 | **없음** (`Test-Path` = False) |
| `.gitignore` | 15번째 줄에 `.venv313/` 등재 — clone에 안 따라옴 |
| `git reflog` | `2026-08-07 13:21:36 clone: from https://github.com/mw3love/KBS_Monitoring_v2_260418` **1건뿐**. 프로젝트 폴더 자체의 생성시각도 정확히 그 순간 — 기존 폴더에서 `git pull`한 게 아니라 **폴더째로 새로 클론된 배포**였음을 뜻한다. |
| 08-07 기동 배너 | `logs/20260807_ui.txt:2` — `SYSTEM - EXPERIMENT: ... python=3.14.3` |
| onset | `2026-08-11 09:33:03` (`data/ui_degraded.flag`, watchdog 로그 텔레그램 발송 기록) |

**결론**: 2026-08-07 13:22 재배포 시점부터 이미 3.14로 돌고 있었다. §13-10 판정("07-25~08-07 13일 무손상")은 그 자체로는 유효한 3.13 표본이지만, **그 이후로도 3.13이 계속 돈다는 전제가 08-07 배포 순간 조용히 깨졌다** — 아무도 몰랐던 5일짜리 사각지대(08-07~08-12)였다.

### 14-2. 근본 원인 — `.venv313`도 `config/kbs_config.json`과 같은 "신규 clone 함정"

`실행.bat`의 인터프리터 선택 로직:

```bat
set "PYEXE=python"
where py >nul 2>nul && set "PYEXE=py"
if exist "%~dp0.venv313\Scripts\python.exe" set "PYEXE=%~dp0.venv313\Scripts\python.exe"
```

`.venv313`이 있으면 그걸 쓰고, **없으면 경고 없이** `py`(시스템 기본, 3.14)로 폴백한다. `.venv313/`은 `.gitignore` 대상이라 **신규 clone마다 사라진다** — 이미 CLAUDE.md "신규 빌드 배포 시 함정"에 문서화돼 있던 `config/kbs_config.json` 유실 패턴과 정확히 같은 종류의 함정인데, 목록에 없어서 이번에 처음 걸렸다.

### 14-3. 새로 확보된 onset traceback (1~5차엔 없던 증거)

`PYTHONMALLOC=debug`로 잡은 `logs/stderr_debug.txt`의 실제 손상 순간 스택:

```
File "ui/main_window.py", line 412, in _on_signoff_state_changed
    self._alarm.play_signoff_sound(sound)
File "ui/alarm.py", line 187, in play_signoff_sound
    th = threading.Thread(...)
File ".../threading.py", line 940, in __init__
    self._started = Event()
File ".../threading.py", line 603, in __init__
    self._cond = Condition(Lock())
TypeError: __init__() should return None, not 'NoneType'
```

트리거는 **정파 전환 알림음 재생**(`_on_signoff_state_changed` → `play_signoff_sound`)이 새 `threading.Thread`를 생성하는 지점. 과거 5회는 onset 순간의 정확한 코드 경로를 못 잡았는데(§10~11 계측 실패), 이번엔 `PYTHONMALLOC=debug`가 켜진 채로 재현돼 처음으로 확보했다.
⚠ 다만 `stderr_debug.txt` 전체(4696줄, 3.84일치)에 **pymalloc 디버그 할당자의 가드바이트 위반 메시지는 0건** — 이 손상은 malloc guard byte로 잡히는 단순 버퍼 오버플로/wild write는 아니다(§11 가설 중 하나 배제). CPython 3.14 내부 상태 자체의 문제이거나, guard byte로 안 잡히는 종류의 corruption으로 범위가 좁혀진다.

### 14-4. Round 2 판정 재해석 — 무효화 아니라 재확증

| 구간 | 인터프리터 | 결과 |
|---|---|---|
| 07-25 ~ 08-07 (13일) | 3.13.14 | 손상 0회 |
| 08-07 13:22 ~ 08-11 09:33 (3.84일) | 3.14.3 (의도치 않음) | **손상 발생** |

의도치 않은 크로스오버 실험이 됐지만 결과는 §13-10의 "Python 3.14 계열이 범인"을 **약화시키지 않고 오히려 재확증**한다. 다만 정직하게 표기: 3.84일은 과거 1~5차 onset 구간(4.15~5.1일, Round 1 5.48일)보다 짧다 — 같은 자릿수이지만 완전히 같은 패턴은 아니다.

### 14-5. 조치

- **`.venv313` 재생성**: `py -3.13 -m venv .venv313` + `requirements.txt` 7개 패키지 설치 성공(빌드 에러 0).
- **앱 재기동**(2026-08-12 09:49): `logs/20260812_ui.txt:92`에 `python=3.13.14` 확인, `data/ui_degraded.flag` 소멸(손상 상태 해소).
- **`실행.bat` 수정**: `.venv313` 부재 시 더 이상 조용히 폴백하지 않는다 — 콘솔과 `logs/stderr_debug.txt` 양쪽에 `[launcher] NOTICE: .venv313 not found - falling back to default interpreter: ...` 기록. `logs\` 생성 순서를 인터프리터 선택보다 앞으로 옮겨서 이 알림도 로그에 남게 함.
- **CLAUDE.md**: "신규 빌드 배포 시 함정"에 `.venv313` 항목 추가(§14 참조).

### 14-6. 판정 시계 재시작

새 위험창은 **2026-08-12 09:49부터** 다시 카운트(3.13.14 기준). 과거 onset 패턴(4.15~5.1일)대로면 다음 판정 시점은 **~08-16~08-17**.
⚠ **이번엔 배포 방식 자체를 바꾸지 않는 한 표본이 또 오염될 수 있다** — 다음 재배포도 "폴더 삭제 후 재clone" 방식이면 `.venv313`이 또 사라진다. `실행.bat`의 NOTICE 추가는 안전망이지 예방책이 아니므로, 재배포 직후엔 반드시 그날 UI 로그의 `EXPERIMENT: ... python=` 배너를 눈으로 확인하는 걸 배포 체크리스트에 못박을 것.

Confidence: high (프로세스 커맨드라인·git reflog·기동 로그 3중 교차확인)
Not-tested: `.venv313` 재생성이 이번에도 5일 안에 재발을 막는지는 다음 위험창(~08-16~17)까지 미판정.
