"""
텔레그램 알림 워커
알림 발생 시 Bot API를 통해 메시지/이미지를 비동기 전송.
내부 큐 + daemon 스레드로 처리. PySide6 임포트 없음.
result_queue에 TelegramStatus 메시지 발행.
"""
import threading
import queue
import time
import datetime

import cv2
import numpy as np

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

_SEND_RETRY_COUNT = 2
_SEND_RETRY_DELAY = 5.0


class TelegramWorker:
    """
    텔레그램 Bot API 클라이언트.
    내부 큐 + daemon 스레드로 HTTP 전송 — notify() 호출 즉시 반환.
    result_queue: TelegramStatus / LogEntry 발행.
    """

    _API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(self, result_queue=None):
        self._result_queue = result_queue
        self._enabled: bool = False
        self._bot_token: str = ""
        self._chat_id: str = ""
        self._send_image: bool = True
        self._cooldown: float = 60.0
        self._notify_flags: dict = {
            "블랙": True, "스틸": True, "오디오": True,
            "무음": True, "정파": True,
        }
        self._last_sent: dict = {}

        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._running: bool = False
        self._worker_lock = threading.Lock()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="TelegramWorker"
        )
        self._consecutive_failures: int = 0
        self._reset_failure_count: bool = False

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

    def _log(self, message: str, error: bool = False):
        from ipc.messages import LogEntry, TelegramStatus
        level = "error" if error else "info"
        self._emit(LogEntry(level=level, source="telegram", message=message))

    # ── 생명주기 ──────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        try:
            self._worker_thread.start()
        except OSError as e:
            self._log(f"TelegramWorker 스레드 시작 실패: {e}", error=True)

    def ensure_worker_alive(self):
        if self._running and not self._worker_thread.is_alive():
            with self._worker_lock:
                if not self._worker_thread.is_alive():
                    from ipc.messages import TelegramStatus
                    self._log("워커 스레드 비정상 종료 감지 — 재시작", error=True)
                    self._emit(TelegramStatus(event="worker_restart",
                                              queue_size=self._queue.qsize()))
                    self._worker_thread = threading.Thread(
                        target=self._worker_loop, daemon=True, name="TelegramWorker"
                    )
                    self._worker_thread.start()

    def stop(self):
        self._running = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        with self._worker_lock:
            t = self._worker_thread
        t.join(timeout=5.0)

    # ── 설정 ──────────────────────────────────────────────────────────────────

    def configure(
        self,
        enabled: bool,
        bot_token: str,
        chat_id: str,
        send_image: bool,
        cooldown: float,
        notify_black: bool = True,
        notify_still: bool = True,
        notify_audio_level: bool = True,
        notify_embedded: bool = True,
        notify_signoff: bool = True,
    ):
        self._enabled = enabled
        self._bot_token = bot_token.strip()
        self._chat_id = chat_id.strip()
        self._send_image = send_image
        self._cooldown = max(0.0, cooldown)
        self._notify_flags = {
            "블랙": notify_black,
            "스틸": notify_still,
            "오디오": notify_audio_level,
            "무음": notify_embedded,
            "정파": notify_signoff,
        }
        self._reset_failure_count = True

    # ── 알림 발생 ─────────────────────────────────────────────────────────────

    def notify(
        self,
        alarm_type: str,
        label: str,
        media_name: str,
        frame: np.ndarray = None,
        is_recovery: bool = False,
        jpeg_bytes: bytes = None,
    ):
        """알림 큐에 삽입 (메인 루프에서 호출). 즉시 반환.

        jpeg_bytes가 주어지면 frame 재인코딩 없이 그대로 사용 (이중 인코딩 방지).
        """
        if not _REQUESTS_AVAILABLE:
            self._log("requests 미설치 — pip install requests", error=True)
            return
        if not self._enabled:
            return
        self.ensure_worker_alive()
        if not self._bot_token or not self._chat_id:
            self._log("Bot Token 또는 Chat ID 미설정", error=True)
            return
        if not self._notify_flags.get(alarm_type, True):
            return

        if not is_recovery:
            key = f"{alarm_type}_{label}"
            now = time.time()
            cutoff = now - 86400
            for k in list(self._last_sent.keys()):
                if self._last_sent[k] < cutoff:
                    del self._last_sent[k]
            if now - self._last_sent.get(key, 0.0) < self._cooldown:
                return
            self._last_sent[key] = now

        if self._send_image:
            if jpeg_bytes is None and frame is not None:
                try:
                    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ok:
                        jpeg_bytes = buf.tobytes()
                except Exception:
                    pass

        item = {
            "alarm_type": alarm_type,
            "label": label,
            "media_name": media_name or label,
            "jpeg_bytes": jpeg_bytes,
            "is_recovery": is_recovery,
        }
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._log(f"알림 큐 가득참 — {alarm_type} {label} 손실", error=True)

    def notify_system(self, message: str):
        """[SYSTEM] prefix 시스템 이벤트 알림 (Watchdog/main에서도 직접 HTTP 발송 가능)."""
        if not self._enabled or not self._bot_token or not self._chat_id:
            return
        item = {"_system": True, "message": message}
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            pass

    def notify_signoff(
        self,
        group_name: str,
        is_entry: bool,
        trigger_label: str,
        trigger_media: str,
        suppressed_labels: list,
        elapsed_sec: float = 0.0,
    ):
        """정파 진입/해제 알림. 쿨다운 없이 즉시 발송."""
        if not _REQUESTS_AVAILABLE or not self._enabled:
            return
        if not self._notify_flags.get("정파", True):
            return
        self.ensure_worker_alive()
        if not self._bot_token or not self._chat_id:
            return
        item = {
            "_signoff": True,
            "group_name": group_name,
            "is_entry": is_entry,
            "trigger_label": trigger_label,
            "trigger_media": trigger_media,
            "suppressed_labels": list(suppressed_labels),
            "elapsed_sec": elapsed_sec,
        }
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._log(f"알림 큐 가득참 — 정파 {'진입' if is_entry else '해제'} 손실", error=True)

    # ── 연결 테스트 ───────────────────────────────────────────────────────────

    def test_connection(self, token: str, chat_id: str) -> tuple:
        if not _REQUESTS_AVAILABLE:
            return False, "requests 라이브러리가 설치되지 않았습니다."
        token = token.strip()
        chat_id = chat_id.strip()
        if not token or not chat_id:
            return False, "Bot Token과 Chat ID를 입력하세요."
        try:
            url = f"{self._API_BASE.format(token=token)}/sendMessage"
            resp = _requests.post(
                url,
                json={"chat_id": chat_id, "text": "[KBS On-Air Monitoring] 텔레그램 연결 테스트 성공"},
                timeout=(5.0, 10.0),
            )
            if resp.status_code == 200:
                return True, "연결 테스트 성공"
            return False, f"오류 {resp.status_code}: {resp.text[:120]}"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    # ── 워커 스레드 ───────────────────────────────────────────────────────────

    def _worker_loop(self):
        while self._running:
            if self._reset_failure_count:
                self._consecutive_failures = 0
                self._reset_failure_count = False
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if item is None:
                break
            try:
                success = self._send(item)
                if success:
                    self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                self._log_with_suppression(
                    f"전송 처리 중 예외: {type(exc).__name__}: {exc}")

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if _REQUESTS_AVAILABLE:
            if isinstance(exc, _requests.exceptions.ConnectionError):
                return "네트워크 차단"
            if isinstance(exc, _requests.exceptions.Timeout):
                return "응답 시간 초과"
        return type(exc).__name__

    def _log_with_suppression(self, msg: str):
        n = self._consecutive_failures
        if n <= 3 or n % 10 == 0:
            self._log(msg, error=True)
        else:
            self._log(msg, error=False)

    def _send(self, item: dict) -> bool:
        if not _REQUESTS_AVAILABLE:
            return False

        # 정파 진입/해제 메시지
        if item.get("_signoff"):
            return self._send_signoff(item)

        # 시스템 메시지 (단순 텍스트)
        if item.get("_system"):
            base = self._API_BASE.format(token=self._bot_token)
            try:
                resp = _requests.post(
                    f"{base}/sendMessage",
                    json={"chat_id": self._chat_id, "text": item["message"]},
                    timeout=(5.0, 15.0),
                )
                return resp.status_code == 200
            except Exception:
                return False

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alarm_type = item["alarm_type"]
        label = item["label"]
        media_name = item["media_name"]
        is_recovery = item.get("is_recovery", False)

        channel_str = f"{label}"
        if media_name != label:
            channel_str += f" ({media_name})"

        if is_recovery:
            text = (
                f"[KBS On-Air Monitoring \U00002705 복구]\n"
                f"\U000023F0 시각: {now_str}\n"
                f"\U0001F4E1 채널: {channel_str}\n"
                f"\U00002714 복구: {alarm_type} 정상"
            )
        else:
            text = (
                f"[KBS On-Air Monitoring \U0001F6A8 알림]\n"
                f"\U000023F0 시각: {now_str}\n"
                f"\U0001F4E1 채널: {channel_str}\n"
                f"\U000026A0 감지: {alarm_type}"
            )

        base = self._API_BASE.format(token=self._bot_token)
        timeout = (5.0, 15.0)

        from ipc.messages import TelegramStatus
        for attempt in range(1 + _SEND_RETRY_COUNT):
            try:
                if item.get("jpeg_bytes"):
                    resp = _requests.post(
                        f"{base}/sendPhoto",
                        data={"chat_id": self._chat_id, "caption": text},
                        files={"photo": ("snapshot.jpg", item["jpeg_bytes"], "image/jpeg")},
                        timeout=timeout,
                    )
                else:
                    resp = _requests.post(
                        f"{base}/sendMessage",
                        json={"chat_id": self._chat_id, "text": text},
                        timeout=timeout,
                    )
                if resp.status_code == 200:
                    kind = "복구" if is_recovery else "알림"
                    self._log(f"{alarm_type} {kind} 전송 완료 ({channel_str})")
                    self._emit(TelegramStatus(event="sent",
                                              message=f"{alarm_type} {kind} ({channel_str})",
                                              queue_size=self._queue.qsize()))
                    return True
                elif resp.status_code == 429:
                    try:
                        retry_after = int(resp.json()["parameters"]["retry_after"])
                    except Exception:
                        retry_after = 10
                    # 최대 30초로 제한 — 긴 블로킹은 큐 손실을 유발함
                    sleep_sec = min(retry_after + 1, 30)
                    self._log(f"Rate Limit(429) — {sleep_sec}초 대기 후 재시도", error=True)
                    self._emit(TelegramStatus(event="retry", queue_size=self._queue.qsize()))
                    time.sleep(sleep_sec)
                    # attempt 소진 여부 체크 (무한루프 방지)
                    if attempt >= _SEND_RETRY_COUNT:
                        self._consecutive_failures += 1
                        self._log_with_suppression("전송 실패 (Rate Limit 재시도 소진)")
                        return False
                    continue
                else:
                    self._consecutive_failures += 1
                    self._log_with_suppression(f"전송 실패 {resp.status_code}: {resp.text[:120]}")
                    self._emit(TelegramStatus(event="failed", queue_size=self._queue.qsize()))
                    return False
            except Exception as exc:
                error_desc = self._classify_error(exc)
                if attempt < _SEND_RETRY_COUNT:
                    self._emit(TelegramStatus(event="retry", queue_size=self._queue.qsize()))
                    time.sleep(_SEND_RETRY_DELAY)
                else:
                    self._consecutive_failures += 1
                    self._log_with_suppression(f"전송 실패 (재시도 소진): {error_desc} — {exc}")
                    self._emit(TelegramStatus(event="failed", queue_size=self._queue.qsize()))
                    return False
        self._consecutive_failures += 1
        self._log_with_suppression("전송 실패 (재시도 횟수 소진)")
        return False

    def _send_signoff(self, item: dict) -> bool:
        """정파 진입/해제 텍스트 메시지 발송."""
        if not _REQUESTS_AVAILABLE:
            return False
        from ipc.messages import TelegramStatus
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        group_name = item["group_name"]
        is_entry = item["is_entry"]
        trigger_label = item["trigger_label"]
        trigger_media = item.get("trigger_media", "")
        suppressed_labels = item.get("suppressed_labels", [])
        elapsed_sec = item.get("elapsed_sec", 0.0)

        trigger_str = trigger_label
        if trigger_media and trigger_media != trigger_label:
            trigger_str += f" ({trigger_media})"

        suppressed_str = ", ".join(suppressed_labels) if suppressed_labels else "-"
        suppressed_count = len(suppressed_labels)

        if is_entry:
            text = (
                f"[KBS On-Air Monitoring \U0001F534 정파]\n"
                f"\U000023F0 시각: {now_str}\n"
                f"\U0001F4CB 그룹: {group_name}\n"
                f"\U0001F3AF 진입 트리거: {trigger_str}\n"
                f"\U0001F515 알림 억제: {suppressed_str} ({suppressed_count}개 채널)"
            )
            log_kind = "정파 진입"
        else:
            minutes = int(elapsed_sec) // 60
            seconds = int(elapsed_sec) % 60
            text = (
                f"[KBS On-Air Monitoring \U00002705 정파 해제]\n"
                f"\U000023F0 시각: {now_str}\n"
                f"\U0001F4CB 그룹: {group_name}\n"
                f"\U0001F3AF 진입 트리거: {trigger_str}\n"
                f"\U0001F515 알림 억제: {suppressed_str} ({suppressed_count}개 채널)\n"
                f"\U000023F1 정파 시간: {minutes}분 {seconds:02d}초"
            )
            log_kind = "정파 해제"

        base = self._API_BASE.format(token=self._bot_token)
        try:
            resp = _requests.post(
                f"{base}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
                timeout=(5.0, 15.0),
            )
            if resp.status_code == 200:
                self._log(f"{log_kind} 알림 전송 완료 ({group_name})")
                self._emit(TelegramStatus(event="sent",
                                          message=f"{log_kind} ({group_name})",
                                          queue_size=self._queue.qsize()))
                return True
            else:
                self._consecutive_failures += 1
                self._log_with_suppression(f"{log_kind} 전송 실패 {resp.status_code}: {resp.text[:120]}")
                return False
        except Exception as exc:
            self._consecutive_failures += 1
            self._log_with_suppression(f"{log_kind} 전송 실패: {self._classify_error(exc)} — {exc}")
            return False
