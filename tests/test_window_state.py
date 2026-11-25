"""ui/window_state.py — 창 자리(saveGeometry 값) 파일 읽기·쓰기와 Qt 왕복."""
import json
import os

import pytest

from ui import window_state


def test_roundtrip(tmp_path):
    p = str(tmp_path / "data" / "window_state.json")
    window_state.save(p, b"\x01\x02geometry\xff")
    assert window_state.load(p) == b"\x01\x02geometry\xff"
    d = json.load(open(p, encoding="utf-8"))
    assert "geometry" in d and "saved_at" in d
    assert not [f for f in os.listdir(tmp_path / "data") if f != "window_state.json"]  # 임시 파일 안 남음


def test_missing_and_broken(tmp_path):
    assert window_state.load(str(tmp_path / "없음.json")) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{깨진", encoding="utf-8")
    assert window_state.load(str(bad)) is None
    bad.write_text(json.dumps({"geometry": "!!!base64아님"}), encoding="utf-8")
    assert window_state.load(str(bad)) is None


def test_qt_geometry_roundtrip(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = QtWidgets.QWidget()
    w.resize(400, 300)  # 화면 밖 모드의 가상 화면(800×600) 안에 들어가게 — 넘치면 Qt가 안으로 끌어와 위치가 바뀜
    w.move(120, 80)
    w.show()
    app.processEvents()
    p = str(tmp_path / "window_state.json")
    window_state.save(p, bytes(w.saveGeometry()))
    w2 = QtWidgets.QWidget()
    assert w2.restoreGeometry(window_state.load(p))
    assert (w2.width(), w2.height()) == (w.width(), w.height())
    w2.show()
    app.processEvents()
    assert w2.pos() == w.pos()  # 창 틀을 포함한 위치(move로 정한 값)
    w.close()
    w2.close()
