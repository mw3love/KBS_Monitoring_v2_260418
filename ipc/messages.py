"""
프로세스 간 Queue 메시지 dataclass 정의
docs_ipc_spec.md §2 와 1:1 대응. 이 파일 단독 변경 금지 — 스펙 문서 먼저 갱신.
"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass(kw_only=True)
class BaseMsg:
    ts: float = field(default_factory=time.time)


# ──────────────────────────────────────────────
# result_queue (Detection → UI, maxsize=200)
# ──────────────────────────────────────────────

@dataclass
class DetectionResult(BaseMsg):
    label: str = ""
    roi_type: str = ""          # 'video' | 'audio' | 'embedded'
    media_name: str = ""
    detection_type: str = ""    # 'black' | 'still' | 'audio_level' | 'embedded'
    active: bool = False
    duration_sec: float = 0.0
    meta: dict = field(default_factory=dict)


@dataclass
class AlarmTrigger(BaseMsg):
    label: str = ""
    detection_type: str = ""
    roi_type: str = ""
    snapshot_jpeg: Optional[bytes] = None


@dataclass
class AlarmResolve(BaseMsg):
    label: str = ""
    detection_type: str = ""
    duration_sec: float = 0.0


@dataclass
class LogEntry(BaseMsg):
    level: str = "info"         # 'debug' | 'info' | 'error' | 'still' | 'audio' | 'embedded'
    source: str = ""
    message: str = ""


@dataclass
class DiagSnapshot(BaseMsg):
    section: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class SignoffStateChange(BaseMsg):
    group_id: int = 1           # 1 | 2
    prev_state: str = ""
    new_state: str = ""         # 'IDLE' | 'PREPARATION' | 'SIGNOFF'
    source: str = ""            # 'auto' | 'manual' | 'trigger'


@dataclass
class RecordingEvent(BaseMsg):
    event: str = ""             # 'start' | 'end' | 'extend' | 'drop'
    label: str = ""
    filepath: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class TelegramStatus(BaseMsg):
    event: str = ""             # 'sent' | 'failed' | 'retry' | 'worker_dead' | 'worker_restart'
    message: Optional[str] = None
    queue_size: int = 0


@dataclass
class StreamError(BaseMsg):
    source: str = ""            # 'video' | 'audio'
    message: str = ""
    retry_count: int = 0


@dataclass
class DetectionReady(BaseMsg):
    """Detection 기동 완료 신호 — 최초 기동 및 재spawn 직후 각 1회 발행. drop 금지."""
    pid: int = 0
    config_loaded: bool = False
    roi_count: int = 0
    version: str = ""


@dataclass
class DetectionCrashed(BaseMsg):
    """Detection 비정상 종료 감지 — Watchdog이 재spawn 직전 발행. drop 금지."""
    dead_pid: int = 0
    reason: str = ""   # 'process_dead' | 'heartbeat_stale'
    stale_sec: float = 0.0   # heartbeat stale 시간 (reason='heartbeat_stale'일 때)


@dataclass
class PerfMeasurement(BaseMsg):
    recommended_interval: int = 200
    recommended_scale: float = 1.0
    cpu_percent: float = 0.0
    ram_percent: float = 0.0


# ──────────────────────────────────────────────
# cmd_queue (UI → Detection, maxsize=50)
# ──────────────────────────────────────────────

@dataclass
class ApplyConfig(BaseMsg):
    config: dict = field(default_factory=dict)
    reason: str = "user_save"   # 'user_save' | 'auto_perf' | 'restore'


@dataclass
class UpdateROIs(BaseMsg):
    rois: list = field(default_factory=list)    # list[dict]


@dataclass
class SetDetectionEnabled(BaseMsg):
    enabled: bool = True


@dataclass
class SetVolume(BaseMsg):
    volume: int = 80            # 0~100


@dataclass
class SetMute(BaseMsg):
    muted: bool = False


@dataclass
class SetSignoffState(BaseMsg):
    group_id: int = 1
    new_state: str = ""


@dataclass
class PauseForRoiEdit(BaseMsg):
    paused: bool = False


@dataclass
class ClearAlarms(BaseMsg):
    pass


@dataclass
class RequestAutoPerf(BaseMsg):
    duration_sec: float = 10.0


@dataclass
class RequestSnapshot(BaseMsg):
    pass


@dataclass
class Shutdown(BaseMsg):
    """정상 종료 신호 — drop 금지."""
    reason: str = "user"


# ──────────────────────────────────────────────
# 편의 export 목록 (ipc/__init__.py 용)
# ──────────────────────────────────────────────

RESULT_MESSAGES = (
    DetectionResult, AlarmTrigger, AlarmResolve, LogEntry, DiagSnapshot,
    SignoffStateChange, RecordingEvent, TelegramStatus, StreamError,
    DetectionReady, DetectionCrashed, PerfMeasurement,
)

CMD_MESSAGES = (
    ApplyConfig, UpdateROIs, SetDetectionEnabled, SetVolume, SetMute,
    SetSignoffState, PauseForRoiEdit, ClearAlarms, RequestAutoPerf,
    RequestSnapshot, Shutdown,
)

ALL_MESSAGES = RESULT_MESSAGES + CMD_MESSAGES
