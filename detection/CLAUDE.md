# Detection 프로세스 — 개발 규칙

## Detection 프로세스 절대 규칙
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

## 예외 처리 원칙
- 모든 DIAG 섹션은 반드시 독립된 try-except로 격리 (하나 실패해도 나머지 계속)
- `traceback.format_exc()` 호출 자체도 inner-try로 보호 (호출 실패 시 에러 정보 소실 방지)
- `threading.Thread.start()` 실패 시 OSError를 반드시 로그에 기록

## 히스테리시스 원칙 (v1에서 이식)
- 경보 전/후 대칭 적용
- SignoffManager: IDLE 진입 시 `_reset_enter_timers()`, SIGNOFF 진입 시 `_reset_exit_timers()`
- still_reset_frames: 연속 정상 프레임 카운터 (글리치 방지)

## 상태 전환 타이머 초기화 원칙
- SignoffManager 상태 전환 시 반드시 해당 방향의 타이머 초기화 함수 호출
  - IDLE 진입 시: `_reset_enter_timers()` (미호출 시 다음 날 PREPARATION 즉시 SIGNOFF 전환 버그)
  - SIGNOFF 진입 시: `_reset_exit_timers()` (미호출 시 이전 주기 stale 타이머 잔류)

## 정파 억제 규칙
- 억제는 그룹별로만 적용: `is_signoff_label(label, group_id)` 사용
- 임베디드 오디오는 그룹 귀속이 없으므로 정파 억제 적용 불가 (`is_any_signoff()` 금지)
- PREPARATION 상태: 스틸만 억제, 블랙은 계속 알림

## 설정 동기화 원칙
- 파라미터 추가·변경 시 반드시 3파일 동시 업데이트:
  1. `config/default_config.json` — 새 설치 기본값
  2. `utils/config_manager.py` `DEFAULT_CONFIG` — 런타임 fallback
  3. `config/kbs_config.json` — 현재 운영 설정 (값 확인)
- 설정 갱신 후 즉시 진단 로그 기록 (silent 실패 방지)

## 예약 재시작 중복 방지 원칙
- 중복 실행 방지는 시각(HH:MM)이 아닌 **날짜+시각(YYYY-MM-DD HH:MM)** 조합으로 관리
  - 시각만으로 방지 시 매일 같은 시각에 재시작 불가

## 오디오 서브시스템 (Detection 프로세스 단독)
- `sounddevice` 스트림 오픈/읽기
- `pycaw` 시스템 볼륨/Mute 제어
- UI는 `cmd_queue`로 `SetVolume(value)`, `SetMute(bool)` 명령만 전송
- 근거: 오디오 스트림과 시스템 볼륨을 서로 다른 프로세스에서 제어 시 충돌 위험

## faulthandler 필수 적용
- `main.py` 시작 시 반드시 `faulthandler.enable(file=open("logs/fault.log", "a"))` 적용
- Python try-except는 C++ 레벨 segfault 감지 불가 → faulthandler만 감지 가능

## v1 코드 이식 규칙
- v1 코드 이식 시, `QThread` / `QTimer` / `Signal` / `QObject` 잔재 여부를 체크 후 보고할 것
- Detection 프로세스에 이식하는 코드는 PySide6 임포트가 없는지 반드시 확인
- 이식 후 변경사항 목록을 사용자에게 보고할 것

## v1에서 그대로 이식 가능한 파일
| v1 | v2 | 주요 변경 |
|----|----|----|
| `core/detector.py` | `detection/detector.py` | Signal 제거, dict 반환 |
| `core/detection_state.py` | `detection/detection_state.py` | Signal 제거 |
| `core/signoff_manager.py` | `detection/signoff_manager.py` | QTimer → time.sleep(1) (1초 주기 상태 점검) |
| `core/auto_recorder.py` | `detection/auto_recorder.py` | 거의 없음 |
| `core/telegram_notifier.py` | `detection/telegram_worker.py` | QObject 제거 |
| `core/roi_manager.py` | `core/roi_manager.py` | 없음 |
| `utils/` | `utils/` | 거의 없음 |

## 새로 작성하는 파일 (v2 신규)
- `main.py`, `processes/*`, `ipc/*`, `ui/ui_bridge.py`, `ui/main_window.py`
