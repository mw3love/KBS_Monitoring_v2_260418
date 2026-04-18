"""
알림 시스템
v1 core/alarm.py에서 임포트 경로 수정. UI 프로세스 전용.
QObject/Signal/QTimer 유지 (UI 프로세스에서만 사용).
Ack 상태 관리: acknowledge_all() — 소리/깜빡임 중단, 재감지 시 재발화.
"""
import logging
import os
import sys
import time
import wave
import threading
import numpy as np

_log = logging.getLogger(__name__)
from PySide6.QtCore import QObject, Signal, QTimer

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False


class AlarmSystem(QObject):
    """알림 시스템: 소리 반복 재생 및 시각적 알림 신호 발송"""

    visual_blink = Signal(bool)    # True=빨간 깜박임 ON, False=OFF
    alarm_triggered = Signal(str)  # 알림 발생 (알림 타입)

    DEFAULT_WINDOWS_SOUND = "SystemHand"

    def __init__(self, sounds_dir: str = "resources/sounds", parent=None):
        super().__init__(parent)
        self._sounds_dir = sounds_dir
        self._sound_files: dict = {}
        self._sound_enabled = True
        self._volume = 0.8
        self._blink_timer = QTimer(self)
        self._blink_state = False
        self._active_alarms: set = set()
        self._sound_thread: threading.Thread = None
        self._stop_sound = threading.Event()
        self._logger = None

        self._acknowledged_alarms: set = set()

        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.setInterval(500)

    def set_logger(self, logger):
        self._logger = logger

    def _log(self, msg: str):
        if self._logger:
            self._logger.warning(msg)
        else:
            print(f"[AlarmSystem] {msg}", file=sys.stderr)

    def trigger(self, alarm_type: str, label: str, alarm_duration: float = 0.0):
        """알림 발생. 이미 acknowledged된 알람은 소리/깜빡임 재활성화 안 함."""
        key = f"{alarm_type}_{label}"
        is_new = key not in self._active_alarms
        self._active_alarms.add(key)

        if key in self._acknowledged_alarms:
            return

        if is_new:
            self.alarm_triggered.emit(f"{label} {alarm_type} 감지")
            self._play_sound(alarm_type, alarm_duration)

        if not self._blink_timer.isActive():
            self._blink_timer.start()

    def resolve(self, alarm_type: str, label: str):
        """알림 해제"""
        key = f"{alarm_type}_{label}"
        was_active = key in self._active_alarms
        self._active_alarms.discard(key)
        self._acknowledged_alarms.discard(key)

        if was_active and not self._active_alarms:
            self._stop_playback()
            self._blink_timer.stop()
            self._blink_state = False
            self.visual_blink.emit(False)

    def resolve_all(self):
        """모든 알림 강제 해제"""
        self._active_alarms.clear()
        self._acknowledged_alarms.clear()
        self._stop_playback()
        self._blink_timer.stop()
        self._blink_state = False
        self.visual_blink.emit(False)

    def acknowledge_all(self):
        """알림확인 — 소리·깜빡임 해제. 감지 상태는 유지. 재감지 시 재발화."""
        self._acknowledged_alarms = set(self._active_alarms)
        self._stop_playback()
        self._blink_timer.stop()
        self._blink_state = False
        self.visual_blink.emit(False)

    def _stop_playback(self):
        self._stop_sound.set()
        if SOUNDDEVICE_AVAILABLE:
            try:
                sd.stop()
            except Exception:
                pass
        if WINSOUND_AVAILABLE:
            try:
                winsound.PlaySound(None, winsound.SND_ASYNC)
            except Exception:
                pass

    def set_sound_enabled(self, enabled: bool):
        self._sound_enabled = enabled
        if not enabled:
            self._stop_playback()
        elif self._active_alarms:
            self._play_sound("default")

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))

    def set_sounds_dir(self, path: str):
        self._sounds_dir = path

    def set_sound_file(self, alarm_type: str, path: str):
        self._sound_files[alarm_type] = path

    def get_sound_files(self) -> dict:
        return dict(self._sound_files)

    def play_test_sound(self, file_path: str):
        """테스트용 알림음 1회 재생."""
        raw_path = file_path
        sound_file = None
        if raw_path:
            abs_path = os.path.abspath(raw_path)
            if os.path.exists(abs_path):
                sound_file = abs_path
            else:
                self._log("파일 없음 → Windows 내장음으로 대체")

        self._stop_playback()
        if self._sound_thread and self._sound_thread.is_alive():
            self._sound_thread.join(timeout=1.5)
        self._stop_sound = threading.Event()
        self._sound_thread = threading.Thread(
            target=self._play_test_worker,
            args=(sound_file,),
            daemon=True,
        )
        try:
            self._sound_thread.start()
        except OSError as e:
            _log.error("테스트 사운드 스레드 시작 실패: %s", e)

    def _play_test_worker(self, sound_file):
        if sound_file and WINSOUND_AVAILABLE:
            try:
                winsound.PlaySound(sound_file,
                                   winsound.SND_FILENAME | winsound.SND_SYNC)
                return
            except Exception:
                pass

        if sound_file and SOUNDDEVICE_AVAILABLE:
            try:
                with wave.open(sound_file, "rb") as wf:
                    sampwidth = wf.getsampwidth()
                    samplerate = wf.getframerate()
                    n_channels = wf.getnchannels()
                    raw_data = wf.readframes(wf.getnframes())
                vol = max(self._volume, 1e-6)
                if sampwidth == 1:
                    audio_raw = np.frombuffer(raw_data, dtype=np.uint8)
                    audio = np.clip(128 + (audio_raw.astype(np.float64) - 128) * vol,
                                    0, 255).astype(np.uint8)
                else:
                    dtype = {2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
                    audio_raw = np.frombuffer(raw_data, dtype=dtype)
                    audio = np.clip(audio_raw.astype(np.float64) * vol,
                                    np.iinfo(dtype).min, np.iinfo(dtype).max).astype(dtype)
                if n_channels > 1:
                    audio = audio.reshape(-1, n_channels)
                sd.play(audio, samplerate=samplerate)
                sd.wait()
                return
            except Exception:
                try:
                    sd.stop()
                except Exception:
                    pass

        if WINSOUND_AVAILABLE:
            try:
                winsound.PlaySound(self.DEFAULT_WINDOWS_SOUND,
                                   winsound.SND_ALIAS | winsound.SND_SYNC)
            except Exception:
                try:
                    winsound.MessageBeep(winsound.MB_ICONHAND)
                except Exception:
                    pass

    def _toggle_blink(self):
        self._blink_state = not self._blink_state
        self.visual_blink.emit(self._blink_state)

    def _play_sound(self, alarm_type: str, alarm_duration: float = 0.0):
        if not self._sound_enabled:
            return
        if self._sound_thread and self._sound_thread.is_alive():
            return
        if self._sound_thread is not None:
            try:
                self._sound_thread.join(timeout=0.5)
            except Exception:
                pass
        self._stop_sound = threading.Event()
        self._sound_thread = threading.Thread(
            target=self._play_sound_worker,
            args=("default", alarm_duration),
            daemon=True,
        )
        try:
            self._sound_thread.start()
        except OSError as e:
            _log.error("알림음 스레드 시작 실패: %s", e)

    def _get_sound_path(self):
        path = self._sound_files.get("default", "")
        if path and os.path.exists(path):
            return path
        for p in self._sound_files.values():
            if p and os.path.exists(p):
                return p
        return None

    def _play_windows_builtin(self):
        if not WINSOUND_AVAILABLE:
            return
        try:
            winsound.PlaySound(self.DEFAULT_WINDOWS_SOUND,
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass

    def _play_sound_worker(self, alarm_type: str, alarm_duration: float = 0.0):
        raw_file = self._get_sound_path()
        sound_file = os.path.abspath(raw_file) if raw_file else None
        start_time = time.time()

        if sound_file and WINSOUND_AVAILABLE:
            sound_duration = 2.0
            try:
                with wave.open(sound_file, "rb") as wf:
                    sound_duration = wf.getnframes() / wf.getframerate()
            except Exception:
                pass
            while not self._stop_sound.is_set():
                if alarm_duration > 0 and (time.time() - start_time) >= alarm_duration:
                    break
                try:
                    winsound.PlaySound(sound_file,
                                       winsound.SND_FILENAME | winsound.SND_ASYNC)
                except Exception:
                    break
                if self._stop_sound.wait(timeout=sound_duration + 0.05):
                    break
            try:
                winsound.PlaySound(None, winsound.SND_ASYNC)
            except Exception:
                pass
            return

        if sound_file and SOUNDDEVICE_AVAILABLE:
            try:
                with wave.open(sound_file, "rb") as wf:
                    sampwidth = wf.getsampwidth()
                    samplerate = wf.getframerate()
                    n_channels = wf.getnchannels()
                    raw_data = wf.readframes(wf.getnframes())
                if sampwidth == 1:
                    audio_raw = np.frombuffer(raw_data, dtype=np.uint8)
                    audio = np.clip(128 + (audio_raw.astype(np.float64) - 128) * self._volume,
                                    0, 255).astype(np.uint8)
                else:
                    dtype = {2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
                    audio_raw = np.frombuffer(raw_data, dtype=dtype)
                    audio = np.clip(audio_raw.astype(np.float64) * self._volume,
                                    np.iinfo(dtype).min, np.iinfo(dtype).max).astype(dtype)
                if n_channels > 1:
                    audio = audio.reshape(-1, n_channels)
                while not self._stop_sound.is_set():
                    if alarm_duration > 0 and (time.time() - start_time) >= alarm_duration:
                        break
                    sd.play(audio, samplerate=samplerate)
                    sd.wait()
                try:
                    sd.stop()
                except Exception:
                    pass
                return
            except Exception:
                try:
                    sd.stop()
                except Exception:
                    pass

        while not self._stop_sound.is_set():
            if alarm_duration > 0 and (time.time() - start_time) >= alarm_duration:
                break
            self._play_windows_builtin()
            if self._stop_sound.wait(timeout=2.0):
                break
        if WINSOUND_AVAILABLE:
            try:
                winsound.PlaySound(None, winsound.SND_ASYNC)
            except Exception:
                pass
