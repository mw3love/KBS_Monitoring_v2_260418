"""ipc 패키지 — 모든 메시지·SharedMemory 클래스 re-export"""
from .messages import (
    BaseMsg,
    AlarmTrigger, AlarmResolve, LogEntry, DiagSnapshot,
    SignoffStateChange, RecordingEvent, TelegramStatus, StreamError,
    DetectionReady,
    ApplyConfig, UpdateROIs, SetDetectionEnabled, SetVolume, SetMute,
    SetSignoffState, ClearAlarms, Shutdown,
    RESULT_MESSAGES, CMD_MESSAGES, ALL_MESSAGES,
)
from .shared_frame import SharedFrameBuffer, SHM_NAME as FRAME_SHM_NAME
from .shared_state import SharedStateBuffer, SHM_NAME as STATE_SHM_NAME

__all__ = [
    "BaseMsg",
    "AlarmTrigger", "AlarmResolve", "LogEntry",
    "DiagSnapshot", "SignoffStateChange", "RecordingEvent", "TelegramStatus",
    "StreamError", "DetectionReady",
    "ApplyConfig", "UpdateROIs", "SetDetectionEnabled", "SetVolume", "SetMute",
    "SetSignoffState", "ClearAlarms", "Shutdown",
    "RESULT_MESSAGES", "CMD_MESSAGES", "ALL_MESSAGES",
    "SharedFrameBuffer", "FRAME_SHM_NAME",
    "SharedStateBuffer", "STATE_SHM_NAME",
]
