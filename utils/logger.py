"""
로깅 모듈
일별 로그 파일: logs/YYYYMMDD_{suffix}.txt (날짜 변경 시 자동 로테이션)
PySide6 의존 없음 — Detection/Watchdog 프로세스에서도 사용 가능.
UI 프로세스는 result_queue LogEntry 메시지를 통해 로그 위젯에 통합 표시.
"""
import logging
import os
import datetime


class AppLogger:
    """파일 전용 로거. suffix로 프로세스별 파일 분리(_detection/_ui/_watchdog)."""

    LOG_DIR = "logs"

    def __init__(self, suffix: str = ""):
        """
        suffix: '_detection' | '_ui' | '_watchdog' | '' (빈 문자열=레거시)
        """
        self._suffix = suffix
        os.makedirs(self.LOG_DIR, exist_ok=True)
        self._current_date: str = ""
        logger_name = f"kbs_monitor{suffix}"
        self._file_logger = logging.getLogger(logger_name)
        self._file_logger.setLevel(logging.DEBUG)
        self._file_logger.propagate = False
        self._rotate_if_needed()

    def _rotate_if_needed(self):
        """날짜가 바뀌면 새 로그 파일로 교체"""
        today = datetime.date.today().strftime("%Y%m%d")
        if today == self._current_date:
            return

        for h in list(self._file_logger.handlers):
            h.close()
            self._file_logger.removeHandler(h)

        log_path = os.path.join(self.LOG_DIR, f"{today}{self._suffix}.txt")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        self._file_logger.addHandler(handler)
        self._current_date = today

    def info(self, message: str):
        self._rotate_if_needed()
        self._file_logger.info(message)

    def warning(self, message: str):
        self._rotate_if_needed()
        self._file_logger.warning(message)

    def error(self, message: str):
        self._rotate_if_needed()
        self._file_logger.error(message)

    def debug(self, message: str):
        self._rotate_if_needed()
        self._file_logger.debug(message)

    def file_only(self, message: str):
        """파일에만 기록 (텔레그램 전송 로그 등)"""
        self._rotate_if_needed()
        self._file_logger.info(message)
