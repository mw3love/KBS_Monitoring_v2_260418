"""
IPC 스펙 정합성 테스트
docs_ipc_spec.md §2 표와 ipc/messages.py 의 dataclass·필드명 1:1 일치 자동 검증.

실행: python -m pytest tests/test_ipc_contract.py -v
      또는: python tests/test_ipc_contract.py
"""
import dataclasses
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ipc.messages as M

# ──────────────────────────────────────────────────────────────────────────────
# docs_ipc_spec.md §2.1 / §2.2 에 정의된 메시지 ↔ 필드 계약
# 이 표가 단일 진실 원천. 구현이 추가되면 이 표도 함께 갱신.
# ──────────────────────────────────────────────────────────────────────────────

RESULT_CONTRACT = {
    "DetectionResult": {"label", "roi_type", "media_name", "detection_type",
                        "active", "duration_sec", "meta"},
    "AlarmTrigger":    {"label", "detection_type", "roi_type", "snapshot_jpeg"},
    "AlarmResolve":    {"label", "detection_type", "duration_sec"},
    "LogEntry":        {"level", "source", "message"},
    "DiagSnapshot":    {"section", "payload"},
    "SignoffStateChange": {"group_id", "prev_state", "new_state", "source"},
    "RecordingEvent":  {"event", "label", "filepath", "reason"},
    "TelegramStatus":  {"event", "message", "queue_size"},
    "StreamError":     {"source", "message", "retry_count"},
    "DetectionReady":  {"pid", "config_loaded", "roi_count", "version"},
    "PerfMeasurement": {"recommended_interval", "recommended_scale",
                        "cpu_percent", "ram_percent"},
}

CMD_CONTRACT = {
    "ApplyConfig":           {"config", "reason"},
    "UpdateROIs":            {"rois"},
    "SetDetectionEnabled":   {"enabled"},
    "SetVolume":             {"volume"},
    "SetMute":               {"muted"},
    "SetSignoffState":       {"group_id", "new_state"},
    "PauseForRoiEdit":       {"paused"},
    "ClearAlarms":           set(),
    "RequestAutoPerf":       {"duration_sec"},
    "RequestSnapshot":       set(),
    "Shutdown":              {"reason"},
}

ALL_CONTRACT = {**RESULT_CONTRACT, **CMD_CONTRACT}


def _user_fields(cls) -> set:
    """BaseMsg 의 ts 를 제외한 사용자 정의 필드명 집합."""
    return {f.name for f in dataclasses.fields(cls) if f.name != "ts"}


def test_all_messages_exist():
    """스펙에 정의된 모든 메시지 클래스가 ipc.messages 에 존재하는지 검증."""
    missing = []
    for name in ALL_CONTRACT:
        if not hasattr(M, name):
            missing.append(name)
    assert not missing, f"ipc/messages.py 에 없는 메시지: {missing}"


def test_no_extra_messages():
    """ipc/messages.py 에 스펙에 없는 메시지가 추가되지 않았는지 검증."""
    extra = []
    for cls in M.ALL_MESSAGES:
        name = cls.__name__
        if name not in ALL_CONTRACT:
            extra.append(name)
    assert not extra, (
        f"docs_ipc_spec.md 에 없는 메시지가 ipc/messages.py 에 있음: {extra}\n"
        "추가 시 스펙 문서를 먼저 갱신하세요."
    )


def test_result_messages_tuple():
    """RESULT_MESSAGES 튜플이 스펙의 result_queue 메시지만 포함하는지."""
    expected = set(RESULT_CONTRACT.keys())
    actual = {cls.__name__ for cls in M.RESULT_MESSAGES}
    assert actual == expected, (
        f"RESULT_MESSAGES 불일치\n  스펙:  {sorted(expected)}\n  실제:  {sorted(actual)}"
    )


def test_cmd_messages_tuple():
    """CMD_MESSAGES 튜플이 스펙의 cmd_queue 메시지만 포함하는지."""
    expected = set(CMD_CONTRACT.keys())
    actual = {cls.__name__ for cls in M.CMD_MESSAGES}
    assert actual == expected, (
        f"CMD_MESSAGES 불일치\n  스펙:  {sorted(expected)}\n  실제:  {sorted(actual)}"
    )


def test_fields_match():
    """각 메시지의 필드명이 스펙과 정확히 일치하는지 검증."""
    errors = []
    for name, expected_fields in ALL_CONTRACT.items():
        cls = getattr(M, name, None)
        if cls is None:
            continue  # test_all_messages_exist 에서 이미 실패
        actual_fields = _user_fields(cls)
        missing = expected_fields - actual_fields
        extra = actual_fields - expected_fields
        if missing or extra:
            errors.append(
                f"{name}: 누락={sorted(missing) or '없음'}, 초과={sorted(extra) or '없음'}"
            )
    assert not errors, "필드 불일치:\n" + "\n".join(errors)


def test_base_msg_ts_present():
    """모든 메시지가 BaseMsg 를 상속해 ts 필드를 갖는지."""
    missing_ts = []
    for cls in M.ALL_MESSAGES:
        if not any(f.name == "ts" for f in dataclasses.fields(cls)):
            missing_ts.append(cls.__name__)
    assert not missing_ts, f"ts 필드 없는 메시지: {missing_ts}"


def test_shared_memory_classes_importable():
    """SharedFrameBuffer / SharedStateBuffer 가 import 가능한지."""
    from ipc.shared_frame import SharedFrameBuffer, TOTAL_SIZE as FRAME_SIZE
    from ipc.shared_state import SharedStateBuffer, TOTAL_SIZE as STATE_SIZE
    assert FRAME_SIZE == 6_220_832, f"frame SHM 크기 불일치: {FRAME_SIZE}"
    assert STATE_SIZE == 64, f"state SHM 크기 불일치: {STATE_SIZE}"


# ──────────────────────────────────────────────────────────────────────────────
# 직접 실행 지원 (pytest 없이도 동작)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_all_messages_exist,
        test_no_extra_messages,
        test_result_messages_tuple,
        test_cmd_messages_tuple,
        test_fields_match,
        test_base_msg_ts_present,
        test_shared_memory_classes_importable,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}\n        {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}\n        {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(0 if failed == 0 else 1)
