"""utils/autostart.py — 시작프로그램 바로가기 만들기·대상 확인·지우기.

진짜 시작프로그램 폴더는 건드리지 않는다(임시 폴더를 시작프로그램 폴더로 넘김).
"""
import os
import sys

import pytest

from utils import autostart

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용")


def _bat(tmp_path, name="실행.bat"):
    d = tmp_path / "설치폴더"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text("@echo off\n", encoding="ascii")
    return str(p)


def test_enable_creates_link_pointing_to_bat(tmp_path):
    startup = tmp_path / "Startup"
    bat = _bat(tmp_path)
    assert autostart.is_enabled(bat, str(startup)) is False
    autostart.enable(bat, str(startup))
    link = startup / autostart.LINK_NAME
    assert link.exists()
    assert os.path.normcase(autostart.read_target(str(startup))) == os.path.normcase(bat)
    assert autostart.is_enabled(bat, str(startup)) is True


def test_link_to_other_bat_is_not_enabled(tmp_path):
    startup = tmp_path / "Startup"
    other = tmp_path / "다른폴더"
    other.mkdir()
    other_bat = other / "실행.bat"
    other_bat.write_text("@echo off\n", encoding="ascii")
    autostart.enable(str(other_bat), str(startup))
    assert autostart.is_enabled(_bat(tmp_path), str(startup)) is False
    # 체크하면 이 폴더로 다시 만든다
    bat = _bat(tmp_path)
    autostart.enable(bat, str(startup))
    assert autostart.is_enabled(bat, str(startup)) is True


def test_disable_removes_link(tmp_path):
    startup = tmp_path / "Startup"
    bat = _bat(tmp_path)
    autostart.enable(bat, str(startup))
    autostart.disable(str(startup))
    assert not (startup / autostart.LINK_NAME).exists()
    assert autostart.is_enabled(bat, str(startup)) is False
    autostart.disable(str(startup))  # 없을 때 지워도 오류 없음


def test_default_startup_dir_is_user_startup():
    d = autostart.default_startup_dir()
    assert d.lower().endswith(os.path.join("start menu", "programs", "startup"))
