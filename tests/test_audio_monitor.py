"""
AudioMonitorWorker 장치 열기 실패 처리 단위 테스트
2026-10-27 사고: 윈도우 마이크 권한 차단으로 장치 열기가 8시간 실패했는데
무음 경보·텔레그램이 하나도 없었다 → 실패 구간도 무음으로 누적 + 1회 통보.
"""
import sys
import os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import detection.audio_monitor as am


class _FakeClock:
    """sleep 하면 시계만 앞으로 가는 가짜 time 모듈."""

    def __init__(self):
        self.now = 1000.0

    def sleep(self, s):
        self.now += s

    def monotonic(self):
        return self.now

    def time(self):
        return self.now


class _OpenError(Exception):
    pass


class _FakeStream:
    def __init__(self, read_fail=False):
        self.read_fail = read_fail

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass

    def read(self, n):
        if self.read_fail:
            raise _OpenError("read fail")
        return np.zeros(n * 2, dtype=np.int16).tobytes(), False


class _FakeSD:
    """open_plan: RawInputStream 호출마다 꺼낼 결과 (Exception 또는 _FakeStream)."""

    def __init__(self, open_plan):
        self.open_plan = list(open_plan)

    def RawInputStream(self, **kw):
        item = self.open_plan.pop(0) if self.open_plan else _OpenError("MME error 1")
        if isinstance(item, Exception):
            raise item
        return item

    def RawOutputStream(self, **kw):
        raise _OpenError("no output")


def _make(monkeypatch, open_plan):
    clock = _FakeClock()
    monkeypatch.setattr(am, "time", clock)
    monkeypatch.setattr(am, "sd", _FakeSD(open_plan), raising=False)
    monkeypatch.setattr(am, "SOUNDDEVICE_AVAILABLE", True)
    w = am.AudioMonitorWorker(shared_state=None, result_queue=None)
    w._running = True
    rec = {"down": [], "up": [], "silence": []}
    w.on_device_down = lambda msg: rec["down"].append(msg)
    w.on_device_up = lambda sec: rec["up"].append(sec)
    return w, rec, clock


def test_open_failure_accumulates_silence_and_notifies_once(monkeypatch):
    """장치 열기가 계속 실패하면 무음이 쌓이고, 통보는 60초 뒤 딱 1번."""
    w, rec, _ = _make(monkeypatch, [])

    def _on_silence(sec):
        rec["silence"].append(sec)
        if sec >= 300:
            w.stop()
    w.on_silence_detected = _on_silence

    w.run()

    assert rec["silence"][-1] >= 300          # 무음 경보(기본 60초)에 충분히 도달
    assert len(rec["down"]) == 1               # 5분 실패에도 통보는 1회
    assert "MME error 1" in rec["down"][0]
    assert rec["up"] == []


def test_no_notify_for_short_outage(monkeypatch):
    """60초 안에 복구되면 장치 끊김/복구 통보 둘 다 없음."""
    w, rec, _ = _make(monkeypatch, [_OpenError("x")] * 3 + [_FakeStream()])
    w.on_device_up = lambda sec: (rec["up"].append(sec), w.stop())
    w.on_silence_detected = lambda sec: None

    # 복구 후 첫 read 에서 멈추게 한다
    orig = _FakeStream.read
    monkeypatch.setattr(_FakeStream, "read",
                        lambda self, n: (w.stop(), orig(self, n))[1])
    w.run()

    assert rec["down"] == []
    assert rec["up"] == []


def test_recovery_notifies_once_after_down(monkeypatch):
    """통보 후 장치가 다시 열리면 복구 통보 1회 (끊긴 시간 포함)."""
    w, rec, _ = _make(monkeypatch, [_OpenError("x")] * 20 + [_FakeStream()])
    w.on_silence_detected = lambda sec: None
    w.on_device_up = lambda sec: (rec["up"].append(sec), w.stop())

    w.run()

    assert len(rec["down"]) == 1
    assert len(rec["up"]) == 1
    assert rec["up"][0] >= w.DEVICE_DOWN_NOTIFY_SEC


def test_device_lost_midrun_goes_to_outer_retry(monkeypatch):
    """가동 중 장치가 죽고 재연결도 실패하면 외부 루프로 넘어가 무음이 쌓인다."""
    w, rec, _ = _make(monkeypatch, [_FakeStream(read_fail=True)])

    def _on_silence(sec):
        rec["silence"].append(sec)
        if sec >= 120:
            w.stop()
    w.on_silence_detected = _on_silence

    w.run()

    assert rec["silence"][-1] >= 120
    assert len(rec["down"]) == 1
