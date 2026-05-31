"""
캡처 입력 상실 자동복구 워치독 (순수 상태기계)

목적
----
캡처보드가 입력 신호를 잃으면 흔히 "유효하지만 완전 검정인 프레임"(ret=True)을
계속 내보낸다. 이 경우 video_capture 의 ret=False 기반 재연결이 영영 걸리지 않아
사람이 프로그램을 재시작할 때까지 무한 블랙이 지속된다.

이 워치독은 화면 *전체* 가 "얼어붙은 검정"(정지 + 블랙) 으로 일정 시간 지속되면
캡처 디바이스만 재오픈(force_reconnect)해 자동 복구를 시도한다.

설계 원칙
---------
- **탐지/기록과 독립(병렬)**: 기존 블랙 알람·로그·녹화 경로는 전혀 건드리지 않는다.
  진짜 블랙이면 1층(채널별 블랙 알람)이 정상적으로 기록·녹화한다.
  이 워치독은 순수 추가물(로그 + 텔레그램 + 캡처 재오픈)이다.
- **보드/설정 무관**: 입력은 원본 프레임에서 자체 계산한 global_black/frozen 만 사용한다.
  detector 의 ROI별 결과나 black/still 감지 설정에 의존하지 않는다.
- **순수 상태기계**: I/O 부수효과 없음. update() 가 수행할 액션 목록만 반환하고,
  실제 재오픈/로그/텔레그램 발송은 호출측(Detection 메인 루프)이 담당 → 단위테스트 용이.

상태 전이
---------
    NORMAL      전 화면 frozen-black 이 trigger_sec 지속 → RECOVERING (재오픈 1회)
    RECOVERING  observe_sec 관찰
                  ├─ 비블랙 프레임 복귀  → COOLDOWN (복구 완료)
                  ├─ 여전히 블랙 & 시도 < max_attempts → 재오픈 재시도
                  └─ 여전히 블랙 & 시도 소진          → ESCALATED (복구 실패)
    ESCALATED   더 이상 재오픈하지 않음. 비블랙 복귀 시 → COOLDOWN
    COOLDOWN    cooldown_sec 동안 재트리거 억제 → NORMAL (플래핑 방지)
"""

NORMAL = "NORMAL"
RECOVERING = "RECOVERING"
ESCALATED = "ESCALATED"
COOLDOWN = "COOLDOWN"


class CaptureLossWatchdog:
    """캡처 입력 상실 감지 → 자동 재오픈 복구 상태기계 (부수효과 없음)."""

    def __init__(self, *, enabled=True, trigger_sec=8.0, observe_sec=5.0,
                 max_attempts=3, cooldown_sec=60.0):
        self.enabled = bool(enabled)
        self.trigger_sec = float(trigger_sec)
        self.observe_sec = float(observe_sec)
        self.max_attempts = int(max_attempts)
        self.cooldown_sec = float(cooldown_sec)

        self.state = NORMAL
        self.attempts = 0
        self._loss_since = None
        self._observe_start = 0.0
        self._cooldown_until = 0.0

    def _to_normal(self):
        self.state = NORMAL
        self.attempts = 0
        self._loss_since = None

    def update(self, now, frame_black, frozen, gated):
        """매 루프 1회 호출.

        Parameters
        ----------
        now : float
            time.monotonic() 값.
        frame_black : bool | None
            화면 전체가 블랙인지. None = 이번 틱에 신선한 프레임 없음(판단 불가).
        frozen : bool | None
            직전 프레임 대비 정지(얼어붙음) 여부. None = 판단 불가.
        gated : bool
            True 면 동작 보류(정파 활성/감지 비활성/ROI편집중/파일재생모드 등).

        Returns
        -------
        list[tuple]
            수행할 액션 목록. 각 원소는 다음 중 하나:
              ("reconnect", None)         캡처 디바이스 재오픈
              ("log", (level, message))   level: "info" | "warn"
              ("telegram", message)       notify_system 발송
        """
        actions = []

        if not self.enabled or gated:
            # 동작 보류 — 진행 중 사이클은 깔끔히 초기화
            if self.state != NORMAL:
                self._to_normal()
            else:
                self._loss_since = None
            return actions

        loss = (frame_black is True) and (frozen is True)
        recovered = (frame_black is False)  # 명확히 비블랙인 프레임을 봤을 때만

        if self.state == NORMAL:
            if loss:
                if self._loss_since is None:
                    self._loss_since = now
                elif now - self._loss_since >= self.trigger_sec:
                    self.state = RECOVERING
                    self.attempts = 1
                    self._observe_start = now
                    actions.append(("log", (
                        "warn",
                        f"캡처 입력 신호 상실 감지 (화면 전체 정지+블랙 {self.trigger_sec:.0f}초 지속) "
                        f"→ 캡처 자동 재오픈 {self.attempts}/{self.max_attempts}",
                    )))
                    actions.append(("telegram",
                                    "캡처 입력 신호 상실 감지 — 자동 복구를 시도합니다."))
                    actions.append(("reconnect", None))
            else:
                self._loss_since = None

        elif self.state == RECOVERING:
            if recovered:
                self.state = COOLDOWN
                self._cooldown_until = now + self.cooldown_sec
                self._loss_since = None
                actions.append(("log", (
                    "info", f"캡처 입력 자동 복구 완료 (재오픈 {self.attempts}회)")))
                actions.append(("telegram", "캡처 입력 자동 복구 완료."))
            elif now - self._observe_start >= self.observe_sec:
                # 관찰 종료 시점에도 복구 안 됨 → 이번 재오픈 실패로 간주
                if self.attempts < self.max_attempts:
                    self.attempts += 1
                    self._observe_start = now
                    actions.append(("log", (
                        "warn",
                        f"캡처 재오픈 후에도 신호 없음 → 재시도 {self.attempts}/{self.max_attempts}")))
                    actions.append(("reconnect", None))
                else:
                    self.state = ESCALATED
                    actions.append(("log", (
                        "warn",
                        f"캡처 입력 자동 복구 실패 ({self.max_attempts}회 재오픈) "
                        f"— 입력 케이블/캡처보드 점검 필요")))
                    actions.append(("telegram",
                                    "캡처 입력 자동 복구 실패 — 입력/캡처보드 점검이 필요합니다."))

        elif self.state == ESCALATED:
            if recovered:
                self.state = COOLDOWN
                self._cooldown_until = now + self.cooldown_sec
                self._loss_since = None
                actions.append(("log", ("info", "캡처 입력 복구 확인")))

        elif self.state == COOLDOWN:
            if now >= self._cooldown_until:
                self._to_normal()

        return actions
