"""
Detection 프로세스 진입점 + 메인 루프
Watchdog이 spawn하며, multiprocessing.Process(target=run, args=(...)) 형태로 호출.
PySide6 임포트 금지. QThread/QTimer/Signal 사용 금지.
"""
import os
import sys
import time
import struct
import threading
import logging
import traceback
from typing import Dict, Optional

_log = logging.getLogger(__name__)

# ── 경로 설정 (프로세스 독립 실행 시 패키지 루트 보장) ───────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# Heartbeat 라이터
# ══════════════════════════════════════════════════════════════════════════════

class HeartbeatWriter(threading.Thread):
    """5초 주기로 data/heartbeat.dat 갱신 (Watchdog 감시용)."""

    HEARTBEAT_PATH = os.path.join(_ROOT, "data", "heartbeat.dat")

    def __init__(self):
        super().__init__(daemon=True, name="HeartbeatWriter")
        self._running = False

    def start(self):
        self._running = True
        super().start()

    def stop(self):
        self._running = False

    def run(self):
        os.makedirs(os.path.dirname(self.HEARTBEAT_PATH), exist_ok=True)
        while self._running:
            try:
                with open(self.HEARTBEAT_PATH, "wb") as f:
                    f.write(struct.pack("<d", time.time()))
            except Exception:
                pass
            time.sleep(5.0)


# ══════════════════════════════════════════════════════════════════════════════
# 메시지 발행 헬퍼
# ══════════════════════════════════════════════════════════════════════════════

def _put(result_queue, msg, drop_counter: list, drop_key: str = "result"):
    """result_queue에 메시지 삽입. Full 시 1개 drop 후 재시도."""
    try:
        result_queue.put_nowait(msg)
    except Exception:
        try:
            result_queue.get_nowait()
            drop_counter[0] += 1
            result_queue.put_nowait(msg)
        except Exception:
            drop_counter[0] += 1


def _put_nodrop(result_queue, msg, max_retry: int = 3):
    """drop 금지 메시지 (DetectionReady, SignoffStateChange 등). 최대 3회 재시도."""
    for _ in range(max_retry):
        try:
            result_queue.put_nowait(msg)
            return
        except Exception:
            time.sleep(0.05)
    # 최후 수단: 1개 drop 후 강제 삽입
    try:
        dropped = result_queue.get_nowait()
        result_queue.put_nowait(msg)
        _log.error(f"result_queue FULL → {type(dropped).__name__} drop 후 {type(msg).__name__} 강제 삽입")
    except Exception as e:
        _log.error(f"result_queue 심각 문제 → {type(msg).__name__} 저장 실패: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 설정 적용 헬퍼
# ══════════════════════════════════════════════════════════════════════════════

def _apply_config_to_detector(detector, cfg: dict):
    det = cfg.get("detection", {})
    detector.black_threshold            = det.get("black_threshold", 10)
    detector.black_dark_ratio           = det.get("black_dark_ratio", 95.0)
    detector.black_duration             = det.get("black_duration", 20)
    detector.black_alarm_duration       = det.get("black_alarm_duration", 60)
    detector.black_motion_suppress_ratio = det.get("black_motion_suppress_ratio", 0.2)
    detector.still_threshold            = det.get("still_threshold", 4)
    detector.still_changed_ratio        = det.get("still_changed_ratio", 10.0)
    detector.still_duration             = det.get("still_duration", 60)
    detector.still_alarm_duration       = det.get("still_alarm_duration", 60)
    detector.audio_hsv_h_min            = det.get("audio_hsv_h_min", 40)
    detector.audio_hsv_h_max            = det.get("audio_hsv_h_max", 95)
    detector.audio_hsv_s_min            = det.get("audio_hsv_s_min", 80)
    detector.audio_hsv_s_max            = det.get("audio_hsv_s_max", 255)
    detector.audio_hsv_v_min            = det.get("audio_hsv_v_min", 60)
    detector.audio_hsv_v_max            = det.get("audio_hsv_v_max", 255)
    detector.audio_pixel_ratio          = det.get("audio_pixel_ratio", 5)
    detector.audio_level_duration       = det.get("audio_level_duration", 20)
    detector.audio_level_alarm_duration = det.get("audio_level_alarm_duration", 60)
    detector.audio_level_recovery_seconds = det.get("audio_level_recovery_seconds", 2)
    detector.embedded_silence_threshold = det.get("embedded_silence_threshold", -50)
    detector.embedded_silence_duration  = det.get("embedded_silence_duration", 20)
    detector.embedded_alarm_duration    = det.get("embedded_alarm_duration", 60)

    perf = cfg.get("performance", {})
    detector.scale_factor               = perf.get("scale_factor", 1.0)
    detector.black_detection_enabled    = perf.get("black_detection_enabled", True)
    detector.still_detection_enabled    = perf.get("still_detection_enabled", True)


def _apply_config_to_recorder(recorder, cfg: dict):
    rec = cfg.get("recording", {})
    recorder.configure(
        enabled       = rec.get("enabled", True),
        save_dir      = rec.get("save_dir", "recordings"),
        pre_seconds   = rec.get("pre_seconds", 5),
        post_seconds  = rec.get("post_seconds", 15),
        max_keep_days = rec.get("max_keep_days", 7),
        output_width  = rec.get("output_width", 960),
        output_height = rec.get("output_height", 540),
        output_fps    = rec.get("output_fps", 10),
    )


def _apply_config_to_telegram(telegram, cfg: dict):
    tg = cfg.get("telegram", {})
    telegram.configure(
        enabled          = tg.get("enabled", False),
        bot_token        = tg.get("bot_token", ""),
        chat_id          = tg.get("chat_id", ""),
        send_image       = tg.get("send_image", True),
        cooldown         = tg.get("cooldown", 60),
        notify_black     = tg.get("notify_black", True),
        notify_still     = tg.get("notify_still", True),
        notify_audio_level = tg.get("notify_audio_level", True),
        notify_embedded  = tg.get("notify_embedded", True),
        notify_signoff   = tg.get("notify_signoff", True),
    )


# ══════════════════════════════════════════════════════════════════════════════
# 프로세스 진입점
# ══════════════════════════════════════════════════════════════════════════════

def run(result_queue, cmd_queue, shutdown_event,
        state_lock, frame_shm_name: str, state_shm_name: str,
        version: str = "2.0", cmd_event=None):
    """
    Watchdog이 spawn하는 Detection 프로세스 메인 함수.
    종료 조건: shutdown_event set 또는 Shutdown 메시지 수신.
    """
    from utils.logger import AppLogger
    logger = AppLogger(suffix="_detection")

    def log_info(msg: str):
        logger.info(msg)
        from ipc.messages import LogEntry
        _put(result_queue, LogEntry(level="info", source="detection", message=msg),
             _ipc_counters, "result")

    def log_error(msg: str):
        logger.error(msg)
        from ipc.messages import LogEntry
        _put(result_queue, LogEntry(level="error", source="detection", message=msg),
             _ipc_counters, "result")

    _ipc_counters = [0]   # [result_dropped]
    _cmd_dropped  = [0]

    log_info(f"Detection 프로세스 시작 (PID={os.getpid()}, v{version})")

    # ── 1. 설정 로드 ──────────────────────────────────────────────────────────
    from utils.config_manager import ConfigManager
    cfg_mgr = ConfigManager()
    cfg = cfg_mgr.load()
    log_info(f"설정 로드 완료 (config_version={cfg.get('config_version', '?')})")

    # ── 2. SharedMemory 연결 ──────────────────────────────────────────────────
    from ipc.shared_frame import SharedFrameBuffer
    from ipc.shared_state import SharedStateBuffer
    try:
        shared_frame = SharedFrameBuffer(create=False, name=frame_shm_name)
        shared_state = SharedStateBuffer(create=False, name=state_shm_name, lock=state_lock)
        log_info("SharedMemory 연결 성공")
    except Exception as e:
        log_error(f"SharedMemory 연결 실패: {e}")
        shared_frame = None
        shared_state = None

    # ── 3. 컴포넌트 초기화 ────────────────────────────────────────────────────
    from core.roi_manager import ROIManager
    from detection.detector import Detector
    from detection.video_capture import VideoCaptureWorker
    from detection.audio_monitor import AudioMonitorWorker, set_system_volume, set_system_mute
    from detection.signoff_manager import SignoffManager
    from detection.auto_recorder import AutoRecorder
    from detection.telegram_worker import TelegramWorker

    roi_mgr   = ROIManager()
    detector  = Detector()
    recorder  = AutoRecorder(result_queue=result_queue)
    telegram  = TelegramWorker(result_queue=result_queue)
    heartbeat = HeartbeatWriter()

    signoff_mgr = SignoffManager(result_queue=result_queue)
    # SignoffManager의 _emit은 result_queue에 직접 넣지만,
    # drop 금지 메시지(SignoffStateChange)는 _put_nodrop으로 래핑 필요.
    # 여기서는 SignoffManager의 _emit을 오버라이드하여 drop-safe 버전 주입.
    def _signoff_emit_safe(msg):
        from ipc.messages import SignoffStateChange
        if isinstance(msg, SignoffStateChange):
            _put_nodrop(result_queue, msg)
        else:
            _put(result_queue, msg, _ipc_counters)
    signoff_mgr._emit = _signoff_emit_safe

    # 설정 적용
    _apply_config_to_detector(detector, cfg)
    _apply_config_to_recorder(recorder, cfg)
    _apply_config_to_telegram(telegram, cfg)

    perf = cfg.get("performance", {})
    detection_interval_ms = perf.get("detection_interval", 200)
    detection_interval    = max(0.05, detection_interval_ms / 1000.0)

    # ROI 복원
    roi_mgr.from_dict(cfg.get("rois", {}))
    video_rois = roi_mgr.video_rois
    audio_rois = roi_mgr.audio_rois

    # SignoffManager 설정
    still_trigger_sec = cfg.get("detection", {}).get("still_duration", 60.0)
    signoff_mgr.configure_from_dict(cfg.get("signoff", {}), still_trigger_sec)
    _update_signoff_media_names(signoff_mgr, video_rois + audio_rois)

    # DetectionState 초기화
    detector.update_roi_list(video_rois)

    # detection_enabled 상태 (SharedState 기준)
    detection_enabled = (
        shared_state.get_detection_enabled() if shared_state else True
    )
    paused_for_roi = False

    # 알람 상태 추적 (AlarmTrigger/Resolve 전환 감지용)
    _prev_black: Dict[str, bool] = {}
    _prev_still: Dict[str, bool] = {}
    _prev_audio: Dict[str, bool] = {}
    _embedded_was_alerting = False

    # 현재 프레임 캐시 (AlarmTrigger snapshot용)
    _last_frame = None
    _last_frame_lock = threading.Lock()

    # ── 4. 워커 스레드 시작 ───────────────────────────────────────────────────
    port = cfg.get("port", 0)

    video_worker = VideoCaptureWorker(
        shared_frame=shared_frame,
        result_queue=result_queue,
        port=port,
    )
    video_file = cfg.get("video_file", "").strip()
    if video_file:
        video_worker.set_video_file(video_file)

    # 오디오 청크 → recorder
    def _on_audio_chunk(samples, ts):
        recorder.push_audio(samples, ts)

    # 무음 상태 → detector
    _silence_seconds = [0.0]
    def _on_silence(secs: float):
        _silence_seconds[0] = secs

    def _on_frame(frame):
        import numpy as np
        with _last_frame_lock:
            nonlocal _last_frame
            _last_frame = frame.copy()
        recorder.push_frame(frame)

    video_worker.on_frame = _on_frame

    audio_worker = AudioMonitorWorker(
        shared_state=shared_state,
        result_queue=result_queue,
    )
    audio_worker.on_silence_detected = _on_silence
    audio_worker.on_audio_chunk = _on_audio_chunk

    # 볼륨/Mute 초기값 시스템 적용
    if shared_state:
        try:
            set_system_volume(shared_state.get_volume())
            set_system_mute(shared_state.get_mute())
        except Exception:
            pass

    workers_started = False
    try:
        video_worker.start()
        audio_worker.start()
        signoff_mgr.start()
        recorder.start()
        telegram.start()
        heartbeat.start()
        workers_started = True
        log_info("워커 스레드 전체 시작 완료")
    except OSError as e:
        log_error(f"워커 스레드 시작 실패: {e}")

    # ── 5. DetectionReady 발행 ────────────────────────────────────────────────
    from ipc.messages import DetectionReady
    _put_nodrop(result_queue, DetectionReady(
        pid=os.getpid(),
        config_loaded=True,
        roi_count=len(video_rois) + len(audio_rois),
        version=version,
    ))
    log_info(f"DetectionReady 발행 (ROI={len(video_rois)}V+{len(audio_rois)}A)")

    # ── 6. DIAG 상태 ─────────────────────────────────────────────────────────
    _diag_last_t = 0.0
    _diag_interval = 30.0
    _loop_count = 0
    _drop_count_snap = 0
    # loop jitter 누적 (sleep 후 실제 경과 - 목표 interval 의 절댓값 평균)
    _jitter_sum_ms = 0.0
    _jitter_samples = 0

    # ── 7. 메인 루프 ──────────────────────────────────────────────────────────
    _running = True
    while _running:
        t = time.monotonic()

        # ── DIAG (독립 try-except) ─────────────────────────────────────────
        try:
            now_t = time.time()
            if now_t - _diag_last_t >= _diag_interval:
                _diag_last_t = now_t
                _avg_jitter_ms = (
                    _jitter_sum_ms / _jitter_samples if _jitter_samples > 0 else 0.0
                )
                _run_diag(
                    result_queue, _ipc_counters, _cmd_dropped,
                    detector, signoff_mgr, audio_worker,
                    telegram, recorder, video_rois, audio_rois,
                    _loop_count, detection_enabled, paused_for_roi,
                    loop_jitter_ms=_avg_jitter_ms,
                )
                _loop_count = 0
                _jitter_sum_ms = 0.0
                _jitter_samples = 0
        except Exception as e:
            try:
                log_error(f"DIAG 오류: {traceback.format_exc()}")
            except Exception:
                pass

        # ── cmd_queue 처리 (독립 try-except) ──────────────────────────────
        try:
            _process_commands(
                cmd_queue, cfg, cfg_mgr,
                detector, recorder, telegram, signoff_mgr,
                roi_mgr, shared_state, audio_worker, video_worker,
                result_queue, _ipc_counters, _cmd_dropped,
                set_system_volume, set_system_mute,
                lambda enabled: shared_state.set_detection_enabled(enabled) if shared_state else None,
            )
        except _ShutdownSignal:
            log_info("Shutdown 메시지 수신 → 종료")
            _running = False
        except Exception as e:
            try:
                log_error(f"cmd 처리 오류: {traceback.format_exc()}")
            except Exception:
                pass

        # shutdown 체크
        if shutdown_event is not None and shutdown_event.is_set():
            log_info("shutdown_event 감지 → 종료")
            _running = False
            break

        # 로컬 변수 업데이트 (cmd 처리 후)
        if shared_state:
            detection_enabled = shared_state.get_detection_enabled()

        # ── 감지 루프 (독립 try-except) ────────────────────────────────────
        try:
            if detection_enabled and not paused_for_roi and shared_frame:
                frame = shared_frame.read_frame()
                if frame is not None:
                    _loop_count += 1
                    video_rois = roi_mgr.video_rois
                    audio_rois = roi_mgr.audio_rois

                    # 정파 감지용 force_still_labels
                    force_still = set()
                    for gid, grp in signoff_mgr.get_groups().items():
                        v_lbl = grp.enter_roi.get("video_label", "")
                        if v_lbl:
                            force_still.add(v_lbl)

                    # 비디오 감지
                    vid_results = detector.detect_frame(frame, video_rois,
                                                        force_still_labels=force_still)
                    # 오디오 레벨미터 감지
                    aud_results = detector.detect_audio_roi(frame, audio_rois)
                    # 임베디드 오디오 감지
                    emb_alerting = detector.update_embedded_silence(_silence_seconds[0])

                    # SignoffManager 에 스틸 결과 공급
                    still_map = {lbl: v.get("still", False) for lbl, v in vid_results.items()}
                    signoff_mgr.update_detection(still_map)

                    # 알람 이벤트 발행
                    with _last_frame_lock:
                        snap = _last_frame.copy() if _last_frame is not None else None

                    _process_alarms(
                        result_queue, _ipc_counters,
                        vid_results, aud_results, emb_alerting,
                        _prev_black, _prev_still, _prev_audio,
                        signoff_mgr, detector, telegram, recorder,
                        video_rois, audio_rois, snap,
                    )
                    _embedded_was_alerting = emb_alerting

        except Exception as e:
            try:
                log_error(f"감지 루프 오류: {traceback.format_exc()}")
            except Exception:
                pass

        elapsed = time.monotonic() - t
        sleep_target = max(0.0, detection_interval - elapsed)
        if cmd_event is not None and sleep_target > 0:
            cmd_event.wait(timeout=sleep_target)
            cmd_event.clear()
        else:
            time.sleep(sleep_target)
        actual_elapsed = time.monotonic() - t
        _jitter_sum_ms += abs(actual_elapsed - detection_interval) * 1000.0
        _jitter_samples += 1

    # ── 8. 정리 ───────────────────────────────────────────────────────────────
    log_info("Detection 프로세스 종료 중...")
    heartbeat.stop()
    signoff_mgr.stop()
    recorder.stop()
    telegram.stop()
    video_worker.stop()
    audio_worker.stop()

    for w in (video_worker, audio_worker):
        try:
            w.join(timeout=3.0)
        except Exception:
            pass

    if shared_frame:
        try:
            shared_frame.close()
        except Exception:
            pass
    if shared_state:
        try:
            shared_state.close()
        except Exception:
            pass

    log_info("Detection 프로세스 종료 완료")


# ══════════════════════════════════════════════════════════════════════════════
# cmd_queue 처리
# ══════════════════════════════════════════════════════════════════════════════

def _process_commands(
    cmd_queue, cfg, cfg_mgr,
    detector, recorder, telegram, signoff_mgr,
    roi_mgr, shared_state, audio_worker, video_worker,
    result_queue, ipc_counters, cmd_dropped,
    set_volume_fn, set_mute_fn, set_det_enabled_fn,
):
    from ipc.messages import (
        ApplyConfig, UpdateROIs, SetDetectionEnabled, SetVolume, SetMute,
        SetSignoffState, PauseForRoiEdit, ClearAlarms, RequestAutoPerf,
        RequestSnapshot, Shutdown, LogEntry,
    )
    _MAX_PER_TICK = 10
    for _ in range(_MAX_PER_TICK):
        try:
            msg = cmd_queue.get_nowait()
        except Exception:
            break

        try:
            if isinstance(msg, ApplyConfig):
                old_video_file = cfg.get("video_file", "")
                old_port = cfg.get("port", 0)
                cfg.update(msg.config)
                _apply_config_to_detector(detector, cfg)
                _apply_config_to_recorder(recorder, cfg)
                _apply_config_to_telegram(telegram, cfg)
                new_video_file = cfg.get("video_file", "").strip()
                new_port = cfg.get("port", 0)
                if new_video_file != old_video_file or new_port != old_port:
                    if new_video_file:
                        video_worker.set_video_file(new_video_file)
                    else:
                        video_worker.set_port(new_port)
                if msg.reason in ("user_save",):
                    cfg_mgr.save(cfg)
                _put(result_queue,
                     LogEntry(level="info", source="detection",
                              message=f"ApplyConfig 적용 완료 (reason={msg.reason})"),
                     ipc_counters)

            elif isinstance(msg, UpdateROIs):
                roi_mgr.from_dict({"video": [], "audio": []})
                # rois: list[dict]
                video_list = [r for r in msg.rois if r.get("roi_type") == "video"]
                audio_list = [r for r in msg.rois if r.get("roi_type") == "audio"]
                from core.roi_manager import ROI
                roi_mgr._video_rois = [ROI.from_dict(r) for r in video_list]
                roi_mgr._audio_rois = [ROI.from_dict(r) for r in audio_list]
                roi_mgr._relabel_video()
                roi_mgr._relabel_audio()
                detector.update_roi_list(roi_mgr.video_rois)
                _update_signoff_media_names(signoff_mgr,
                                            roi_mgr.video_rois + roi_mgr.audio_rois)

            elif isinstance(msg, SetDetectionEnabled):
                set_det_enabled_fn(msg.enabled)

            elif isinstance(msg, SetVolume):
                if shared_state:
                    shared_state.set_volume(msg.volume)
                set_volume_fn(msg.volume)
                if audio_worker:
                    audio_worker.set_volume(msg.volume / 100.0)

            elif isinstance(msg, SetMute):
                if shared_state:
                    shared_state.set_mute(msg.muted)
                set_mute_fn(msg.muted)
                if audio_worker:
                    audio_worker.set_muted(msg.muted)

            elif isinstance(msg, SetSignoffState):
                signoff_mgr.set_state_direct(msg.group_id, msg.new_state)

            elif isinstance(msg, ClearAlarms):
                detector.reset_all()

            elif isinstance(msg, RequestAutoPerf):
                _handle_auto_perf(result_queue, ipc_counters, msg.duration_sec)

            elif isinstance(msg, Shutdown):
                # shutdown은 메인 루프에서 shutdown_event로도 감지하므로 여기선 플래그만
                raise _ShutdownSignal()

        except _ShutdownSignal:
            raise
        except Exception as e:
            _put(result_queue,
                 LogEntry(level="error", source="detection",
                          message=f"cmd 처리 오류 ({type(msg).__name__}): {e}"),
                 ipc_counters)


class _ShutdownSignal(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════════
# 알람 이벤트 처리
# ══════════════════════════════════════════════════════════════════════════════

def _process_alarms(
    result_queue, ipc_counters,
    vid_results, aud_results, emb_alerting,
    prev_black, prev_still, prev_audio,
    signoff_mgr, detector, telegram, recorder,
    video_rois, audio_rois, snap,
):
    from ipc.messages import AlarmTrigger, AlarmResolve, DetectionResult
    from core.roi_manager import ROI

    roi_media = {roi.label: roi.media_name for roi in (video_rois + audio_rois)}

    # 비디오 ROI: 블랙/스틸
    for lbl, res in vid_results.items():
        media = roi_media.get(lbl, lbl)

        for det_type, alerting_key, prev_dict in (
            ("black", "black_alerting", prev_black),
            ("still", "still_alerting", prev_still),
        ):
            alerting = res.get(alerting_key, False)
            was = prev_dict.get(lbl, False)

            # 정파 억제 체크
            suppressed = signoff_mgr.is_signoff_label(lbl)
            if det_type == "still":
                suppressed = suppressed or signoff_mgr.is_prep_label(lbl)

            if alerting and not was:
                if not suppressed:
                    _put(result_queue,
                         AlarmTrigger(label=lbl, detection_type=det_type,
                                      roi_type="video",
                                      snapshot_jpeg=_encode_jpeg(snap)),
                         ipc_counters)
                    telegram.notify(
                        "블랙" if det_type == "black" else "스틸",
                        lbl, media, snap,
                    )
                    recorder.trigger(det_type, lbl, media)
            elif not alerting and was:
                duration = res.get(f"{det_type}_last_duration", 0.0)
                _put(result_queue,
                     AlarmResolve(label=lbl, detection_type=det_type,
                                  duration_sec=duration),
                     ipc_counters)
                telegram.notify(
                    "블랙" if det_type == "black" else "스틸",
                    lbl, media, is_recovery=True,
                )

            prev_dict[lbl] = alerting

    # 오디오 레벨미터 ROI
    for lbl, res in aud_results.items():
        media = roi_media.get(lbl, lbl)
        alerting = res.get("alerting", False)
        was = prev_audio.get(lbl, False)
        suppressed = signoff_mgr.is_signoff_label(lbl)

        if alerting and not was:
            if not suppressed:
                _put(result_queue,
                     AlarmTrigger(label=lbl, detection_type="audio_level",
                                  roi_type="audio",
                                  snapshot_jpeg=_encode_jpeg(snap)),
                     ipc_counters)
                telegram.notify("오디오", lbl, media, snap)
                recorder.trigger("오디오", lbl, media)
        elif not alerting and was:
            _put(result_queue,
                 AlarmResolve(label=lbl, detection_type="audio_level",
                              duration_sec=res.get("last_duration", 0.0)),
                 ipc_counters)
            telegram.notify("오디오", lbl, media, is_recovery=True)

        prev_audio[lbl] = alerting

    # 임베디드 오디오 (그룹 귀속 없음 — 정파 억제 미적용)
    emb_was = getattr(_process_alarms, "_emb_was", False)
    if emb_alerting and not emb_was:
        _put(result_queue,
             AlarmTrigger(label="EA", detection_type="embedded",
                          roi_type="embedded",
                          snapshot_jpeg=None),
             ipc_counters)
        telegram.notify("무음", "EA", "임베디드오디오")
    elif not emb_alerting and emb_was:
        _put(result_queue,
             AlarmResolve(label="EA", detection_type="embedded", duration_sec=0.0),
             ipc_counters)
        telegram.notify("무음", "EA", "임베디드오디오", is_recovery=True)
    _process_alarms._emb_was = emb_alerting


def _encode_jpeg(frame) -> "bytes | None":
    if frame is None:
        return None
    try:
        import cv2
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes() if ok else None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DIAG 발행
# ══════════════════════════════════════════════════════════════════════════════

def _run_diag(
    result_queue, ipc_counters, cmd_dropped,
    detector, signoff_mgr, audio_worker,
    telegram, recorder, video_rois, audio_rois,
    loop_count, detection_enabled, paused_for_roi,
    loop_jitter_ms: float = 0.0,
):
    from ipc.messages import DiagSnapshot
    import psutil

    proc = psutil.Process(os.getpid())

    def emit(section, payload):
        _put(result_queue, DiagSnapshot(section=section, payload=payload), ipc_counters)

    try:
        emit("SYSTEM-HB", {
            "pid": os.getpid(),
            "rss_mb": proc.memory_info().rss / 1024 / 1024,
            "cpu_percent": proc.cpu_percent(interval=None),
            "loop_count": loop_count,
            "detection_enabled": detection_enabled,
            "paused_for_roi": paused_for_roi,
            "loop_jitter_ms": round(loop_jitter_ms, 2),
        })
    except Exception as e:
        _log.error(f"SYSTEM-HB DIAG 실패: {e}")

    try:
        raw = detector._last_raw
        emit("DIAG-V", {
            lbl: {
                "dark_ratio":    v.get("dark_ratio", -1.0),
                "changed_ratio": v.get("changed_ratio", -1.0),
                "black_alert":   detector._black_states[lbl].is_alerting if lbl in detector._black_states else False,
                "still_alert":   detector._still_states[lbl].is_alerting if lbl in detector._still_states else False,
            }
            for lbl, v in raw.items()
        })
    except Exception as e:
        _log.error(f"DIAG-V 실패: {e}")

    try:
        alarm_payload = {}
        for lbl, state in detector._black_states.items():
            alarm_payload[f"{lbl}_black"] = {
                "alerting": state.is_alerting,
                "duration": round(state.alert_duration, 1),
            }
        for lbl, state in detector._still_states.items():
            alarm_payload[f"{lbl}_still"] = {
                "alerting": state.is_alerting,
                "duration": round(state.alert_duration, 1),
            }
        for lbl, state in detector._audio_level_states.items():
            alarm_payload[f"{lbl}_audio"] = {
                "alerting": state.is_alerting,
                "duration": round(state.alert_duration, 1),
            }
        emit("DIAG-ALARM", alarm_payload)
    except Exception as e:
        _log.error(f"DIAG-ALARM 실패: {e}")

    try:
        signoff_payload = {}
        for gid, group in signoff_mgr.get_groups().items():
            state = signoff_mgr.get_state(gid)
            flags = signoff_mgr.get_debug_flags(gid)
            signoff_payload[f"group{gid}"] = {
                "name":  group.name,
                "state": state.value,
                **flags,
                "elapsed": round(signoff_mgr.get_elapsed_seconds(gid), 1),
            }
        emit("DIAG-SIGNOFF", signoff_payload)
    except Exception as e:
        _log.error(f"DIAG-SIGNOFF 실패: {e}")

    try:
        emit("DIAG-AUDIO", {
            "device": getattr(audio_worker, "_device_name", "?"),
            "silence_sec": round(getattr(audio_worker, "_silence_duration", 0.0), 1),
            "embedded_alerting": detector.embedded_alerting,
        })
    except Exception as e:
        _log.error(f"DIAG-AUDIO 실패: {e}")

    try:
        emit("DIAG-IPC", {
            "result_dropped": ipc_counters[0],
            "cmd_dropped":    cmd_dropped[0],
            "result_qsize":   result_queue.qsize() if hasattr(result_queue, "qsize") else -1,
            "cmd_qsize":      0,
        })
    except Exception as e:
        _log.error(f"DIAG-IPC 실패: {e}")

    try:
        emit("DIAG-TELEGRAM", {
            "enabled":              telegram._enabled,
            "queue_size":           telegram._queue.qsize(),
            "consecutive_failures": telegram._consecutive_failures,
            "worker_alive":         telegram._worker_thread.is_alive(),
        })
    except Exception as e:
        _log.error(f"DIAG-TELEGRAM 실패: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 자동 성능 감지
# ══════════════════════════════════════════════════════════════════════════════

def _handle_auto_perf(result_queue, ipc_counters, duration_sec: float):
    from ipc.messages import PerfMeasurement
    import psutil
    try:
        proc = psutil.Process(os.getpid())
        proc.cpu_percent(interval=None)
        time.sleep(min(duration_sec, 10.0))
        cpu = proc.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        # 간단한 권고: CPU > 70% 시 interval 올리기, > 50% 시 scale_factor 낮추기
        interval = 200 if cpu < 50 else (500 if cpu < 70 else 1000)
        scale = 1.0 if cpu < 50 else (0.5 if cpu < 70 else 0.25)
        _put(result_queue,
             PerfMeasurement(recommended_interval=interval, recommended_scale=scale,
                             cpu_percent=cpu, ram_percent=ram),
             ipc_counters)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════════════════════════════

def _update_signoff_media_names(signoff_mgr, rois):
    media_map = {roi.label: roi.media_name for roi in rois}
    signoff_mgr.update_media_names(media_map)
