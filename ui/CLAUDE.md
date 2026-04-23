# UI 프로세스 — 개발 규칙

## PySide6 QWidget 생성 규칙
- `QScrollArea` 사용 시: `QWidget()` 생성 직후 **즉시** `setWidget()` 호출 (GC 삭제 방지)
- 레이아웃 변수명은 역할별로 명확하게 (`inner`, `layout` 같은 범용 이름 재사용 금지)
  - 잘못된 예: `layout = QVBoxLayout()` → 이후 `layout = QHBoxLayout()` 덮어쓰기 → 이전 위젯 GC 삭제
  - 올바른 예: `scroll_layout = QVBoxLayout()`, `button_row = QHBoxLayout()`

## UI 전용 규칙
- **QSpinBox 위아래 버튼 사용 금지**
- 색상 원칙: 정상=색 없음(기본 배경/텍스트), 이상=빨간색만 사용 (초록색 금지)
  - 예외: `ui/log_widget.py`의 로그 타입 구분 색상은 시각 구별을 위해 허용
    (블랙이상=빨간 #cc0000, 스틸이상=보라 #7B2FBE, 오디오레벨미터=초록 #006600, 임베디드=파란 #004488)

## AlarmSystem 위치
- UI 프로세스에만 존재 (winsound는 Windows GUI 스레드 연관)
- trigger/resolve는 UIBridge.alarm_event_received Signal로 수신

## 알림 상태(Acknowledge)
- **UI 프로세스에만 존재** (`ui/alarm.py`의 `AlarmSystem`이 보관)
- Detection은 trigger/resolve 이벤트만 계속 발행 (ack 상태 모름)
- UI는 동일 라벨 재trigger 시 사운드/깜빡임 억제, resolve 수신 시 ack 해제
- 근거: Detection은 "감지 중", UI는 "사용자 알림 중" — 관심사 분리
