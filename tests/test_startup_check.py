"""
기동 자가점검(_startup_self_check)의 부품(파이썬 패키지) 항목 단위 테스트
2026-11-18: 새 PC에서 psutil·requests 등이 빠진 채 켜졌는데 자가점검이 이를 보여 주지 않아
「UI 손상」 오경보로만 드러났다 → 자가점검에 「부품 누락」 항목을 더함.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processes import watchdog_process as wp


def _fake_find_spec(missing):
    """missing에 든 이름만 없다고 답한다(시험 PC의 실제 설치 상태와 무관하게)."""
    def fake(name, *args, **kwargs):
        return None if name in missing else object()
    return fake


def test_missing_packages_reported(monkeypatch):
    """psutil·requests가 없으면 「부품 누락: psutil, requests」가 나오고 문제 있음(True)."""
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec({"psutil", "requests"}))
    line, bad = wp._startup_self_check()
    assert "부품 누락: psutil, requests" in line
    assert bad is True


def test_all_packages_present(monkeypatch):
    """8개 모두 있으면 「✓ 부품」이 나오고 누락 문구는 없다."""
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: object())
    line, _bad = wp._startup_self_check()
    assert "✓ 부품" in line
    assert "부품 누락" not in line


def test_package_list_matches_requirements():
    """점검 목록이 requirements.txt의 패키지 수(8개)와 같다 — 한쪽만 바뀌는 것을 막는다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "requirements.txt"), encoding="utf-8") as f:
        reqs = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    assert len(wp._REQUIRED_MODULES) == len(reqs)
