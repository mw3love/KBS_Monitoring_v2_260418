"""
텔레그램 재전송 판정 테스트.

- 사진을 올리는 도중 시간 초과(write timeout) → 요청이 끝까지 안 갔으므로 사진 없이 재전송
  (2026-11-12·11-17 정파 알림 2건이 이 형태로 '전달 불명' 처리돼 유실됨)
- 요청은 갔고 응답만 늦음(ReadTimeout 등) → 중복 방지 위해 재전송 안 함 (2026-10-07 3중 발송)
"""
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from urllib3.exceptions import ProtocolError, ReadTimeoutError
from http.client import RemoteDisconnected

from detection.telegram_worker import TelegramWorker


def _worker():
    w = TelegramWorker(result_queue=None)
    w._bot_token = "TOKEN"
    w._chat_id = "123"
    w._send_image = True
    return w


def _ok():
    r = MagicMock()
    r.status_code = 200
    return r


def _write_timeout():
    """운영 로그에 찍힌 그대로의 예외 형태."""
    return requests.exceptions.ConnectionError(
        ProtocolError("Connection aborted.", TimeoutError("The write operation timed out")))


def _signoff_item():
    return {
        "_signoff": True, "group_name": "2TV", "is_entry": False, "is_revert": False,
        "trigger_label": "V5", "trigger_media": "", "suppressed_labels": ["V5"],
        "elapsed_sec": 100.0, "jpeg_bytes": b"\xff\xd8fakejpeg",
    }


def _alarm_item():
    return {
        "alarm_type": "블랙", "label": "V1", "media_name": "1TV",
        "is_recovery": False, "duration_sec": 10.0, "jpeg_bytes": b"\xff\xd8fakejpeg",
    }


def _run(item, side_effect):
    w = _worker()
    with patch("detection.telegram_worker._requests.post", side_effect=side_effect) as post, \
            patch("detection.telegram_worker.time.sleep"):
        ok = w._send(item)
    return ok, post


def test_classify_write_timeout_is_not_unknown():
    exc = _write_timeout()
    assert TelegramWorker._is_upload_timeout(exc)
    assert not TelegramWorker._is_delivery_unknown(exc)


def test_classify_read_side_errors_still_unknown():
    """10월 3중 발송 방지 장치는 그대로: 응답 쪽 지연·끊김은 '전달 불명'."""
    read_to = requests.exceptions.ReadTimeout("read timed out")
    wrapped_read = requests.exceptions.ConnectionError(
        ReadTimeoutError(None, "/", "Read timed out."))
    remote_closed = requests.exceptions.ConnectionError(
        ProtocolError("Connection aborted.", RemoteDisconnected("closed")))
    for exc in (read_to, wrapped_read, remote_closed):
        assert TelegramWorker._is_delivery_unknown(exc), repr(exc)
        assert not TelegramWorker._is_upload_timeout(exc), repr(exc)


def test_signoff_write_timeout_resends_without_photo():
    ok, post = _run(_signoff_item(), [_write_timeout(), _ok()])
    assert ok
    assert post.call_count == 2
    first, second = post.call_args_list
    assert first.args[0].endswith("/sendPhoto")
    assert second.args[0].endswith("/sendMessage"), "재전송은 사진 없이 글자만"
    assert "사진 없이 재전송" in second.kwargs["json"]["text"]


def test_alarm_write_timeout_resends_without_photo():
    ok, post = _run(_alarm_item(), [_write_timeout(), _ok()])
    assert ok
    assert post.call_count == 2
    assert post.call_args_list[1].args[0].endswith("/sendMessage")


def test_signoff_read_timeout_not_resent():
    ok, post = _run(_signoff_item(), [requests.exceptions.ReadTimeout("slow"), _ok()])
    assert not ok
    assert post.call_count == 1, "응답 지연은 중복 방지 위해 재전송하지 않아야 함"


def test_alarm_read_timeout_not_resent():
    ok, post = _run(_alarm_item(), [requests.exceptions.ReadTimeout("slow"), _ok()])
    assert not ok
    assert post.call_count == 1
