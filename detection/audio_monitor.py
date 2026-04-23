"""
임베디드 오디오 모니터링 워커
v1 core/audio_monitor.py에서 QThread/Signal 제거.
L/R 레벨은 SharedStateBuffer에 직접 기록.
pycaw 볼륨/Mute 제어: Detection 프로세스 전담.
PySide6 임포트 없음.
"""
import threading
import time
import math
import logging
import numpy as np

_log = logging.getLogger(__name__)

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False


class AudioMonitorWorker(threading.Thread):
    """
    오디오 레벨 모니터링 스레드.
    L/R dB 레벨을 shared_state.set_levels()로 SharedMemory에 기록.
    무음 이벤트: on_silence_detected 콜백(float 초).
    오디오 청크: on_audio_chunk 콜백(np.ndarray int16, float timestamp).
    """

    CHUNK = 1024
    SAMPLE_RATE = 44100
    CHANNELS = 2

    def __init__(self, shared_state, result_queue):
        super().__init__(daemon=True, name="AudioMonitorWorker")
        self._shared_state = shared_state
        self._result_queue = result_queue
        self._running = False
        self._silence_duration = 0.0
        self._muted = False
        self._volume = 1.0
        self._stereo = (self.CHANNELS == 2)
        self._lock = threading.Lock()
        self.silence_threshold_db = -50.0  # detection_process에서 config 값으로 주입

        # 외부 콜백
        self.on_silence_detected = None   # callable(float)
        self.on_audio_chunk = None        # callable(np.ndarray, float)

    def set_muted(self, muted: bool):
        with self._lock:
            self._muted = muted

    def set_volume(self, volume: float):
        with self._lock:
            self._volume = max(0.0, min(1.0, volume))

    def stop(self):
        self._running = False

    def _emit(self, msg):
        if self._result_queue is None:
            return
        try:
            self._result_queue.put_nowait(msg)
        except Exception:
            try:
                self._result_queue.get_nowait()
                self._result_queue.put_nowait(msg)
            except Exception:
                pass

    @staticmethod
    def _linear_to_db(linear: float) -> float:
        if linear <= 0:
            return -60.0
        db = 20 * math.log10(max(linear, 1e-10))
        return max(-60.0, min(0.0, db))

    def run(self):
        from ipc.messages import LogEntry, StreamError
        self._running = True

        if not SOUNDDEVICE_AVAILABLE:
            self._emit(LogEntry(level="info", source="audio",
                                message="sounddevice 없음 - 더미 신호로 동작"))
            while self._running:
                if self._shared_state is not None:
                    self._shared_state.set_levels(-60.0, -60.0)
                if self.on_silence_detected:
                    self._silence_duration += 0.5
                    try:
                        self.on_silence_detected(self._silence_duration)
                    except Exception:
                        pass
                time.sleep(0.5)
            return

        device_index = None
        self._emit(LogEntry(level="info", source="audio",
                            message="DIAG-AUDIO: 사용 장치=(시스템 기본)"))

        stream = None
        output_stream = None

        try:
            stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.CHUNK,
                device=device_index,
                channels=self.CHANNELS,
                dtype="int16",
            )
            stream.start()

            try:
                output_stream = sd.RawOutputStream(
                    samplerate=self.SAMPLE_RATE,
                    blocksize=self.CHUNK,
                    channels=self.CHANNELS,
                    dtype="int16",
                )
                output_stream.start()
                self._emit(LogEntry(level="info", source="audio",
                                    message="오디오 스트림 시작 (패스스루 활성)"))
            except Exception as e:
                output_stream = None
                self._emit(LogEntry(level="info", source="audio",
                                    message=f"오디오 스트림 시작 (출력 오류: {e})"))

            chunk_duration = self.CHUNK / self.SAMPLE_RATE
            consecutive_errors = 0
            _MAX_CONSECUTIVE_ERRORS = 10

            while self._running:
                try:
                    if stream is None:
                        raise RuntimeError("오디오 스트림 없음")
                    data, _ = stream.read(self.CHUNK)
                    consecutive_errors = 0
                    samples = np.frombuffer(data, dtype=np.int16)

                    # AutoRecorder 콜백
                    if self.on_audio_chunk is not None:
                        try:
                            self.on_audio_chunk(samples.copy(), time.time())
                        except Exception:
                            pass

                    # 패스스루
                    with self._lock:
                        muted = self._muted
                        volume = self._volume
                    if output_stream is not None and not muted and volume > 0:
                        if volume < 1.0:
                            out_f = samples.astype(np.float32) * volume
                            out_samples = np.clip(out_f, -32768, 32767).astype(np.int16)
                        else:
                            out_samples = samples
                        try:
                            output_stream.write(out_samples.tobytes())
                        except Exception:
                            pass

                    if self._stereo:
                        left = samples[0::2].astype(np.float32) / 32768.0
                        right = samples[1::2].astype(np.float32) / 32768.0
                    else:
                        left = right = samples.astype(np.float32) / 32768.0

                    l_rms = float(np.sqrt(np.mean(left ** 2))) if len(left) > 0 else 0.0
                    r_rms = float(np.sqrt(np.mean(right ** 2))) if len(right) > 0 else 0.0
                    l_db = self._linear_to_db(l_rms)
                    r_db = self._linear_to_db(r_rms)

                    # SharedMemory에 레벨 기록
                    if self._shared_state is not None:
                        try:
                            self._shared_state.set_levels(l_db, r_db)
                        except Exception:
                            pass

                    avg_db = (l_db + r_db) / 2.0
                    if avg_db <= self.silence_threshold_db:
                        self._silence_duration += chunk_duration
                        if self.on_silence_detected is not None:
                            try:
                                self.on_silence_detected(self._silence_duration)
                            except Exception:
                                pass
                    else:
                        self._silence_duration = 0.0

                except Exception as e:
                    consecutive_errors += 1
                    if self._shared_state is not None:
                        try:
                            self._shared_state.set_levels(-60.0, -60.0)
                        except Exception:
                            pass
                    _log.debug("오디오 루프 예외 (%d회): %s", consecutive_errors, e)

                    if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                        _log.warning("오디오 스트림 연속 실패 %d회 — 재연결", consecutive_errors)
                        self._emit(StreamError(source="audio",
                                               message="오디오 장치 오류 — 재연결 시도",
                                               retry_count=consecutive_errors))
                        try:
                            stream.stop(); stream.close()
                        except Exception:
                            pass
                        stream = None
                        if output_stream is not None:
                            try:
                                output_stream.stop(); output_stream.close()
                            except Exception:
                                pass
                            output_stream = None

                        time.sleep(3.0)
                        if not self._running:
                            return
                        try:
                            stream = sd.RawInputStream(
                                samplerate=self.SAMPLE_RATE,
                                blocksize=self.CHUNK,
                                device=device_index,
                                channels=self.CHANNELS,
                                dtype="int16",
                            )
                            stream.start()
                            try:
                                output_stream = sd.RawOutputStream(
                                    samplerate=self.SAMPLE_RATE,
                                    blocksize=self.CHUNK,
                                    channels=self.CHANNELS,
                                    dtype="int16",
                                )
                                output_stream.start()
                            except Exception:
                                output_stream = None
                            consecutive_errors = 0
                            self._silence_duration = 0.0
                            self._emit(LogEntry(level="info", source="audio",
                                                message="오디오 스트림 재연결 성공"))
                        except Exception as re_e:
                            self._emit(StreamError(source="audio",
                                                   message=f"오디오 재연결 실패: {re_e}",
                                                   retry_count=consecutive_errors))
                            time.sleep(5.0)
                            if not self._running:
                                return
                            consecutive_errors = 0

        except Exception as e:
            self._emit(StreamError(source="audio",
                                   message=f"오디오 스트림 오류: {e}", retry_count=0))
            while self._running:
                if self._shared_state is not None:
                    try:
                        self._shared_state.set_levels(-60.0, -60.0)
                    except Exception:
                        pass
                time.sleep(0.5)
        finally:
            if output_stream is not None:
                try:
                    output_stream.stop(); output_stream.close()
                except Exception:
                    pass
            if stream is not None:
                try:
                    stream.stop(); stream.close()
                except Exception:
                    pass


# ── pycaw 볼륨/Mute 제어 (Detection 프로세스 전담) ────────────────────────────

def set_system_volume(volume: int):
    """시스템 볼륨 설정 (0~100). pycaw 미설치 시 무시."""
    if not PYCAW_AVAILABLE:
        return
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        scalar = max(0.0, min(1.0, volume / 100.0))
        vol.SetMasterVolumeLevelScalar(scalar, None)
    except Exception as e:
        _log.error("시스템 볼륨 설정 오류: %s", e)


def set_system_mute(muted: bool):
    """시스템 음소거 설정. pycaw 미설치 시 무시."""
    if not PYCAW_AVAILABLE:
        return
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        vol.SetMute(int(muted), None)
    except Exception as e:
        _log.error("시스템 Mute 설정 오류: %s", e)
