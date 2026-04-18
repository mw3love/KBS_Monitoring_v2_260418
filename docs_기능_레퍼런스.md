# KBS 16채널 비디오 모니터링 시스템 (KBS Peacock v1.6.21) - 기능 레퍼런스 문서

> 작성 목적: 재작성(v2) 프로젝트의 요구사항 기반 자료
> 작성 기준: "무엇을 하는가" 중심 (구현 방법 제외)
> 작성일: 2026-04-16

---

## 1. 프로그램 전체 개요

KBS Peacock v1.6.21은 16개 채널의 방송 영상과 오디오를 실시간으로 모니터링하는 시스템입니다. 영상 신호 품질(블랙, 스틸, 무음), 임베디드 오디오 무음을 감지하고, 정파(Sign-off) 모드의 자동화된 상태 관리를 제공합니다.

**주요 기능:**
- 실시간 영상 감지 (블랙/스틸)
- 오디오 레벨미터 감지 (HSV 기반 색상 감지)
- 임베디드 오디오 무음 감지
- 감지 영역(ROI) 편집 기능
- 정파 준비/정파모드 자동 상태 관리
- 다중 알림 시스템 (소리/시각/텔레그램)
- 자동 녹화 기능 (사고 전후 영상/오디오 버퍼링)
- 설정 저장/불러오기
- Watchdog 모니터링 (감지 루프 staleness 감지)
- 자동 예약 재시작

---

## 2. UI 구조 전체

### 2.1 메인 윈도우 레이아웃

**3분할 구성:**
- **상단 바 (TopBar)**: 시스템 정보, 제어 버튼, 시간, 오디오, 감지현황, 정파 상태 (높이: 68px)
- **비디오 영역 (VideoWidget)**: 1920×1080 영상 또는 "NO SIGNAL INPUT" 표시, 감지영역 오버레이 (약 75%)
- **로그 영역 (LogWidget)**: 시스템 로그 및 감지 이벤트 (약 25%, 최대 500개)

**분할 비율**: 수평 3:1, 스플리터로 동적 조정 가능

---

### 2.2 상단 바 구성

#### 시스템 성능 수치 (2초 주기 갱신)
- **CPU 사용률**: psutil 기반
- **RAM 사용률**: psutil 기반
- **GPU 사용률**: GPUtil 또는 nvidia-smi (미설치 시 "N/A")

#### Health Check 인디케이터
- 감지 루프 중단 감지 (5초 이상 응답 없음)
- 정상 시 숨김 / 이상 시 빨간색 "감지 중단" 표시
- Watchdog 텔레그램 알림 발송

#### 현재 시간
- HH:MM:SS 형식, 1초 주기 갱신

#### Embedded Audio 영역
- **음소거 버튼**: 체크 시 볼륨 0 (이전 값 기억)
- **볼륨 슬라이더**: 0~100% (기본 80%), L/R 패스스루 출력 동시 조절
- **L/R 레벨 미터**: 채널당 세로 10칸 세그먼트, -60~0 dB
  - 상단 2칸: 밝은 빨간 (#ff2222)
  - 3~4칸: 주황빛 빨간 (#ee3322)
  - 나머지: 기본 빨간 (#bb1111)

#### 감지 현황 표시
- **V**: 비디오 감지영역 개수
- **A**: 오디오 감지영역 개수
- **EA**: 임베디드 오디오 감지 활성화 여부 ("1"/"0"/"-")
  - 알림 중: 빨간색 (#cc0000) / 활성: 기본색 / 비활성: 회색

#### 제어 버튼군
1. **감지 ON/OFF**: 모든 감지 비활성화 시 알람/깜빡임 즉시 해제
2. **감지영역 보이기/숨기기**: ROI 오버레이 토글 (알림 중인 ROI는 항상 표시)
3. **Mute**: 프로그램 알림음 음소거
4. **알림확인**: 소리/깜빡임 해제 (감지기 상태 유지, 동일 이상 재알림 없음)
5. **그룹1/2 정파 버튼**: IDLE → PREPARATION → SIGNOFF → IDLE 수동 순환 (소리 없음)
   - 버튼 하단에 현재 상태까지 남은 시간 카운트다운 표시: `정파준비까지 1D [6H:6M:26S]` 형식
   - IDLE 상태: "정파준비까지 Xd [HH:MM:SS]" / PREPARATION: "정파까지 [HH:MM:SS]" / SIGNOFF: "정파해제준비까지 [HH:MM:SS]"
6. **설정**: 설정 다이얼로그 열기 (비모달)
7. **주간/야간 모드**: 다크/라이트 테마 전환
8. **전체화면**: F11 단축키 또는 버튼 클릭

---

### 2.3 비디오 영역

**기본 상태:**
- 1920×1080 프레임 표시
- 프레임 없을 시 "NO SIGNAL INPUT" 검은 배경

**ROI 오버레이 (show_rois=True 또는 알림 중):**
- **비디오 ROI**: 빨간색 경계선, 알림 중: 밝은 빨간 + 반투명 채우기 + 500ms 깜빡임
- **오디오 ROI**: 주황색 경계선, 알림 중: 동일 깜빡임
- **ROI 레이블**: `V1 [1TV]` 형식 (한글 지원, 검은 외곽선 + 흰 글자)
- 아스펙트 비율 유지 (레터박스 처리)

---

### 2.4 로그 영역

**헤더**: "SYSTEM LOG" 제목 + "Log 폴더 열기" + "Log 초기화" (화면만, 파일 보존)

**로그 항목 색상:**
| log_type | 배경색 |
|----------|-------|
| error (블랙) | 빨간 #cc0000 |
| still (스틸) | 보라 #7B2FBE |
| audio (오디오레벨미터) | 초록 #006600 |
| embedded (임베디드) | 파란 #004488 |
| info (일반) | QSS 테마색 |

날짜 변경 시 구분선 자동 삽입 / 최대 500개 (초과 시 오래된 항목 삭제)

---

### 2.5 설정 다이얼로그 (7개 탭)

#### 탭 1: 영상설정
- 포트 선택 (0~31) 또는 비디오 파일 선택 (MP4, AVI 등), 파일 선택 시 조기화 버튼으로 포트 모드 복귀
- 자동 녹화 설정 (활성화, 저장 폴더, 찾아보기, 폴더 열기)
- 녹화 구간: 사고 전 버퍼(1~30초), 사고 후 녹화(1~60초)
- 파일 관리: 최대 보관 기간(1~365일)
- 녹화 출력 설정: 출력 해상도 드롭다운, 출력 FPS 입력
- 하단 정보 표시: 버퍼 메모리 / 예상 파일 크기 / 코덱
- "영상설정 전체 초기화" 버튼

#### 탭 2: 비디오 영역 설정
- 상단 "비디오 감지영역 편집" 버튼: 클릭 시 영상 위 ROI 오버레이 편집 모드 진입 ("편집 완료(클릭하여 종료)"로 변경)
- 편집 모드 조작: 빈 곳 드래그=새 영역, 영역 드래그=이동, Shift+드래그=수직/수평 이동, Ctrl+드래그(빈 곳)=범위 다중 선택, Ctrl+클릭=선택 추가/제거, 다중선택 후 드래그=한번에 이동, 다중선택 후 Ctrl+드래그=복사, Ctrl+Shift+드래그=수직/수평 복사
- ROI 테이블 (라벨, 매체명, X, Y, W, H)
- 버튼: 추가(이전 행 X,Y 소폭 오프셋으로 생성) / 삭제 / ▲위로 / ▼아래로 / 전체 초기화

#### 탭 3: 오디오 레벨미터 영역 설정
- 탭 2와 동일 구조 (A1, A2, ... 레이블)

#### 탭 4: 감도설정 (5개 섹션)
- 블랙 감지 파라미터
- 스틸 감지 파라미터
- 오디오 레벨미터(HSV) 파라미터
- 임베디드 오디오 파라미터
- 성능 설정 (감지 주기, 해상도 스케일 드롭다운, 타입별 활성화)
- **"자동 성능 감지" 버튼**: 현재 시스템 CPU/RAM 성능을 측정하여 scale_factor / detection_interval 추천값 자동 적용

#### 탭 5: 정파설정
- 자동 정파 활성화 체크박스, "자동정파 안내" 버튼
- 그룹 1/2 각각:
  - 그룹명, 정파모드 시작/종료 시각, 익일 종료 체크박스
  - 정파준비 활성화 (X분 전 선택 → 실제 시각 표시)
  - 정파해제준비 활성화 (X분 전 선택 → 실제 시각 표시)
  - 몇 초 이상시 정파해제 (exit_trigger_sec)
  - 요일 선택 (매일 또는 개별 요일)
  - **"정파 감지영역" 버튼** → 팝업 다이얼로그:
    - **진입 트리거**: 단일 드롭다운 — 선택한 비디오 ROI가 스틸 상태 지속 시 SIGNOFF 조기 진입 (enter_roi)
    - **알림 억제 대상**: 비디오/오디오 ROI 다중 체크박스 — SIGNOFF 중 해당 ROI 알림 억제 (suppressed_labels)
- **정파 알림음** (3종, 각 파일 선택+테스트):
  - 정파준비 시작 (prep_alarm_sound)
  - 정파모드 진입 (enter_alarm_sound)
  - 정파 해제 (release_alarm_sound)
- "정파설정 전체 초기화" 버튼

#### 탭 6: 알림설정
- 알림음 파일 경로 설정 (찾아보기, 초기화, 테스트)
- 텔레그램 봇 설정 (활성화, Bot Token, Chat ID, 연결 테스트)
- 텔레그램 알림 옵션: 이미지 첨부, 타입별 알림 플래그(블랙/스틸/오디오레벨미터/임베디드), 쿨다운
- **자동 재시작** 섹션: 재시작 시각 1/2 (HH:MM, 각 활성화 체크박스), OS 리소스 초기화 목적

#### 탭 7: 저장/불러오기
- 현재 설정 저장 (파일 다이얼로그 → JSON)
- 설정 파일 불러오기 (JSON → 즉시 적용)
- 기본값으로 초기화 (확인 다이얼로그 → 기본값 적용)
- About 정보 (버전, 날짜, GitHub, E-mail)

---

## 3. 감지 기능 상세

### 3.1 블랙 감지

**감지 조건**: ROI 영역의 어두운 픽셀 비율 >= `black_dark_ratio`% 지속

**히스테리시스**: 없음 (단일 정상 프레임으로 복구)

**모션 억제**: 블랙 판정 후 `changed_ratio >= black_motion_suppress_ratio`이면 블랙 취소 (스크롤 자막 오감지 방지)

| 파라미터 | 기본값 | 범위 | 설명 |
|--------|------|-----|------|
| black_threshold | 5 | 0~255 | 어두움 기준 픽셀값 |
| black_dark_ratio | 98.0 | 0~100% | 어두운 픽셀 비율 기준 |
| black_duration | 20 | 1~300초 | 알림 발생까지 지속 시간 |
| black_alarm_duration | 60 | 1~300초 | 알림 지속 시간 |
| black_motion_suppress_ratio | 0.2 | 0~100% | 모션 억제 비율 |

---

### 3.2 스틸 감지

**감지 조건**: 5×5 블록 분할 시 모든 블록의 변화량이 `still_block_threshold`% 미만으로 지속

**히스테리시스**: `still_reset_frames` 연속 정상 프레임 카운터 — 이 수치 미만이면 타이머 유지 (글리치 방지)

**near-miss 추적**: dark_ratio>80% 또는 changed_ratio<3% 상태 30초 이상 지속 시 진단 로그 출력 (30초 1회)

| 파라미터 | 기본값 | 범위 | 설명 |
|--------|------|-----|------|
| still_threshold | 4 | 0~255 | 프레임 차이 기준값 |
| still_block_threshold | 10.0 | 0~100% | 블록 움직임 기준 |
| still_duration | 60 | 1~300초 | 알림 발생까지 지속 시간 |
| still_alarm_duration | 60 | 1~300초 | 알림 지속 시간 |
| still_reset_frames | 3 | 1~10 | 히스테리시스 프레임 수 |

---

### 3.3 오디오 레벨미터 감지 (HSV 기반)

**감지 조건**: 오디오 ROI의 HSV 범위 내 픽셀 비율 < `audio_pixel_ratio`% 지속 (무음 판정)

**이동 평균**: 최근 5프레임 평균 적용

**복구 히스테리시스**:
- `audio_level_recovery_seconds > 0`: 활성 상태가 해당 초 이상 지속 시 복구
- `= 0`: `still_reset_frames` 방식의 연속 정상 프레임 카운터 사용

| 파라미터 | 기본값 | 범위 | 설명 |
|--------|------|-----|------|
| audio_hsv_h_min/max | 40/95 | 0~179 | Hue 범위 |
| audio_hsv_s_min/max | 80/255 | 0~255 | Saturation 범위 |
| audio_hsv_v_min/max | 60/255 | 0~255 | Value 범위 |
| audio_pixel_ratio | 5.0 | 0~100% | 활성 픽셀 비율 기준 |
| audio_level_duration | 20 | 1~300초 | 알림 발생까지 지속 시간 |
| audio_level_alarm_duration | 60 | 1~300초 | 알림 지속 시간 |
| audio_level_recovery_seconds | 2.0 | 0~30초 | 복구 딜레이 |

---

### 3.4 임베디드 오디오 무음 감지

**감지 조건**: 시스템 오디오 스트림의 L/R 평균 RMS <= `embedded_silence_threshold` dB 지속

**복구**: 정상 신호 수신 시 즉시 복구 (딜레이 없음)

**스트림 장애**: 연속 10회 실패 → 3초 대기 후 재연결 시도

| 파라미터 | 기본값 | 범위 | 설명 |
|--------|------|-----|------|
| embedded_silence_threshold | -50 | -60~0 dB | 무음 기준 |
| embedded_silence_duration | 20 | 1~300초 | 알림 발생까지 지속 시간 |
| embedded_alarm_duration | 60 | 1~300초 | 알림 지속 시간 |

---

## 4. 알림 시스템

### 4.1 3가지 알림 채널

| 채널 | 조건 | 해제 조건 |
|------|------|---------|
| 시각적 (ROI 깜빡임) | 항상 활성 | 감지 해제 또는 알림확인 |
| 청각적 (WAV 반복) | Mute OFF 상태 | 감지 해제 또는 알림확인 |
| 텔레그램 | 설정 활성화 + 타입별 플래그 | 감지 해제 시 복구 메시지 발송 |

### 4.2 시각적 알림

- ROI 반투명 채우기 + 밝은 경계선, 500ms 주기 깜빡임
- "알림확인" 버튼도 빨간 배경으로 변경

### 4.3 청각적 알림

- `resources/sounds/alarm.wav` 반복 재생 (파일 없으면 Windows 내장음)
- 볼륨: 0~100% (기본 80)
- 다중 감지 시 단일 알림음 재생 (중복 방지)

### 4.4 알림확인(Acknowledge) 동작

- 소리/깜빡임 즉시 중지
- 동일 이상이 지속되어도 재알림 없음
- 감지 resolve 시 acknowledged 상태 제거 → 다음 이상 발생 시 정상 알림 재개

### 4.5 텔레그램 알림

- **발송**: `/sendMessage` + `/sendPhoto` (JPEG 85품질)
- **메시지**: `[LABEL] 감지타입 감지\n시각: YYYY-MM-DD HH:MM:SS`
- **복구**: `[LABEL] 감지타입 복구 (지속: Ns)\n시각: ...`
- **쿨다운**: 동일 채널 중복 발송 방지 (기본 60초)
- **워커**: 백그라운드 큐 기반 → 실패 시 2회 재시도 → 워커 사망 시 자동 재시작

---

## 5. 정파(Signoff) 시스템

### 5.1 3가지 상태

| 상태 | 설명 | 자동 전환 조건 |
|-----|------|-------------|
| IDLE | 정파 시간대 밖 | start_time - prep_minutes 도달 |
| PREPARATION | 정파 준비 구간 | start_time 도달 또는 enter_roi 스틸 조기 감지 |
| SIGNOFF | 정파 중 | end_time 도달 또는 exit_prep 구간에서 비-스틸 감지 |

수동 전환: 상단바 버튼 클릭 → 순환 (소리 없음)

### 5.2 히스테리시스

**진입 (PREPARATION → SIGNOFF)**:
- enter_roi 스틸 지속 >= `still_trigger_sec` 초 → SIGNOFF
- 비-스틸 3연속 → 타이머 리셋 (아티팩트 방지)

**해제 (SIGNOFF → IDLE)**:
- exit_prep_minutes 구간에서 비-스틸 지속 >= `exit_trigger_sec` 초 → IDLE
- 스틸 감지 시 카운터 리셋

### 5.3 정파 중 알림 억제

- SIGNOFF 상태 + `suppressed_labels` 목록 ROI → 알림 즉시 resolve
- PREPARATION 상태: 스틸 억제, 블랙은 계속 발생
- 억제 시작 로그: 1회만 출력

### 5.4 주요 파라미터

| 파라미터 | 기본값 | 설명 |
|--------|------|------|
| auto_preparation | True | 자동 정파준비 활성화 |
| prep_minutes | 150/90분 | 정파준비 선행 시간 (30분 단위) |
| exit_prep_minutes | 180/30분 | 정파해제준비 구간 |
| still_trigger_sec | 5초 | 진입 스틸 지속 기준 (enter_roi 스틸이 이 시간 이상 지속 시 SIGNOFF 조기 진입) |
| exit_trigger_sec | 5초 | 조기 해제 트리거 시간 |
| weekdays | 요일 목록 | 적용 요일 (every_day=True면 무시) |

---

## 6. 자동 녹화 기능

### 6.1 구조

- 순환 버퍼: 비디오(JPEG 압축) + 오디오(Raw PCM) 상시 유지
- 알림 발생 → 사전 버퍼 + 사후 녹화 → ffmpeg로 비디오+오디오 합성 → MP4 저장
- 녹화 중 추가 알림 → record_end 시간 연장 (새 파일 미생성)
- 파일명: `YYYYMMDD_HHMMSS_mmm_{label}_{media}_{type}.mp4`

### 6.2 파라미터

| 파라미터 | 기본값 | 범위 | 설명 |
|--------|------|-----|------|
| enabled | True | - | 자동 녹화 활성화 |
| save_dir | "recordings" | - | 저장 폴더 |
| pre_seconds | 5 | 1~60초 | 사고 전 버퍼 |
| post_seconds | 15 | 1~60초 | 사고 후 녹화 |
| max_keep_days | 7 | 1~30일 | 최대 보관 일수 |
| output_width | 960 | 160~1920px | 출력 가로 |
| output_height | 540 | 90~1080px | 출력 세로 |
| output_fps | 10 | 1~30fps | 출력 FPS |

**ffmpeg 없으면**: 비디오 전용 MP4로 폴백 (소리 없음, 에러 아님)

---

## 7. 감지영역(ROI) 편집

### 7.1 반화면 편집 모드

- 진입 조건: 설정 탭 "편집" 버튼 → 감지 타이머 중단
- 마우스 드래그로 ROI 생성/이동/리사이즈
- Ctrl+드래그: 다중 선택 / Ctrl+클릭: 개별 토글 / Del: 삭제 / Ctrl+D: 복사

### 7.2 ROI 구조

| 필드 | 설명 |
|-----|------|
| label | "V1", "A1" (자동 생성) |
| media_name | "1TV", "2TV" (사용자 입력) |
| x, y | 좌표 (픽셀) |
| w, h | 크기 (픽셀, 최대 500×300) |
| roi_type | "video" 또는 "audio" |

---

## 8. 시스템 모니터링

### 8.1 시스템 수치

CPU/RAM/GPU 2초 주기 갱신 (TopBar)

### 8.2 Heartbeat + DIAG 로그 (약 30초 주기)

- **SYSTEM-HB**: 경과 시간, 타이머 상태, 스레드 수
- **DIAG-V**: 비디오 ROI별 블랙/스틸 상태
- **DIAG-ALARM**: 현재 활성 알람 목록
- **DIAG-SIGNOFF**: 정파 그룹 상태
- **DIAG-AUDIO**: 오디오 감지 상태
- **DIAG-TELEGRAM**: 워커 상태, 큐 크기

---

## 9. 로그 시스템

- **파일 로그**: `logs/YYYYMMDD.txt`, 일별 로테이션, 90일 보관
- **UI 로그**: 최대 500개, 타입별 색상 구분, 날짜 구분선 자동 삽입
- **로그 폭풍 방지**: 동일 에러 반복 시 1회 후 "반복" 표시

---

## 10. Watchdog 기능

### 10.1 감지 루프 Staleness 감지

- 5초 이상 감지 루프 응답 없음 → 빨간 "감지 중단" 표시 + 텔레그램 알림 (프레임 첨부)
- 복구 시: "감지 루프 정상 복구" 로그

### 10.2 텔레그램 워커 모니터

- 30초 주기 확인 → 워커 사망 시 자동 재시작

---

## 11. 예약 재시작

- 지정 시각에 프로그램 자동 재시작 (최대 2개 시각 설정)
- 10초 주기로 설정 파일 직접 확인 (런타임 변경 즉시 반영)
- 같은 슬롯 중복 실행 방지
- 프로그램 비정상 재시작 시 텔레그램 알림 발송 (v2 신규 추가 예정)

---

## 12. 전체 설정값 목록

### 감지(Detection)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| black_threshold | 5 | 0~255 | 픽셀값 |
| black_dark_ratio | 98.0 | 0~100 | % |
| black_duration | 20 | 1~300 | 초 |
| black_alarm_duration | 60 | 1~300 | 초 |
| black_motion_suppress_ratio | 0.2 | 0~100 | % |
| still_threshold | 4 | 0~255 | 픽셀값 |
| still_block_threshold | 10.0 | 0~100 | % |
| still_duration | 60 | 1~300 | 초 |
| still_alarm_duration | 60 | 1~300 | 초 |
| still_reset_frames | 3 | 1~10 | 프레임 |
| audio_hsv_h_min | 40 | 0~179 | - |
| audio_hsv_h_max | 95 | 0~179 | - |
| audio_hsv_s_min | 80 | 0~255 | - |
| audio_hsv_s_max | 255 | 0~255 | - |
| audio_hsv_v_min | 60 | 0~255 | - |
| audio_hsv_v_max | 255 | 0~255 | - |
| audio_pixel_ratio | 5.0 | 0~100 | % |
| audio_level_duration | 20 | 1~300 | 초 |
| audio_level_alarm_duration | 60 | 1~300 | 초 |
| audio_level_recovery_seconds | 2.0 | 0~30 | 초 |
| embedded_silence_threshold | -50 | -60~0 | dB |
| embedded_silence_duration | 20 | 1~300 | 초 |
| embedded_alarm_duration | 60 | 1~300 | 초 |

### 성능(Performance)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| detection_interval | 200 | 100~1000 | ms |
| scale_factor | 1.0 | 1.0/0.5/0.25 | - |
| black_detection_enabled | True | - | - |
| still_detection_enabled | True | - | - |
| audio_detection_enabled | True | - | - |
| embedded_detection_enabled | True | - | - |

### 알림(Alarm)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| sound_enabled | True | - | - |
| volume | 80 | 0~100 | % |
| sound_file | "resources/sounds/alarm.wav" | - | 경로 |

### 텔레그램(Telegram)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| enabled | False | - | - |
| bot_token | "" | - | - |
| chat_id | "" | - | - |
| send_image | True | - | - |
| cooldown | 60 | 1~3600 | 초 |
| notify_black | True | - | - |
| notify_still | True | - | - |
| notify_audio_level | True | - | - |
| notify_embedded | True | - | - |
| notify_signoff | True | - | - |

> **주의**: `notify_signoff`는 config에 존재하지만 알림설정 탭 UI에는 표시되지 않음 (내부 동작용)

### 녹화(Recording)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| enabled | True | - | - |
| save_dir | "recordings" | - | 경로 |
| pre_seconds | 5 | 1~30 | 초 |
| post_seconds | 15 | 1~60 | 초 |
| max_keep_days | 7 | 1~365 | 일 |
| output_width | 960 | 160~1920 | px |
| output_height | 540 | 90~1080 | px |
| output_fps | 10 | 1~30 | fps |

### 정파(Signoff)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| auto_preparation | True | - | - |
| name (G1/G2) | "1TV"/"2TV" | - | - |
| start_time | "03:00"/"02:00" | HH:MM | - |
| end_time | "05:00" | HH:MM | - |
| end_next_day | False | - | - |
| prep_minutes | 150/90 | 0~180 | 분 (30 단위) |
| exit_prep_minutes | 180/30 | 0~180 | 분 (30 단위) |
| still_trigger_sec | 5 | 1~300 | 초 |
| exit_trigger_sec | 5 | 1~300 | 초 |
| weekdays | [0,1]/[0~6] | - | 0=월 |
| enter_roi | None | - | 진입 트리거 ROI 라벨 (단일) |
| suppressed_labels | [] | - | 알림 억제 대상 ROI 라벨 목록 |
| prep_alarm_sound | "resources/sounds/sign_off.wav" | - | 정파준비 시작 알림음 |
| enter_alarm_sound | "resources/sounds/sign_off.wav" | - | 정파모드 진입 알림음 |
| release_alarm_sound | "resources/sounds/sign_off.wav" | - | 정파 해제 알림음 |

### UI 상태(ui_state)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| detection_enabled | True | - | 감지 ON/OFF 상태 (재시작 시 복원) |
| roi_visible | True | - | 감지영역 표시 상태 (재시작 시 복원) |
| fullscreen | False | - | 전체화면 상태 (재시작 시 복원) |

### 시스템(System)

| 항목 | 기본값 | 범위 | 단위 |
|------|------|-----|-----|
| scheduled_restart_enabled | True | - | - |
| scheduled_restart_time | "08:56" | HH:MM | - |
| scheduled_restart_time_2 | "" | HH:MM | - |

---

## 13. v2 재작성 시 추가/변경 사항

- **프로그램 비정상 재시작 텔레그램 알림** (신규)
- **채널당 메모리 버퍼 상한** (신규, 장기 운영 안정성)
- **multiprocessing 기반 아키텍처** (핵심 변경, freeze 문제 해결 목적)
- **독립 Watchdog 프로세스** (신규, 메인 프로세스 외부에서 감시)
