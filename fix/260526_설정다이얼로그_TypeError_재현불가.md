# 설정 다이얼로그 TypeError (재현불가) — 260526

> **상태**: **2건 발생** (260526, 260620). 코드 버그 아님 확정에 가까움 — 런타임/네이티브 손상.
> 260620 발생분 + 계측 보강은 **§10** 참조.
> **버전**: 1차 v2.2.7 / 2차 v2.7.1. 동일 코드 베이스, 다른 PC.
> **결론**: 코드 버그 아닌 런타임 손상(C 확장 / GC / 하드웨어) 의심. 재발 시 본 문서 + 새 로그 함께 검토.

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
