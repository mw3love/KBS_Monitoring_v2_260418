"""
감지영역(ROI) 관리 모듈
"""
from dataclasses import dataclass
from typing import List


@dataclass
class ROI:
    """단일 감지영역 정보"""
    label: str         # 표시 이름 (V1, A1 등)
    media_name: str    # 매체명
    x: int
    y: int
    w: int
    h: int
    roi_type: str = "video"  # "video" 또는 "audio"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "media_name": self.media_name,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "roi_type": self.roi_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ROI":
        return cls(
            label=d.get("label", ""),
            media_name=d.get("media_name", ""),
            x=d.get("x", 0),
            y=d.get("y", 0),
            w=d.get("w", 100),
            h=d.get("h", 100),
            roi_type=d.get("roi_type", "video"),
        )

    def clamp(self, max_w: int, max_h: int):
        """영역이 화면 밖으로 나가지 않도록 보정"""
        self.x = max(0, min(self.x, max_w - 1))
        self.y = max(0, min(self.y, max_h - 1))
        self.w = max(1, min(self.w, max_w - self.x))
        self.h = max(1, min(self.h, max_h - self.y))


class ROIManager:
    """감지영역 목록을 관리하는 클래스"""

    def __init__(self):
        self._video_rois: List[ROI] = []
        self._audio_rois: List[ROI] = []

    @property
    def video_rois(self) -> List[ROI]:
        return self._video_rois

    @property
    def audio_rois(self) -> List[ROI]:
        return self._audio_rois

    def _relabel_video(self):
        for i, roi in enumerate(self._video_rois):
            roi.label = f"V{i + 1}"

    def _relabel_audio(self):
        for i, roi in enumerate(self._audio_rois):
            roi.label = f"A{i + 1}"

    def to_dict(self) -> dict:
        return {
            "video": [r.to_dict() for r in self._video_rois],
            "audio": [r.to_dict() for r in self._audio_rois],
        }

    def from_dict(self, d: dict):
        self._video_rois = [ROI.from_dict(r) for r in d.get("video", [])]
        self._audio_rois = [ROI.from_dict(r) for r in d.get("audio", [])]

    def replace_video_rois(self, rois: List[ROI]):
        """영상 감지영역 목록을 통째로 교체 (편집기에서 사용)"""
        self._video_rois = list(rois)
        self._relabel_video()

    def replace_audio_rois(self, rois: List[ROI]):
        """오디오 감지영역 목록을 통째로 교체 (편집기에서 사용)"""
        self._audio_rois = list(rois)
        self._relabel_audio()

    def clear(self):
        self._video_rois.clear()
        self._audio_rois.clear()
