"""
火灾检测核心模块
基于 YOLOv8 检测火焰和烟雾，滑动窗口投票机制
"""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field

import cv2
import numpy as np
from ultralytics import YOLO

from .config import fire_cfg

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class FireDetection:
    """单个检测目标"""
    bbox: tuple[int, int, int, int]    # x1, y1, x2, y2
    confidence: float
    class_id: int
    class_name: str                     # "fire" / "smoke"


@dataclass
class FireResult:
    """单帧火灾检测输出"""
    timestamp: float = field(default_factory=time.time)
    has_fire: bool = False
    has_smoke: bool = False
    level: str = "normal"               # normal / warning / critical
    confidence: float = 0.0
    detections: list[FireDetection] = field(default_factory=list)
    fire_count: int = 0
    smoke_count: int = 0
    fire_alert_sec: float = 0.0
    smoke_alert_sec: float = 0.0
    message: str = ""


# ---------------------------------------------------------------------------
# 检测器
# ---------------------------------------------------------------------------


class FireDetector:
    """火灾检测器 —— YOLOv8 火焰/烟雾检测 + 滑动窗口投票"""

    def __init__(self):
        cfg = fire_cfg
        self._fire_conf = cfg.fire_confidence
        self._smoke_conf = cfg.smoke_confidence
        self._iou = cfg.model_iou
        self._frame_skip = cfg.frame_skip
        self._detection_width = cfg.detection_width
        self._fire_id = cfg.fire_class_id
        self._smoke_id = cfg.smoke_class_id

        # 滑动窗口参数
        self._fire_window = cfg.fire_window_size
        self._fire_votes = cfg.fire_min_votes
        self._smoke_window = cfg.smoke_window_size
        self._smoke_votes = cfg.smoke_min_votes

        # 滑动窗口历史: 记录最近 N 次检测结果 (1=命中, 0=未命中)
        self._fire_history: deque[int] = deque(maxlen=self._fire_window)
        self._smoke_history: deque[int] = deque(maxlen=self._smoke_window)

        self._frame_idx: int = 0
        self._fps: float = 30.0

        # 加载模型
        model_path = cfg.model_path
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"火灾检测模型未找到: {model_path}\n"
                "请运行: python download_model.py  下载所有模型\n"
                "或下载 YOLO 火焰检测权重文件到 models/ 目录"
            )
        self._model = YOLO(model_path)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray, fps: float = 30.0) -> FireResult:
        """处理一帧图像，返回火灾检测结果"""
        self._fps = fps
        self._frame_idx += 1

        # 跳帧以减少计算量
        if self._frame_idx % self._frame_skip != 0:
            return self._build_result()

        # 缩放到检测分辨率
        h, w = frame.shape[:2]
        scale = self._detection_width / w
        if scale != 1.0:
            new_h = int(h * scale)
            frame = cv2.resize(frame, (self._detection_width, new_h))

        # YOLO 推理: 用两个类别中较低的阈值, 然后在代码中按类过滤
        min_conf = min(self._fire_conf, self._smoke_conf)
        results = self._model(frame, conf=min_conf, iou=self._iou, verbose=False)

        detections: list[FireDetection] = []
        has_fire = False
        has_smoke = False

        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])

                if cls_id == self._fire_id:
                    if conf < self._fire_conf:
                        continue
                    class_name = "fire"
                    has_fire = True
                elif cls_id == self._smoke_id:
                    if conf < self._smoke_conf:
                        continue
                    class_name = "smoke"
                    has_smoke = True
                else:
                    continue

                xyxy = box.xyxy[0].tolist()
                bbox = (int(xyxy[0] / scale), int(xyxy[1] / scale),
                        int(xyxy[2] / scale), int(xyxy[3] / scale))

                detections.append(FireDetection(
                    bbox=bbox, confidence=round(conf, 4),
                    class_id=cls_id, class_name=class_name,
                ))

        # 记录到滑动窗口
        self._fire_history.append(1 if has_fire else 0)
        self._smoke_history.append(1 if has_smoke else 0)

        return self._build_result(detections)

    def reset(self) -> None:
        self._fire_history.clear()
        self._smoke_history.clear()
        self._frame_idx = 0

    def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _build_result(self, detections: list[FireDetection] | None = None) -> FireResult:
        if detections is None:
            detections = []

        fps = max(self._fps, 1.0)
        fire_votes = sum(self._fire_history)
        smoke_votes = sum(self._smoke_history)

        fire_alert = fire_votes >= self._fire_votes
        smoke_alert = smoke_votes >= self._smoke_votes

        has_fire = any(d.class_name == "fire" for d in detections)
        has_smoke = any(d.class_name == "smoke" for d in detections)

        fire_confs = [d.confidence for d in detections if d.class_name == "fire"]
        smoke_confs = [d.confidence for d in detections if d.class_name == "smoke"]
        max_conf = max(fire_confs + smoke_confs) if (fire_confs or smoke_confs) else 0.0

        # 告警持续时间估算: 命中帧数 × 帧间隔
        fire_sec = fire_votes * self._frame_skip / fps
        smoke_sec = smoke_votes * self._frame_skip / fps

        # 判定 (仅通过滑动窗口投票触发告警, 避免单帧误报)
        if fire_alert and smoke_alert:
            level = "critical"
            message = f"火灾告警: 火焰+烟雾, 请立即处理!"
        elif fire_alert:
            level = "critical"
            message = f"火灾告警: 检测到火焰, 请立即处理!"
        elif smoke_alert:
            level = "warning"
            message = f"烟雾告警: 检测到烟雾, 请注意"
        else:
            level = "normal"
            message = ""

        return FireResult(
            timestamp=time.time(),
            has_fire=has_fire or fire_alert,
            has_smoke=has_smoke or smoke_alert,
            level=level,
            confidence=round(max_conf, 4),
            detections=[d for d in detections if d.class_name in ("fire", "smoke")],
            fire_count=len(fire_confs),
            smoke_count=len(smoke_confs),
            fire_alert_sec=round(fire_sec, 2),
            smoke_alert_sec=round(smoke_sec, 2),
            message=message,
        )

    def annotate_frame(self, frame: np.ndarray, result: FireResult) -> np.ndarray:
        """在帧上绘制火焰/烟雾检测框"""
        for d in result.detections:
            x1, y1, x2, y2 = d.bbox
            if d.class_name == "fire":
                color = (0, 0, 255)        # 红色框 - 火焰
                label = f"FIRE {d.confidence:.2f}"
            else:
                color = (128, 128, 128)     # 灰色框 - 烟雾
                label = f"SMOKE {d.confidence:.2f}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        if result.level != "normal":
            text = result.message
            y0 = frame.shape[0] - 60
            cv2.putText(frame, text, (10, y0),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        return frame
