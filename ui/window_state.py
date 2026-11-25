"""
창 자리 기억 — data/window_state.json에 Qt saveGeometry() 값(위치·크기·최대화)을 둔다.

PC마다 모니터 배치가 달라서 설정 파일(kbs_config.json — 백업으로 다른 PC에 옮겨짐) 대신 data/에 따로 둔다.
쓰기는 임시 파일에 쓴 뒤 os.replace로 바꿔, 크래시 때 반쯤 쓴 파일이 남지 않게 한다.
MainWindow가 켤 때 읽고, 창을 옮기거나 크기를 바꾼 2초 뒤와 닫을 때 쓴다(전체화면이면 안 씀).
계획 문서: docs/plan/20261125-0953-스스로-켜지고-크래시-뒤-다시-켜기.md
"""
import base64
import binascii
import datetime
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(_ROOT, "data", "window_state.json")


def load(path: str = DEFAULT_PATH) -> bytes | None:
    """저장된 saveGeometry 값. 파일이 없거나 깨졌으면 None."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return base64.b64decode(data["geometry"], validate=True)
    except (OSError, ValueError, KeyError, TypeError, binascii.Error):
        return None


def save(path: str, geometry: bytes) -> None:
    """saveGeometry 값을 저장한다. 실패하면 OSError."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({
            "geometry": base64.b64encode(geometry).decode("ascii"),
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }, f)
    os.replace(tmp, path)
