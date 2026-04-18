"""
비디오 캡처 워커
v1 core/video_capture.py에서 QThread/Signal/QMutex 제거.
프레임을 SharedFrameBuffer에 직접 write.
PySide6 임포트 없음.
"""
import threading
import time
import logging

import cv2
import numpy as np

_log = logging.getLogger(__name__)


class VideoCaptureWorker(threading.Thread):
    """
    OpenCV 영상 캡처를 별도 스레드에서 실행.
    프레임은 shared_frame.write_frame()으로 SharedMemory에 직접 기록.
    상태 이벤트는 result_queue에 LogEntry / StreamError 발행.
    """

    def __init__(self, shared_frame, result_queue, port: int = 0):
        super().__init__(daemon=True, name="VideoCaptureWorker")
        self._shared_frame = shared_frame
        self._result_queue = result_queue
        self._port = port
        self._video_file: str = ""
        self._reconnect = False
        self._running = False
        self._lock = threading.Lock()
        self._target_fps = 30
        # 외부에서 구독할 수 있는 콜백 (frame 수신 시 호출, optional)
        self.on_frame = None      # callable(np.ndarray) — AutoRecorder.push_frame 등

    def set_port(self, port: int):
        with self._lock:
            self._port = port
            self._video_file = ""
            self._reconnect = True

    def set_video_file(self, path: str):
        with self._lock:
            self._video_file = path
            self._reconnect = True

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

    def run(self):
        from ipc.messages import LogEntry, StreamError
        self._running = True
        cap = None
        was_connected = False
        consecutive_failures = 0
        frame_count = 0
        max_failures = 30
        source_name = ""

        while self._running:
            try:
                with self._lock:
                    current_port = self._port
                    current_file = self._video_file
                    reconnect = self._reconnect
                    if reconnect:
                        self._reconnect = False

                if reconnect and cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    was_connected = False
                    consecutive_failures = 0
                    frame_count = 0

                if cap is None:
                    if current_file:
                        cap = cv2.VideoCapture(current_file)
                        source_name = f"파일: {current_file}"
                    else:
                        cap = cv2.VideoCapture(current_port, cv2.CAP_DSHOW)
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                        cap.set(cv2.CAP_PROP_FPS, self._target_fps)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        source_name = f"포트 {current_port}"

                    if cap.isOpened():
                        was_connected = True
                        consecutive_failures = 0
                        self._emit(LogEntry(level="info", source="video",
                                            message=f"{source_name} 연결 성공"))
                    else:
                        if was_connected:
                            was_connected = False
                            self._emit(StreamError(source="video",
                                                   message=f"{source_name} 연결 실패",
                                                   retry_count=0))
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                        time.sleep(1.0)
                        continue

                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    consecutive_failures = 0
                    frame_count += 1
                    if frame_count % 500 == 0:
                        _log.debug("VIDEO-HB source=%s frames=%d", source_name, frame_count)

                    # SharedMemory에 프레임 기록
                    if self._shared_frame is not None:
                        try:
                            self._shared_frame.write_frame(frame)
                        except Exception as e:
                            _log.error("SharedFrame write 오류: %s", e)

                    # AutoRecorder 등 콜백 호출
                    if self.on_frame is not None:
                        try:
                            self.on_frame(frame)
                        except Exception as e:
                            _log.error("on_frame 콜백 오류: %s", e)
                else:
                    if current_file and cap is not None:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    else:
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            try:
                                cap.release()
                            except Exception:
                                pass
                            cap = None
                            if was_connected:
                                was_connected = False
                                self._emit(StreamError(
                                    source="video",
                                    message=f"포트 {current_port} 신호 없음",
                                    retry_count=consecutive_failures,
                                ))

            except Exception as e:
                self._emit(StreamError(source="video", message=f"캡처 오류: {e}",
                                       retry_count=consecutive_failures))
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                if was_connected:
                    was_connected = False
                consecutive_failures = 0
                time.sleep(1.0)
                continue

            time.sleep(1.0 / self._target_fps)

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
