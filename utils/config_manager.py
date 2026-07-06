"""
설정 저장/불러오기 모듈
JSON 파일 기반
"""
import os
import sys
import json


DEFAULT_CONFIG = {
    "config_version": 2,
    "port": 0,
    "detection": {
        "black_threshold": 5,
        "black_dark_ratio": 98.0,
        "black_block_dark_ratio": 92.0,
        "black_duration": 5,
        "black_alarm_duration": 60,
        "black_motion_suppress_ratio": 0.2,
        "black_recovery_seconds": 2.0,
        "still_threshold": 4,
        "still_changed_ratio": 10.0,
        "still_duration": 120,
        "still_alarm_duration": 60,
        "still_reset_frames": 3,
        "audio_hsv_h_min": 40,
        "audio_hsv_h_max": 95,
        "audio_hsv_s_min": 80,
        "audio_hsv_s_max": 255,
        "audio_hsv_v_min": 60,
        "audio_hsv_v_max": 255,
        "audio_pixel_ratio": 5,
        "audio_level_duration": 60,
        "audio_level_alarm_duration": 60,
        "audio_level_recovery_seconds": 2,
        "embedded_silence_threshold": -50,
        "embedded_silence_duration": 60,
        "embedded_alarm_duration": 60,
        "embedded_recovery_seconds": 2,
    },
    "alarm": {
        "sound_enabled": True,
        "volume": 80,
        "sound_file": "resources/sounds/alarm.wav",
    },
    "rois": {
        "video": [],
        "audio": [],
    },
    "performance": {
        "detection_interval": 200,      # ms, 이산값: 100/200/500/1000
        "scale_factor": 1.0,            # 이산값: 1.0 / 0.5 / 0.25
        "black_detection_enabled": True,
        "still_detection_enabled": True,
        "audio_detection_enabled": True,
        "embedded_detection_enabled": True,
    },
    "capture_recovery": {                   # v2 신규: 캡처 입력 상실 자동복구
        "enabled": True,
        "trigger_sec": 8.0,                 # 전 화면 정지+블랙 지속 시간 → 재오픈 트리거
        "observe_sec": 5.0,                 # 재오픈 후 복구 관찰 시간
        "max_attempts": 3,                  # 최대 재오픈 시도 횟수
        "cooldown_sec": 60.0,               # 복구/실패 후 재트리거 억제(플래핑 방지)
    },
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "chat_id": "",
        "system_chat_id": "",
        "send_image": True,
        "cooldown": 60,
        "notify_black": True,
        "notify_still": True,
        "notify_audio_level": True,
        "notify_embedded": True,
        "notify_signoff": True,
        "notify_system": True,          # v2 신규: [SYSTEM] prefix 프로세스 이벤트
    },
    "recording": {
        "enabled": True,
        "save_dir": "recordings",
        "pre_seconds": 10,              # 1~30
        "post_seconds": 10,             # 1~60
        "max_keep_days": 30,
        "output_width": 960,
        "output_height": 540,
        "output_fps": 10,
    },
    "ui_state": {
        "detection_enabled": True,
        "roi_visible": True,
        "fullscreen": False,            # v2 신규
        "embed_muted": False,           # v2 신규: 임베디드 오디오 음소거 상태
    },
    "signoff": {
        "auto_preparation": True,
        "prep_alarm_sound": "resources/sounds/sign_off.wav",
        "enter_alarm_sound": "resources/sounds/sign_off.wav",
        "release_alarm_sound": "resources/sounds/sign_off.wav",
        "group1": {
            "name": "1TV",
            "enter_roi": {"video_label": ""},
            "suppressed_labels": [],
            "prep_start_time": "00:30",
            "exit_prep_start_time": "04:30",
            "end_time": "05:00",
            "still_trigger_sec": 120,
            "exit_trigger_sec": 30,
            "weekdays": [0, 1],
        },
        "group2": {
            "name": "2TV",
            "enter_roi": {"video_label": ""},
            "suppressed_labels": [],
            "prep_start_time": "00:30",
            "exit_prep_start_time": "04:30",
            "end_time": "05:00",
            "still_trigger_sec": 120,
            "exit_trigger_sec": 30,
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
        },
    },
    "system": {                         # v2 신규: 예약 재시작
        "scheduled_restart_enabled": False,
        "scheduled_restart_base_time": "03:00",     # 기준 시각 HH:MM
        "scheduled_restart_interval_hours": 24,     # 주기 (시간 단위)
        "scheduled_restart_exclude": "",            # 제외 시간대 "HH:MM-HH:MM,..."
    },
}


class ConfigManager:
    """JSON 기반 설정 저장/불러오기"""

    CONFIG_DIR = "config"
    CONFIG_FILE = "kbs_config.json"
    DEFAULT_FILE = "default_config.json"

    def __init__(self):
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        self._default_path = os.path.join(self.CONFIG_DIR, self.DEFAULT_FILE)
        self._config_path = os.path.join(self.CONFIG_DIR, self.CONFIG_FILE)
        # 마지막 load 호출이 파일 손상 등으로 DEFAULT 폴백을 거쳤는지 표시.
        # 호출자가 UI/로그에 별도 안내를 띄울 때 사용.
        self.last_load_was_reset = False

        if not os.path.exists(self._default_path):
            self._write_json(self._default_path, DEFAULT_CONFIG)

    def load(self, filename: str = None) -> dict:
        """설정 불러오기. 파일 없으면 기본값 반환"""
        path = os.path.join(self.CONFIG_DIR, filename) if filename else self._config_path

        if os.path.exists(path):
            try:
                data = self._read_json(path)
                self.last_load_was_reset = False
                return self._merge_defaults(data)
            except Exception as e:
                # 파일이 있는데 파싱 실패 → 설정 손상. 기본값 폴백을 명확히 알린다.
                msg = (
                    f"[ConfigManager] 설정 파일 손상 — 기본값으로 초기화됨\n"
                    f"  경로: {path}\n"
                    f"  사유: {e}\n"
                    f"  조치: 설정 다이얼로그에서 다시 저장하거나 백업 파일을 복원하세요."
                )
                print(msg, file=sys.stderr, flush=True)
                self.last_load_was_reset = True

        return dict(DEFAULT_CONFIG)

    def save(self, config: dict, filename: str = None) -> bool:
        """설정 저장"""
        path = os.path.join(self.CONFIG_DIR, filename) if filename else self._config_path
        try:
            self._write_json(path, config)
            return True
        except Exception:
            return False

    def save_to_path(self, config: dict, abs_path: str) -> bool:
        """절대 경로로 설정 저장"""
        try:
            parent = os.path.dirname(abs_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._write_json(abs_path, config)
            return True
        except Exception:
            return False

    def load_from_path(self, abs_path: str) -> dict:
        """절대 경로에서 설정 불러오기"""
        try:
            data = self._read_json(abs_path)
            return self._merge_defaults(data)
        except Exception as e:
            print(
                f"[ConfigManager] 설정 불러오기 실패 — 기본값 사용\n"
                f"  경로: {abs_path}\n  사유: {e}",
                file=sys.stderr, flush=True,
            )
            self.last_load_was_reset = True
            return dict(DEFAULT_CONFIG)

    def _merge_defaults(self, data: dict) -> dict:
        """기본값과 병합하여 누락된 키 보완"""
        result = dict(DEFAULT_CONFIG)
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value
        return result

    def _read_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: str, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
