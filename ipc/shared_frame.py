"""
SharedMemory 프레임 버퍼 래퍼
docs_ipc_spec.md §1.1 레이아웃 구현

헤더 (32 bytes):
  0  uint64 LE  seq_no      홀수=쓰기 중, 짝수=안정
  8  float64 LE timestamp
 16  uint32 LE  width
 20  uint32 LE  height
 24  uint32 LE  channels    3 고정 (BGR)
 28  uint32 LE  flags       bit0=scale 적용, bit1=no-signal
픽셀 (6,220,800 bytes):  1920×1080×3 고정 할당
총 6,220,832 bytes
"""
import struct
import numpy as np
from multiprocessing.shared_memory import SharedMemory

_HEADER_FMT = "<QdIIII"   # seq_no, timestamp, width, height, channels, flags
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)   # 32 bytes
_MAX_W = 1920
_MAX_H = 1080
_MAX_CH = 3
_PIXEL_SIZE = _MAX_W * _MAX_H * _MAX_CH       # 6,220,800
TOTAL_SIZE = _HEADER_SIZE + _PIXEL_SIZE       # 6,220,832

SHM_NAME = "kbs_frame_v2"


class SharedFrameBuffer:
    """프레임 SharedMemory 래퍼. Detection은 write_frame, UI는 read_frame 사용."""

    def __init__(self, create: bool = False, name: str = SHM_NAME):
        self._name = name
        if create:
            try:
                self._shm = SharedMemory(name=name, create=True, size=TOTAL_SIZE)
            except FileExistsError:
                # Windows: 직전 unlink 후 핸들 반환 전 재생성 시도 → 기존 것 재사용
                self._shm = SharedMemory(name=name, create=False)
            self._buf = self._shm.buf
            # 헤더 초기화 (seq_no=0, 나머지 0)
            struct.pack_into(_HEADER_FMT, self._buf, 0, 0, 0.0, 0, 0, _MAX_CH, 0)
        else:
            self._shm = SharedMemory(name=name, create=False)
            self._buf = self._shm.buf

    # ── Detection 측 ──────────────────────────────

    def write_frame(self, frame: np.ndarray, flags: int = 0) -> None:
        """Lamport seq 기반 tearing-free 쓰기."""
        import time
        h, w = frame.shape[:2]
        ch = frame.shape[2] if frame.ndim == 3 else 1
        nbytes = w * h * ch

        # seq_no 홀수로 → 픽셀 복사 → seq_no 짝수로
        old_seq = struct.unpack_from("<Q", self._buf, 0)[0]
        struct.pack_into("<Q", self._buf, 0, old_seq | 1)  # 홀수 = 쓰기 중

        struct.pack_into(_HEADER_FMT, self._buf, 0,
                         old_seq | 1,   # 홀수 유지
                         time.time(),
                         w, h, ch, flags)

        self._buf[_HEADER_SIZE: _HEADER_SIZE + nbytes] = frame.tobytes()

        # 짝수로 완료 (이전 짝수 +2)
        new_seq = (old_seq & ~1) + 2
        struct.pack_into("<Q", self._buf, 0, new_seq)

    # ── UI 측 ────────────────────────────────────

    def read_frame(self) -> "np.ndarray | None":
        """
        Lamport seq 기반 tearing-free 읽기.
        쓰기 중이거나 읽는 사이 seq 변경이면 None 반환 (최악 1프레임 스킵 허용).
        반환값은 항상 .copy() 된 독립 배열.
        """
        s1 = struct.unpack_from("<Q", self._buf, 0)[0]
        if s1 & 1:          # 홀수 = 쓰기 중
            return None

        seq, ts, w, h, ch, flags = struct.unpack_from(_HEADER_FMT, self._buf, 0)
        if w == 0 or h == 0:
            return None

        nbytes = w * h * ch
        raw = bytes(self._buf[_HEADER_SIZE: _HEADER_SIZE + nbytes])

        s2 = struct.unpack_from("<Q", self._buf, 0)[0]
        if s1 != s2:        # 읽는 사이 seq 변경
            return None

        arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, ch)
        return arr.copy()   # SharedMemory 해제 후 원본 참조 무효화 방지

    def read_meta(self) -> dict:
        """헤더만 읽어 width/height/seq_no/flags 반환."""
        seq, ts, w, h, ch, flags = struct.unpack_from(_HEADER_FMT, self._buf, 0)
        return {"seq_no": seq, "timestamp": ts, "width": w, "height": h,
                "channels": ch, "flags": flags}

    def clear_frame(self) -> None:
        """프레임을 비워 read_frame()이 None을 반환하게 함 (소스 전환 시 사용)."""
        old_seq = struct.unpack_from("<Q", self._buf, 0)[0]
        new_seq = (old_seq & ~1) + 2
        struct.pack_into(_HEADER_FMT, self._buf, 0, new_seq, 0.0, 0, 0, _MAX_CH, 0)

    # ── 공통 ──────────────────────────────────────

    def close(self) -> None:
        self._buf.release()
        self._shm.close()

    def unlink(self) -> None:
        self._shm.unlink()
