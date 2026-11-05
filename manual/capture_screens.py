"""사용안내·README용 화면 캡처 — 화면이 바뀌면 이 명령 한 번으로 다시 찍는다.

사용법 (저장소 루트에서):
    .venv313\\Scripts\\python.exe manual\\capture_screens.py            # 설정창 7개 탭 + 메인 창
    .venv313\\Scripts\\python.exe manual\\capture_screens.py --no-live  # 설정창만

- 설정창: 운영 중인 프로그램과 별도로 이 스크립트가 설정창만 띄워(화면 밖 렌더) 탭별로 찍는다.
  `config/kbs_config.json`을 읽기만 하고 쓰지 않는다. 텔레그램 토큰·채팅 ID는 가린다.
- 메인 창: 운영 중인 `KBS On-Air Monitoring` 창을 PrintWindow로 찍는다(클릭·포커스 변경 없음).
  창이 없으면 건너뛴다.
- 결과: `docs/screenshots/` (README와 사용안내가 같은 그림을 쓴다)
"""
import argparse
import copy
import ctypes
import ctypes.wintypes as W
import os
import queue
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "screenshots")
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # ConfigManager가 config/ 상대경로를 쓴다

# 탭 순서 = SettingsDialog._TAB_LABELS 순서
TAB_FILES = [
    "09_recording_settings.png",  # 영상설정
    "02_video_roi.png",           # 비디오 영역 설정
    "03_audio_roi.png",           # 오디오 레벨미터 영역 설정
    "04_sensitivity.png",         # 감도설정
    "05_signoff.png",             # 정파설정
    "06_alerts.png",              # 알림설정
    "07_save_load.png",           # 저장/불러오기
]
LIVE_FILE = "01_dashboard.png"
LIVE_TITLE_PREFIX = "KBS On-Air Monitoring"


def _mask(cfg: dict) -> dict:
    """그림에 남으면 안 되는 값(텔레그램 토큰·채팅 ID)을 가린 사본."""
    cfg = copy.deepcopy(cfg)
    tg = cfg.setdefault("telegram", {})
    if tg.get("bot_token"):
        tg["bot_token"] = "0000000000:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    for key in ("chat_id", "system_chat_id"):
        if tg.get(key):
            tg[key] = "-100XXXXXXXXXX"
    return cfg


def capture_settings() -> list[str]:
    from PySide6.QtWidgets import QApplication
    from utils.config_manager import ConfigManager
    from ui.settings_dialog import SettingsDialog

    app = QApplication.instance() or QApplication(sys.argv)
    # MainWindow._apply_theme(dark=True)와 같은 방식으로 다크 테마 적용
    res = os.path.join(ROOT, "resources")
    with open(os.path.join(res, "styles", "dark_theme.qss"), encoding="utf-8") as f:
        qss = f.read()
    check_icon = os.path.join(res, "icons", "check_orange.svg").replace("\\", "/")
    app.setStyleSheet(qss.replace("__CHECK_ICON_URL__", check_icon))

    cfg = _mask(ConfigManager().load())
    dlg = SettingsDialog(cfg=cfg, cmd_queue=queue.Queue(), alarm=None)
    dlg.resize(980, 720)
    dlg.setAttribute(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.WA_DontShowOnScreen)
    dlg.show()
    saved = []
    for idx, name in enumerate(TAB_FILES):
        dlg._switch_tab(idx)
        for _ in range(5):
            app.processEvents()
        path = os.path.join(OUT_DIR, name)
        dlg.grab().save(path)
        saved.append(path)
    dlg.close()
    return saved


def capture_live() -> str | None:
    """운영 중인 메인 창을 PrintWindow로 캡처. 창이 없으면 None."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.SetProcessDPIAware()
    found = []

    def _cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n and user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            if buf.value.startswith(LIVE_TITLE_PREFIX):
                found.append(h)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)(_cb), 0)
    if not found:
        return None
    hwnd = found[0]
    rect = W.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT: 가려진 창도 찍힘

    class _BIH(ctypes.Structure):
        _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG),
                    ("biPlanes", W.WORD), ("biBitCount", W.WORD), ("biCompression", W.DWORD),
                    ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG),
                    ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                    ("biClrImportant", W.DWORD)]

    bi = _BIH(biSize=ctypes.sizeof(_BIH), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
    pixels = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, pixels, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)

    import cv2
    import numpy as np
    img = np.frombuffer(pixels, np.uint8).reshape(h, w, 4)[:, :, :3]
    path = os.path.join(OUT_DIR, LIVE_FILE)
    cv2.imencode(".png", img)[1].tofile(path)  # 한글 경로 대응
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-live", action="store_true", help="운영 중인 메인 창은 찍지 않음")
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    if not args.no_live:
        p = capture_live()
        print("메인 창:", p or "운영 중인 창 없음 — 건너뜀")
    for p in capture_settings():
        print("설정창:", p)


if __name__ == "__main__":
    main()
