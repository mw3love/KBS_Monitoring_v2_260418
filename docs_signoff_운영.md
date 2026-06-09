# 정파 시스템 — 운영 특성

> KBS 모니터링 운영 도메인 지식. 코드 규칙(`CLAUDE.md`, `detection/CLAUDE.md`)이 아닌 **현장에서 관찰된 정파 동작 패턴**을 정리한다. 코드 동작과 운영 의도가 어긋날 때 이 문서를 근거로 판단한다.

---

## 1. 정파 시작 시각의 불규칙성

- **실측 범위**: 00:40 ~ 03:50 (날짜·편성에 따라 변동)
- 따라서 `signoff.groupN.prep_start_time`(정파준비 시작 시간)을 가장 이른 정파보다 충분히 앞(기본 `00:30`)으로 잡아, 일찍 시작하는 정파도 스틸 감지로 포착해야 한다. (스키마 상세는 §6)

**시사점**: 자동 진입은 **스틸 자동감지 단독**이며(§6), "정파 시작 시각 직전에만 허용" 같은 시간 가드는 도입할 수 없다 — 시각이 불규칙해 합리적 가드 범위 설정이 불가능. (그래서 시간 강제진입 자체를 제거함.)

---

## 2. 정파 중 테스트영상 송출 예외

- 정파 시간대에 **테스트영상(움직이는 영상)** 을 송출하며 점검을 수행하는 경우가 있음.
- 빈도는 매우 낮음 (예외적 케이스).
- 따라서 "정파 = 무조건 스틸"이라는 가정을 코드/로직에 박지 말 것.

**시사점**: SIGNOFF 상태에서 "비스틸이면 즉시 해제" 같은 단순 로직은 이 예외 케이스를 깨뜨릴 수 있음. 현재 코드의 `exit_prep_window`(종료 30분 전)에서만 해제 검사하는 설계는 이 예외에 대한 보호 효과도 있다.

---

## 3. `still_trigger_sec` 120초 결정 근거 (2026-05-19)

### 배경
- v2 초기 기본값: **60초**
- 2026-05-18 운영 중 1TV 정파준비모드에서 V1 영상이 60초간 우연히 스틸로 잡혀 정파 시작 시각(03:00) 한참 전인 **01:02:31에 SIGNOFF로 잘못 진입**한 사례 발생.

### 변경
- group1, group2 모두 **60초 → 120초**.

### 근거
- 정상 콘텐츠 중 60초 연속 스틸이 가능한 패턴이 존재:
  - 자막 카드 (긴 안내 화면)
  - 광고 정지컷 연속
  - 장시간 고정 카메라 클로즈업
- 2분(120초) 이상 거의 안 움직이는 콘텐츠는 사실상 없음 → 99.9% 오진입 차단 예상.
- 0.1% 잔여 오진입의 영향도 운영상 미미하다고 판단:
  - 잘못된 텔레그램 알림이 발송되어도 사용자가 캡쳐 이미지로 즉시 원인 식별 가능
  - 알람 차단 시간 동안 진짜 알람이 차단될 수 있으나 실측상 거의 발생 안 함

### 미도입 대안 — "빠른 해제(진입 후 N분 내 비스틸 시 즉시 해제)"
- 검토 후 도입 보류. 이유:
  - 신규 실패 모드(정상 정파를 노이즈/일시 깜빡임으로 오해제) 추가 위험
  - 120초만으로 99.9% 차단되므로 추가 보완의 한계 이득
  - `CLAUDE.md` 원칙 "필요 이상 추상화 금지"와 부합
- 향후 운영 중 오진입이 한 달에 2~3회 이상 반복되거나, 차단된 알람으로 실제 손실이 누적되면 재검토.

> **2026-06-08 갱신**: 이 "빠른 해제"를 **IDLE이 아닌 PREPARATION으로 복귀**하는 변형으로 §7에서 채택했다. 재무장이라 위 "신규 실패 모드(정상 정파 오해제)"를 회피한다.

---

## 4. SIGNOFF 오진입의 자연 회복 경로

오진입이 발생하더라도 시간이 지나면 자동 해제된다. 단, 즉각적이지 않음.

> **2026-06-08 갱신**: §7 조기복귀 도입으로, 해제준비 시각 **전**이라면 아래의 느린 회복은 더 이상 적용되지 않는다(움직임 시 즉시 PREPARATION 복귀). 아래는 조기복귀 도입 전 동작 기록이자, 해제준비 윈도우 **안**의 해제 동작 설명으로 유효하다.

### 흐름 (5/18 케이스 기준)
```
01:02:31  잘못 SIGNOFF 진입 (auto-detect)
01:02 ~ 04:30  exit_prep_window 밖 → 자동 해제 검사 미실행
                (이 구간 동안 v_label/suppressed_labels 알람 차단됨)
04:30:00  exit_prep_window 진입 (end_time 05:00 - 30분)
          → _tick_exit_preparation 호출 시작, 비스틸 감지 시작
04:50:05  V1이 exit_trigger_sec(5초) 연속 비스틸로 잡힘 → IDLE 해제
04:50:09  텔레그램 해제 알림
```

### 핵심 코드 위치 (함수명 기준 — 라인은 변동됨)
- `detection/signoff_manager.py` `_tick_impl` SIGNOFF 분기: 해제준비 구간 안에서만 `_tick_exit_preparation` 호출
- `_is_in_exit_prep_window`(해제준비 구간 = `exit_prep_start_time`~`end_time` 판정), `_tick_exit_preparation`(비스틸 감지/해제)

### 시사점
- "오진입 후 알람 차단이 최대 (정파 시작 ~ `exit_prep_start_time`) 시간만큼 지속될 수 있다"는 사실은 운영상 알고 있어야 함.
- 이 기간을 단축하려면 `exit_prep_start_time`을 앞당기는 방법이 있으나, 정상 정파에서 종료 직전 영상이 움직이기 시작하면 일찍 해제될 위험과 트레이드오프.

---

## 5. `auto_preparation` OFF = 완전 수동 모드 (2026-05-29, W11)

설정 "자동 정파준비"(`signoff.auto_preparation`)를 끄면 해당 시스템은 **완전 수동 모드**가 된다.

### 동작
- **자동 전환 0건**: 시간대 진입(IDLE→PREP)·시간대 이탈 강등(→IDLE)·스틸 감지 자동진입(`_tick_preparation`)·exit-prep 자동해제(`_tick_exit_preparation`)·스케줄 저장 시 즉시 재평가(`set_group`)가 **모두 억제**된다.
- 상태는 **상단바 정파 버튼 수동 클릭**으로만 바뀐다. 한 번 설정한 상태는 다음 수동 조작까지 유지된다(1초 tick에 의해 되돌려지지 않음).
- 상단바 버튼은 auto OFF여도 **활성 유지**되며, 카운트다운 대신 "대기 · 수동 / 정파준비 · 수동 / 정파중 · 수동"으로 현재 상태를 표기한다.

### 수동 순환 규칙 (시간대 인지)
버튼 클릭은 `SignoffManager.cycle_state()`를 탄다:
- IDLE → PREPARATION (항상)
- PREPARATION → 정파준비 윈도우 안이면 SIGNOFF, **밖이면 IDLE**
- SIGNOFF → IDLE

즉 auto OFF여도 **정파준비 윈도우 밖에서는 수동으로도 SIGNOFF에 진입할 수 없다**(PREPARATION 클릭 시 IDLE로 감). 정파준비 윈도우(`prep_start_time`~`end_time`)가 넓으므로 운영상 제약은 작지만, 윈도우를 벗어난 임의 시점에 SIGNOFF 강제가 필요하면 `prep_start_time`/`end_time`을 조정해야 한다.

### 설계 근거
- auto ON일 때는 가드가 항상 통과하므로 §1~§4의 자동 동작·자연 회복 경로가 **그대로 유지**된다(거동 무변).
- 기존 코드는 IDLE 분기만 `auto_preparation`를 존중하고 PREP/SIGNOFF 분기는 무시하던 **비일관 상태**였음 → W11에서 세 분기 + `set_group` 모두 동일 가드로 정렬.

### 핵심 코드 위치
- `detection/signoff_manager.py` `_tick_impl` PREPARATION/SIGNOFF 분기 `if self._auto_preparation:` 가드
- `detection/signoff_manager.py` `set_group` `if schedule_changed and self._auto_preparation:`
- `detection/signoff_manager.py:255` `cycle_state` (시간대 인지 순환)
- UI: `ui/main_window.py` `_on_signoff_button_clicked`(→`CycleSignoffState`), `ui/top_bar.py` `update_signoff_state`(수동 표기)

---

## 6. 진입=감지 단독 / 해제=시간 기반 — 3 직접시각 스키마 (2026-06-07)

### 배경 — 진입/해제 비대칭
- 정파 **시작** 시각은 불규칙(§1, 00:40~03:50), 정파 **해제** 시각은 거의 고정(4:30 이후, 5:00 못 넘김. 실측 2TV 04:45 / 1TV 04:50).
- 기존 구조는 정파 시간대(start_time~end_time) 진입 시 화면 상태와 무관하게 **강제로 SIGNOFF 전환**했다. 시작 시각이 불규칙해 03:00에 강제 진입해도 실제 정파는 03:50일 수 있어, 그 사이 정상 방송 채널의 블랙/스틸/오디오 알림이 묵살되는 **오진입**이 잦았다.

### 오류 비대칭 (설계 근거)
- **오진입(정파 아닌데 정파모드)**: 실제 방송 문제를 새벽 내내 묵살 → 나쁨.
- **미진입(정파인데 정파모드 아님)**: 새벽 오감지 알림 몇 개 → 경미. 정파모드 목적 자체가 "새벽 불필요 알림 억제"라 목적을 덜 달성할 뿐.
- 며칠 운영 결과 정파준비모드의 **스틸 자동감지(`_tick_preparation`)가 실제 정파를 놓치지 않고 SIGNOFF 전환**함이 확인됨 → 시간 강제진입은 이른 정파엔 중복, 늦은 정파엔 유해.

### 변경 — 3 직접시각 스키마 (`start_time`/`prep_minutes`/`exit_prep_minutes`/`end_next_day`/`force_time_signoff` 전면 제거)
운용자가 의미 있는 **3개 시각을 직접 입력**한다 (그룹당):

| 필드 | 의미 | 기본값 |
|---|---|---|
| `prep_start_time` | 정파준비 시작 시간(이 시각부터 스틸 감지로 진입 대기) | `"00:30"` |
| `exit_prep_start_time` | 정파해제 준비 시작 시간(`""`=미사용) | `"04:30"` |
| `end_time` | 정파해제 시간(하드캡) | `"05:00"` |

- **진입(entry)**: 시간 강제진입 **완전 제거**. SIGNOFF 진입은 **스틸 자동감지 단독**. "정파 예정시각" 개념 자체가 사라짐.
- **해제(exit)**: 시간 기반 유지 — `end_time` 하드캡(이 시각 무조건 IDLE) + 해제준비 구간(`exit_prep_start_time`~`end_time`)의 비스틸 감지 조기 해제. 만약의 오진입도 `end_time`엔 반드시 해제 → 억제 폭주 없음.
- **자정 넘김 자동 판정**: `prep_start_time > end_time`(문자열 비교)이면 wrap 윈도우로 자동 처리. `end_next_day` 수동 토글 제거.
- **수동 버튼(`cycle_state`)**: 정파준비 윈도우 안이면 즉시 SIGNOFF, 밖이면 IDLE.

### 수용한 비용
- PREP는 스틸만 억제(블랙/오디오는 알림)하므로, 늦은 정파의 진입 직전 구간이나 스틸로 안 끝나는 정파(§2 테스트영상)에서 새벽 블랙/오디오 알림 몇 개 발생 가능. 미진입 방향이라 운영상 수용. (탈출구 토글 없음 — 감지 불안정 채널은 수동 버튼 또는 코드로 대응.)

### UI 표현 (대칭 디자인)
- 대기 → "정파준비까지 카운트다운" / 정파준비 → **"감지중"**(클릭=즉시 정파) / 정파중 → "해제까지 카운트다운" / 해제준비 구간 → **"해제 감지중"**.

### 마이그레이션
- 없음. 기존 config에 새 필드 없으면 기본값 로드(`from_dict`의 `_valid_hm` fallback). 운용자가 설정창에서 3 시각 입력·저장 시 새 스키마로 기록됨.

### 핵심 코드 위치
- `detection/signoff_manager.py`: `SignoffGroup`(3 시각 필드), `_is_in_prep_window`(prep_start>end wrap), `_is_in_exit_prep_window`(gap=end−exit_prep_start), `_tick_impl`(진입=감지 단독), `cycle_state`(prep 윈도우 판정).
- `ui/top_bar.py` `update_signoff_state`(exit_detecting 분기), `ui/main_window.py` `_calc_signoff_seconds`·`_is_in_exit_prep`.
- 설정 UI: `ui/settings_dialog.py` `_build_signoff_group_section`(직접 시각 3행 + 해제준비 "사용" 체크박스).

---

## 7. 조기복귀(Early-Revert) — 해제준비 시각 전 오감지 SIGNOFF 자동 회복 (2026-06-08)

### 배경 — §4 문제의 능동적 해소
§4는 오진입한 SIGNOFF가 해제준비 시각(`exit_prep_start_time`, 기본 04:30)까지 갇혀 그동안 해당 그룹 알람이 묵살되는 "느린 자연 회복"을 기술했다. 조기복귀는 이 대기 시간을 없앤다.

### 동작
- SIGNOFF 상태에서 **해제준비 시각 전**에 V영상이 비스틸(움직임)로 `exit_trigger_sec`(기본 30초) 연속 잡히면 → **IDLE이 아니라 PREPARATION으로 복귀**(재무장). 스틸 타이머가 리셋되어 다시 `still_trigger_sec` 스틸이 쌓여야 SIGNOFF 재진입.
- **해제준비 윈도우 안(`exit_prep_start_time`~`end_time`)**에서는 기존대로 비스틸 시 → IDLE(진짜 해제). 즉 같은 "비스틸" 신호를 **해제준비 시각을 경계로** 다르게 해석한다.
- **해제준비 미사용("") 그룹**: end_time 전까지 복귀만 적용, 진짜 해제는 `end_time` 하드캡.
- 복귀 시 텔레그램 발송(중립 문구 "화면 움직임 감지 — 정파준비로 복귀"). `SignoffStateChange.source='auto-revert'`.
- **수동 모드(`auto_preparation` OFF)에선 미작동**(동결) — §5 철학과 일관.

### §3 "빠른 해제" 반려와의 차이 (왜 안전한가)
§3은 "빠른 해제(→IDLE)"를 정상 정파 오해제 위험으로 반려했다. 조기복귀는 **IDLE이 아닌 PREPARATION으로만** 복귀하므로, §2 테스트영상(정파 중 움직이는 점검영상)에서도 영구 오해제가 아니라 "일시 복귀 → 테스트영상 종료 시 스틸 재감지로 자동 재진입"으로 피해가 제한된다 → §6의 "미진입 방향 수용" 원칙에 부합. 이 차이가 §3 반려를 안전하게 우회한다.

### 향후 (Phase B)
복귀 텔레그램으로 가짜 정파 실제 발생 빈도를 관찰해, 자동 모드 정확도가 충분히 확인되면 수동 모드/`cycle_state`를 제거하고 정파 버튼을 정보표시 전용으로 전환 예정.

### 핵심 코드 위치
- `detection/signoff_manager.py`: `_tick_signoff_revert`(신규), `_tick_impl` SIGNOFF 분기(해제준비 전→복귀 / 안→해제), `_transition_to`(auto-revert 문구).
- `processes/detection_process.py`: `_signoff_emit_safe` SIGNOFF→PREPARATION 텔레그램 분기.
- `detection/telegram_worker.py`: `notify_signoff(is_revert=...)`, `_send_signoff` 복귀 렌더.
- 설정 UI 설명: `ui/settings_dialog.py` "정파해제 준비 시작 시간"·"조기 해제 기준 시간" 행 설명 텍스트.

---

## 8. 정파 변동 묶음 처리 · 정파 알림음 배선 · exit_trigger_sec 둔감화 (2026-06-09)

### 배경 — 본사 테스트영상에 의한 플래핑
2026-06-09 새벽, 본사 송출부가 2TV에 **테스트영상(움직이는 영상)** 을 송출하며 점검 → 진입 트리거 V5가 정지↔움직임을 반복 → 상태기계가 SIGNOFF ⇄ 정파준비를 밤새 **10회** 왕복(진입 10·복귀 9·해제 1). 텔레그램 정파 알림이 **약 20건** 폭주(`fix/20260609_ui.txt`).

- **원인 비대칭**: 진입은 `still_trigger_sec`=120초(스틸), 해제(조기복귀)는 `exit_trigger_sec`=5초(움직임). 5초짜리 움직임 블립에 즉시 정파준비로 튕겨나가고 → 120초 스틸이면 다시 빨려듦.
- 동작 자체는 §7 조기복귀가 의도대로 작동한 결과(가짜 정파 재무장). 문제는 **알림 볼륨**.

### 세 갈래 대응 (상호보완)
1. **`exit_trigger_sec` 5초 → 30초 (근원 둔감화)**: 짧은 테스트영상 깜빡임에 더는 조기복귀하지 않음 → 왕복 빈도 자체 감소. 진짜 해제(04:45 본방송 복귀)는 *연속* 움직임이라 30초도 즉시 걸리고, `end_time` 하드캡도 유지. IDLE이 아닌 PREPARATION 복귀라 §3 "빠른 해제 반려"·§2 테스트영상 예외와 일관(안전).
2. **텔레그램 묶음 처리**: 짧은 시간 전환 반복을 "묶음 모드"로 묶어 개별 알림 억제 + 요약.
3. **정파 알림음 배선**: `prep/enter/release_alarm_sound` 3종은 설정창·config엔 있으나 **재생 코드가 없어 한 번도 울리지 않던 미배선(dead) 설정**이었음(플래핑 중 들린 소리는 정파음이 아니라 억제 해제로 되살아난 블랙/오디오 감지음). 이번에 정파 전환 시 1회 재생되도록 배선, 묶음 모드 중에는 텔레그램과 동일 억제.

### 묶음 처리 판정 (`SignoffFlapTracker`)
- 집계 대상 전환: enter(→SIGNOFF) / revert(SIGNOFF→PREPARATION).
- **묶음 진입**: 10분(`FLAP_WINDOW_SEC`) 안에 전환 **3회**(`FLAP_ENTER_COUNT`) 이상 → 묶음 모드 ON, "정파 변동 반복 감지" 텔레그램 1회.
- **묶음 중**: 개별 진입/복귀 텔레그램·정파음 침묵.
- **안정화**: 전환 없이 **25분**(`FLAP_STABLE_SEC`) 경과 또는 정파 해제 시 → "변동 N회 후 안정화, 현재 [정파중/정파준비/해제], 변동 구간 HH:MM~HH:MM" 요약 1회 후 묶음 종료.
- 정상 정파(플래핑 없음)는 전환 3회 임계 미도달 → 기존대로 진입 1·해제 1만 발송(**거동 무변**).
- **25분 결정 근거**: 6/9 로그 시뮬레이션 — 15분이면 17분짜리 짧은 안정 구간을 끊어 요약 중복(20→12건), 25분이면 병합(20→8건). 8건이 그날 바닥(01:39~03:49 **2시간 안정 구간**으로 플래핑 에피소드가 둘로 갈렸기 때문). 정상 정파 시작/해제는 보존하는 설계상 더 못 줄임.

### 정파 알림음 매핑 (전환 → 음)
- IDLE/SIGNOFF→PREPARATION → `prep`(조기복귀 포함) / →SIGNOFF → `enter` / SIGNOFF→IDLE → `release` / PREPARATION→IDLE(정파 없이 종료)·restore(재주입) → 무음.
- 감지 알람음(`alarm.wav`)을 끊지 않는 별도 one-shot(`AlarmSystem.play_signoff_sound`). 두 소리가 겹치면 단일 채널 특성상 짧은 끊김 가능(드문 이벤트라 수용).

### 파라미터 (상수, 설정 노출 없음 — `detection/signoff_flap.py`)
| 상수 | 값 | 의미 |
|---|---|---|
| `FLAP_WINDOW_SEC` | 600 | 변동 집계 창(10분) |
| `FLAP_ENTER_COUNT` | 3 | 묶음 진입 임계 |
| `FLAP_STABLE_SEC` | 1500 | 안정화 판정(25분) |

### 핵심 코드 위치
- `detection/signoff_flap.py`(신규): `SignoffFlapTracker`, `FLAP_*` 상수.
- `processes/detection_process.py`: `_signoff_emit_safe`(묶음 판정·텔레그램 분기·`suppress_alarm_sound` 태깅) + 메인 루프 안정화 폴링.
- `detection/telegram_worker.py`: `notify_signoff_flap`/`_send_signoff_flap`.
- `ipc/messages.py`: `SignoffStateChange.suppress_alarm_sound`.
- `ui/main_window.py`: `_on_signoff_state_changed`(전환 시 정파음) + `_load_signoff_sounds`.
- `ui/alarm.py`: `play_signoff_sound`(감지음 비차단 1회 재생).

---

## 부록 — 관련 참조

- 코드 규칙: `detection/CLAUDE.md` "히스테리시스 원칙", "정파 억제 규칙"
- IPC 사양: `docs_ipc_spec.md` (SignoffStateChange 메시지)
- 5/18 케이스 로그: `fix/20260518_ui.txt`
