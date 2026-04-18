"""
SharedMemory 상태 버퍼 래퍼
docs_ipc_spec.md §1.2 레이아웃 구현 (64 bytes)

offset  size  type        field             direction
  0      4    uint32 LE   magic             고정 0x4B425332 ('KBS2')
  4      4    uint32 LE   version           고정 1
  8      8    uint64 LE   write_seq         쓸 때마다 +1 (디버깅)
 16      1    uint8       detection_enabled 양방향 0/1
 17      1    uint8       mute              양방향 0/1
 18      1    uint8       volume            양방향 0~100
 19      1    uint8       reserved          패딩
 20      4    float32 LE  level_l           Detection→UI, dB -60~0
 24      4    float32 LE  level_r           Detection→UI, dB -60~0
 28      4    uint32 LE   reserved          향후 확장
 32     32    bytes       reserved          향후 확장
총 64 bytes
"""
import struct
from multiprocessing import Lock
from multiprocessing.shared_memory import SharedMemory

_MAGIC = 0x4B425332     # 'KBS2'
_VERSION = 1
TOTAL_SIZE = 64
SHM_NAME = "kbs_state_v2"

# struct offsets
_OFF_MAGIC = 0
_OFF_VERSION = 4
_OFF_WRITE_SEQ = 8
_OFF_DET_EN = 16
_OFF_MUTE = 17
_OFF_VOLUME = 18
_OFF_LEVEL_L = 20
_OFF_LEVEL_R = 24


class SharedStateBuffer:
    """상태 SharedMemory 래퍼. 동시 쓰기는 multiprocessing.Lock 으로 보호."""

    def __init__(self, create: bool = False, name: str = SHM_NAME,
                 lock: "Lock | None" = None):
        self._name = name
        self._lock = lock  # main 프로세스에서 생성해 전달
        if create:
            self._shm = SharedMemory(name=name, create=True, size=TOTAL_SIZE)
            self._buf = self._shm.buf
            self._init_header()
        else:
            self._shm = SharedMemory(name=name, create=False)
            self._buf = self._shm.buf

    def _init_header(self) -> None:
        struct.pack_into("<II", self._buf, _OFF_MAGIC, _MAGIC, _VERSION)
        struct.pack_into("<Q", self._buf, _OFF_WRITE_SEQ, 0)
        self._buf[_OFF_DET_EN] = 1
        self._buf[_OFF_MUTE] = 0
        self._buf[_OFF_VOLUME] = 80
        self._buf[19] = 0
        struct.pack_into("<ff", self._buf, _OFF_LEVEL_L, -60.0, -60.0)

    def is_ready(self) -> bool:
        """magic 검증. 0이면 Detection 초기화 미완료."""
        magic = struct.unpack_from("<I", self._buf, _OFF_MAGIC)[0]
        return magic == _MAGIC

    def _bump_seq(self) -> None:
        seq = struct.unpack_from("<Q", self._buf, _OFF_WRITE_SEQ)[0]
        struct.pack_into("<Q", self._buf, _OFF_WRITE_SEQ, seq + 1)

    # ── 쓰기 (Lock 보호) ──────────────────────────

    def _write(self, fn) -> None:
        if self._lock:
            with self._lock:
                fn()
                self._bump_seq()
        else:
            fn()
            self._bump_seq()

    def set_detection_enabled(self, value: bool) -> None:
        self._write(lambda: self._buf.__setitem__(_OFF_DET_EN, int(value)))

    def set_mute(self, value: bool) -> None:
        self._write(lambda: self._buf.__setitem__(_OFF_MUTE, int(value)))

    def set_volume(self, value: int) -> None:
        self._write(lambda: self._buf.__setitem__(_OFF_VOLUME, max(0, min(100, value))))

    def set_levels(self, level_l: float, level_r: float) -> None:
        def _set():
            struct.pack_into("<ff", self._buf, _OFF_LEVEL_L,
                             max(-60.0, min(0.0, level_l)),
                             max(-60.0, min(0.0, level_r)))
        self._write(_set)

    # ── 읽기 (lock-free 허용) ────────────────────

    def get_detection_enabled(self) -> bool:
        return bool(self._buf[_OFF_DET_EN])

    def get_mute(self) -> bool:
        return bool(self._buf[_OFF_MUTE])

    def get_volume(self) -> int:
        return int(self._buf[_OFF_VOLUME])

    def get_levels(self) -> "tuple[float, float]":
        return struct.unpack_from("<ff", self._buf, _OFF_LEVEL_L)

    def get_write_seq(self) -> int:
        return struct.unpack_from("<Q", self._buf, _OFF_WRITE_SEQ)[0]

    # ── 공통 ─────────────────────────────────────

    def close(self) -> None:
        self._buf.release()
        self._shm.close()

    def unlink(self) -> None:
        self._shm.unlink()
