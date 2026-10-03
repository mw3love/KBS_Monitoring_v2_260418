"""
알림음 지속시간(설정창 "알림음 지속(초)") 회귀 테스트.
배경: docs/261003_프로그램_종합점검.md F2 — 설정값이 AlarmSystem까지 전달되지 않아
알림음이 확인/복구 전까지 무제한으로 울렸다.
소리가 실제로 나지 않도록 무음 wav를 쓴다.
"""
import os
import sys
import time
import wave

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.alarm import AlarmSystem  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def alarm(app, tmp_path):
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 2000)   # 0.25초 무음
    a = AlarmSystem(sounds_dir=str(tmp_path))
    a.set_sound_file("default", str(wav_path))
    yield a
    a.resolve_all()


def _wait_stopped(alarm, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not (alarm._sound_thread and alarm._sound_thread.is_alive()):
            return True
        time.sleep(0.05)
    return False


def test_sound_stops_after_duration(alarm):
    alarm.trigger("black", "V1", 1.0)
    assert alarm._sound_thread.is_alive()
    assert _wait_stopped(alarm, 3.0), "지속시간이 지나도 알림음이 멈추지 않음"
    assert "black_V1" in alarm._active_alarms   # 알람 상태(깜빡임)는 유지


def test_zero_duration_plays_until_resolve(alarm):
    alarm.trigger("black", "V1", 0.0)
    time.sleep(1.5)
    assert alarm._sound_thread.is_alive(), "0(무제한)인데 알림음이 멈춤"
    alarm.resolve("black", "V1")
    assert _wait_stopped(alarm, 2.0)


def test_new_alarm_extends_sound(alarm):
    alarm.trigger("black", "V1", 1.0)
    time.sleep(0.6)
    alarm.trigger("still", "V2", 2.0)   # 재생 중 새 알람 → 종료 시각 연장
    time.sleep(0.8)                     # V1만 있었다면 이미 멈췄을 시점
    assert alarm._sound_thread.is_alive(), "새 알람이 알림음 시간을 늘리지 못함"
    assert _wait_stopped(alarm, 3.0)


@pytest.mark.parametrize("det_type", ["black", "still", "audio_level", "embedded"])
def test_main_window_passes_configured_duration(app, det_type):
    """MainWindow가 설정의 *_alarm_duration을 AlarmSystem.trigger로 넘기는지."""
    from unittest.mock import MagicMock
    from ipc.messages import AlarmTrigger
    from ui.main_window import MainWindow

    fake = MagicMock()
    fake._detection_enabled = True
    fake._active_alarm_roi = {}
    fake._cfg = {"detection": {f"{det_type}_alarm_duration": 42}}
    msg = AlarmTrigger(label="V1", detection_type=det_type, roi_type="video")
    MainWindow._on_alarm_trigger(fake, msg)
    fake._alarm.trigger.assert_called_once_with(det_type, "V1", 42.0)
