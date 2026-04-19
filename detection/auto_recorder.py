"""
자동 녹화 모듈
알림 발생 시 사고 전 N초 + 사고 후 M초를 지정 해상도/FPS로 MP4 자동 저장.
순환 버퍼(JPEG 압축)로 "사고 전" 구간 구현, 오래된 파일 자동 삭제.
오디오(임베디드)를 WAV로 동시 버퍼링하여 ffmpeg로 영상과 합성.
ffmpeg 미설치 시 영상만 저장(폴백).
PySide6 임포트 없음.
"""
import os
import subprocess
import threading
import time
import wave
import datetime
from collections import deque
from typing import Optional
import queue as _queue_module

import logging

import cv2
import numpy as np

_log = logging.getLogger(__name__)

_JPEG_QUALITY = 85
_MAX_RECORD_FRAMES = 9000  # 녹화 큐 최대 프레임 수 (30fps × 300초 = 5분 상한)

_AUDIO_SR    = 44100
_AUDIO_CH    = 2
_AUDIO_CHUNK = 1024


class AutoRecorder:
    """
    순환 버퍼 기반 자동 녹화기.
    - push_frame(): 프레임 수신마다 호출
    - push_audio(): 오디오 청크 수신마다 호출
    - trigger(): 알림 발생 시 호출
    result_queue: RecordingEvent 발행 (start/end/extend/drop)
    """

    def __init__(self, result_queue=None):
        self._result_queue = result_queue
        self._enabled: bool = False
        self._save_dir: str = "recordings"
        self._pre_seconds: float = 5.0
        self._post_seconds: float = 15.0
        self._max_keep_days: int = 7

        self._out_w: int = 960
        self._out_h: int = 540
        self._out_fps: int = 10
        self._buf_interval: float = 1.0 / self._out_fps

        maxlen = int(self._pre_seconds * self._out_fps) + 5
        self._buffer: deque = deque(maxlen=maxlen)
        self._buffer_lock = threading.Lock()
        self._last_buf_time: float = 0.0

        audio_maxlen = int(self._pre_seconds * _AUDIO_SR / _AUDIO_CHUNK) + 10
        self._audio_buffer: deque = deque(maxlen=audio_maxlen)
        self._audio_lock = threading.Lock()

        self._recording: bool = False
        self._record_end: float = 0.0
        self._record_queue: deque = deque()
        self._audio_record_queue: deque = deque()
        self._record_thread: Optional[threading.Thread] = None

        self._running: bool = False
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="RecorderCleanup"
        )

    def _emit(self, msg):
        """result_queue에 메시지 발행 (Full 시 드롭)."""
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

    # ── 생명주기 ──────────────────────────────────────────────────────────────

    def start(self):
        self._cleanup_orphan_temp_files()
        self._running = True
        self._cleanup_thread.start()

    def stop(self):
        self._running = False

    # ── 설정 ──────────────────────────────────────────────────────────────────

    def configure(
        self,
        enabled: bool,
        save_dir: str,
        pre_seconds: float,
        post_seconds: float,
        max_keep_days: int,
        output_width: int = 960,
        output_height: int = 540,
        output_fps: int = 10,
    ):
        self._enabled = enabled
        self._save_dir = save_dir or "recordings"
        self._pre_seconds = max(1.0, float(pre_seconds))
        self._post_seconds = max(1.0, float(post_seconds))
        self._max_keep_days = max(1, int(max_keep_days))
        self._out_w = max(160, int(output_width))
        self._out_h = max(90, int(output_height))
        self._out_fps = max(1, int(output_fps))
        self._buf_interval = 1.0 / self._out_fps

        new_maxlen = int(self._pre_seconds * self._out_fps) + 5
        with self._buffer_lock:
            old = list(self._buffer)[-new_maxlen:]
            self._buffer = deque(old, maxlen=new_maxlen)

        new_audio_maxlen = int(self._pre_seconds * _AUDIO_SR / _AUDIO_CHUNK) + 10
        with self._audio_lock:
            old_audio = list(self._audio_buffer)[-new_audio_maxlen:]
            self._audio_buffer = deque(old_audio, maxlen=new_audio_maxlen)

        # 버퍼 메모리 예산 로그 (JPEG 압축 기준 추정치 — 실제는 더 작음)
        frame_bytes_est = int(self._out_w * self._out_h * 3 * 0.07)  # JPEG ~7%
        pre_buf_mb = new_maxlen * frame_bytes_est / 1024 / 1024
        rec_buf_mb = _MAX_RECORD_FRAMES * frame_bytes_est / 1024 / 1024
        _log.info(
            "AutoRecorder configure: pre_buf=%d frames(~%.1f MB) "
            "rec_max=%d frames(~%.1f MB) fps=%d pre=%.1fs post=%.1fs",
            new_maxlen, pre_buf_mb, _MAX_RECORD_FRAMES, rec_buf_mb,
            self._out_fps, self._pre_seconds, self._post_seconds,
        )

    # ── 프레임/오디오 수신 ────────────────────────────────────────────────────

    def push_frame(self, frame: np.ndarray):
        if not self._enabled:
            return
        now = time.time()
        if now - self._last_buf_time >= self._buf_interval:
            self._last_buf_time = now
            try:
                small = cv2.resize(frame, (self._out_w, self._out_h))
                ok, buf = cv2.imencode(".jpg", small,
                                       [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
                if ok:
                    with self._buffer_lock:
                        self._buffer.append((now, buf.tobytes()))
            except Exception:
                pass

        if self._recording:
            if now < self._record_end and len(self._record_queue) < _MAX_RECORD_FRAMES:
                try:
                    small = cv2.resize(frame, (self._out_w, self._out_h))
                    self._record_queue.append((now, small))
                except Exception:
                    pass
            else:
                if len(self._record_queue) >= _MAX_RECORD_FRAMES:
                    _log.warning("녹화 큐 상한 도달 (%d프레임) — 녹화 강제 종료", _MAX_RECORD_FRAMES)
                    from ipc.messages import RecordingEvent, LogEntry
                    self._emit(RecordingEvent(event="drop", label="", reason="max_frames"))
                    self._emit(LogEntry(
                        level="error", source="recorder",
                        message=f"녹화 프레임 버퍼 상한 도달({_MAX_RECORD_FRAMES}프레임) — 녹화 강제 종료",
                    ))
                self._recording = False

    def push_audio(self, samples: np.ndarray, timestamp: float):
        if not self._enabled:
            return
        raw = samples.tobytes()
        with self._audio_lock:
            self._audio_buffer.append((timestamp, raw))
        if self._recording and timestamp < self._record_end:
            self._audio_record_queue.append((timestamp, raw))

    # ── 알림 발생 트리거 ──────────────────────────────────────────────────────

    def trigger(self, alarm_type: str, label: str, media_name: str = ""):
        if not self._enabled:
            return
        now = time.time()
        new_end = now + self._post_seconds
        from ipc.messages import RecordingEvent

        if self._recording:
            if new_end > self._record_end:
                self._record_end = new_end
                self._emit(RecordingEvent(event="extend", label=label))
            return

        if self._record_thread is not None and self._record_thread.is_alive():
            _log.warning("이전 녹화 스레드 실행 중 — 새 녹화 스킵 (%s %s)", alarm_type, label)
            return

        self._recording = True
        self._record_end = new_end
        self._record_queue.clear()
        self._audio_record_queue.clear()

        with self._buffer_lock:
            pre_frames = list(self._buffer)
        with self._audio_lock:
            pre_audio = list(self._audio_buffer)

        os.makedirs(self._save_dir, exist_ok=True)
        now_dt = datetime.datetime.now()
        ts = now_dt.strftime("%Y%m%d_%H%M%S") + f"_{now_dt.microsecond // 1000:03d}"
        safe_label = label.replace("/", "_").replace("\\", "_")
        safe_media = (media_name.replace("/", "_").replace("\\", "_")
                      if media_name else "")
        safe_type = alarm_type.replace("/", "_")
        if safe_media:
            filename = f"{ts}_{safe_label}_{safe_media}_{safe_type}.mp4"
        else:
            filename = f"{ts}_{safe_label}_{safe_type}.mp4"
        filepath = os.path.join(self._save_dir, filename)

        self._emit(RecordingEvent(event="start", label=label, filepath=filepath))

        self._record_thread = threading.Thread(
            target=self._record_worker,
            args=(pre_frames, pre_audio, filepath, label),
            daemon=True,
            name="RecorderWriter",
        )
        self._record_thread.start()

    # ── 녹화 워커 ─────────────────────────────────────────────────────────────

    def _record_worker(self, pre_frames: list, pre_audio: list,
                       filepath: str, label: str):
        base = filepath[:-4] if filepath.endswith(".mp4") else filepath
        vtmp = base + "_vtmp.mp4"
        atmp = base + "_atmp.wav"

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(vtmp, fourcc, self._out_fps,
                                 (self._out_w, self._out_h))
        if not writer.isOpened():
            return

        has_audio = False
        wav_file = None
        merged = False

        try:
            try:
                try:
                    wav_file = wave.open(atmp, "wb")
                    wav_file.setnchannels(_AUDIO_CH)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(_AUDIO_SR)
                except Exception:
                    wav_file = None

                for _ts, jpeg_bytes in pre_frames:
                    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                    frm = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frm is not None:
                        writer.write(frm)

                if wav_file is not None:
                    for _ts, raw in pre_audio:
                        wav_file.writeframes(raw)
                        has_audio = True

                while True:
                    while self._record_queue:
                        _ts, frm = self._record_queue.popleft()
                        writer.write(frm)
                    if wav_file is not None:
                        while self._audio_record_queue:
                            _ts, raw = self._audio_record_queue.popleft()
                            wav_file.writeframes(raw)
                            has_audio = True
                    if not self._recording:
                        while self._record_queue:
                            _ts, frm = self._record_queue.popleft()
                            writer.write(frm)
                        if wav_file is not None:
                            while self._audio_record_queue:
                                _ts, raw = self._audio_record_queue.popleft()
                                wav_file.writeframes(raw)
                                has_audio = True
                        break
                    else:
                        time.sleep(0.02)
            finally:
                writer.release()
                if wav_file is not None:
                    wav_file.close()

            if has_audio:
                v_start = pre_frames[0][0] if pre_frames else None
                a_start = pre_audio[0][0] if pre_audio else None
                audio_offset = (a_start - v_start) if (v_start and a_start) else 0.0
                merged = self._merge_with_ffmpeg(vtmp, atmp, filepath, audio_offset)

        finally:
            if merged:
                try:
                    os.remove(vtmp)
                except Exception:
                    pass
            else:
                try:
                    if os.path.exists(vtmp):
                        os.rename(vtmp, filepath)
                except Exception:
                    pass
            try:
                if os.path.exists(atmp):
                    os.remove(atmp)
            except Exception:
                pass

            from ipc.messages import RecordingEvent
            self._emit(RecordingEvent(event="end", label=label, filepath=filepath))

    # ── ffmpeg ────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_ffmpeg() -> str:
        import shutil
        if shutil.which("ffmpeg"):
            return "ffmpeg"
        dedicated = r"C:\KBS_Tools\ffmpeg.exe"
        if os.path.isfile(dedicated):
            return dedicated
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bundled = os.path.join(base_dir, "resources", "bin", "ffmpeg.exe")
        if os.path.isfile(bundled):
            return bundled
        return "ffmpeg"

    @staticmethod
    def _merge_with_ffmpeg(vtmp: str, atmp: str, output: str,
                           audio_offset: float = 0.0) -> bool:
        ffmpeg = AutoRecorder._find_ffmpeg()
        cmd = [ffmpeg, "-y", "-i", vtmp]
        if audio_offset > 0.05:
            cmd += ["-itsoffset", f"{audio_offset:.3f}"]
            cmd += ["-i", atmp]
        elif audio_offset < -0.05:
            cmd += ["-ss", f"{-audio_offset:.3f}", "-i", atmp]
        else:
            cmd += ["-i", atmp]
        cmd += ["-c:v", "copy", "-c:a", "aac",
                "-map", "0:v:0", "-map", "1:a:0", "-shortest", output]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return False

    # ── 자동 삭제 ─────────────────────────────────────────────────────────────

    def _cleanup_orphan_temp_files(self):
        if not os.path.isdir(self._save_dir):
            return
        try:
            for fname in os.listdir(self._save_dir):
                if fname.endswith("_vtmp.mp4") or fname.endswith("_atmp.wav"):
                    try:
                        os.remove(os.path.join(self._save_dir, fname))
                    except OSError:
                        pass
        except Exception:
            pass

    def _cleanup_loop(self):
        while self._running:
            self._delete_old_files()
            self._cleanup_orphan_temp_files()
            for _ in range(3600):
                if not self._running:
                    return
                time.sleep(1)

    def _delete_old_files(self):
        if not os.path.isdir(self._save_dir):
            return
        cutoff = time.time() - self._max_keep_days * 86400
        try:
            for fname in os.listdir(self._save_dir):
                if not fname.lower().endswith(".mp4"):
                    continue
                fpath = os.path.join(self._save_dir, fname)
                try:
                    if os.path.getmtime(fpath) < cutoff:
                        os.remove(fpath)
                except Exception:
                    pass
        except Exception:
            pass
