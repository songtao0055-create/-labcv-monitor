"""
视频流处理模块 —— 后台线程读取视频帧 → 瞌睡检测 + 火灾检测 → 更新共享状态
支持: USB 摄像头 / RTSP 网络流 / 本地视频文件
"""

import time
import threading
import logging
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from .config import drowsiness_cfg, StreamConfig
from .detector import DrowsinessDetector, DrowsinessResult, FaceMetrics
from ..fire.detector import FireDetector, FireResult

logger = logging.getLogger(__name__)


class VideoProcessor:
    """
    视频流处理器，在后台线程中持续读取帧并执行瞌睡检测 + 火灾检测。

    用法:
        proc = VideoProcessor(StreamConfig(source="rtsp://..."))
        proc.start()
        # ... 随时读取 proc.latest_result / proc.latest_fire_result
        proc.stop()
    """

    def __init__(self, config: StreamConfig | None = None):
        self.cfg = config or StreamConfig()
        self._drowsiness_detector = DrowsinessDetector()

        # 火灾检测器 (模型不存在时降级，不阻塞启动)
        try:
            self._fire_detector = FireDetector()
            self._fire_enabled = True
            logger.info("火灾检测模块已加载")
        except FileNotFoundError as e:
            self._fire_detector = None
            self._fire_enabled = False
            logger.warning(f"火灾检测模型未找到，火灾检测已禁用: {e}")

        # 共享状态 (线程安全)
        self._lock = threading.Lock()
        self._latest_result = self._empty_drowsiness_result()
        self._latest_fire_result = FireResult(message="等待视频流连接...")
        self._history: deque[DrowsinessResult] = deque(maxlen=500)
        self._alert_history: deque[DrowsinessResult] = deque(maxlen=200)
        self._fire_history: deque[FireResult] = deque(maxlen=500)
        self._fire_alert_history: deque[FireResult] = deque(maxlen=200)
        self._fps_actual: float = 0.0
        self._frame_count: int = 0
        self._is_running: bool = False
        self._is_connected: bool = False

        # 后台线程
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台处理线程"""
        if self._is_running:
            logger.warning("VideoProcessor 已在运行中")
            return
        self._stop_event.clear()
        self._drowsiness_detector.reset()
        if self._fire_detector:
            self._fire_detector.reset()
        self._thread = threading.Thread(
            target=self._loop, name="video-processor", daemon=True
        )
        self._thread.start()
        self._is_running = True
        logger.info(f"VideoProcessor 启动, source={self.cfg.source}")

    def stop(self) -> None:
        """停止后台处理并释放资源"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._is_running = False
        logger.info("VideoProcessor 已停止")

    # ------------------------------------------------------------------
    # 共享状态读取 (线程安全)
    # ------------------------------------------------------------------

    @property
    def latest_result(self) -> DrowsinessResult:
        with self._lock:
            return self._latest_result

    @property
    def latest_fire_result(self) -> FireResult:
        with self._lock:
            return self._latest_fire_result

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    @property
    def fire_enabled(self) -> bool:
        return self._fire_enabled

    @property
    def fps_actual(self) -> float:
        with self._lock:
            return self._fps_actual

    @property
    def frame_count(self) -> int:
        with self._lock:
            return self._frame_count

    def get_history(self, limit: int = 20) -> list[dict]:
        """获取最近 N 条检测记录，用于前端展示"""
        with self._lock:
            items = list(self._history)[-limit:]
        return [_drowsiness_result_to_dict(r) for r in items]

    def get_alerts(self, limit: int = 20) -> list[dict]:
        """获取最近 N 条瞌睡告警记录"""
        with self._lock:
            items = list(self._alert_history)[-limit:]
        return [_drowsiness_result_to_dict(r) for r in items]

    def get_fire_history(self, limit: int = 20) -> list[dict]:
        """获取最近 N 条火灾检测记录"""
        with self._lock:
            items = list(self._fire_history)[-limit:]
        return [_fire_result_to_dict(r) for r in items]

    def get_fire_alerts(self, limit: int = 20) -> list[dict]:
        """获取最近 N 条火灾告警记录"""
        with self._lock:
            items = list(self._fire_alert_history)[-limit:]
        return [_fire_result_to_dict(r) for r in items]

    def snapshot(self) -> dict:
        """返回当前检测状态快照，供 GET /api/status 调用"""
        r = self.latest_result
        fr = self.latest_fire_result
        base = {
            "is_running": self._is_running,
            "is_connected": self._is_connected,
            "fps_actual": round(self._fps_actual, 1),
            "frame_count": self._frame_count,
            "source": self.cfg.source,
            "fire_enabled": self._fire_enabled,
            **_drowsiness_result_to_dict(r),
        }
        base["fire"] = _fire_result_to_dict(fr)
        return base

    # ------------------------------------------------------------------
    # 内部循环
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        cap = None

        while not self._stop_event.is_set():
            # 建立连接
            if cap is None:
                cap = self._open_source()
                if cap is None:
                    logger.warning(f"无法打开视频源, {self.cfg.reconnect_delay}s 后重试...")
                    self._stop_event.wait(self.cfg.reconnect_delay)
                    continue
                with self._lock:
                    self._is_connected = True
                self._drowsiness_detector.reset()
                if self._fire_detector:
                    self._fire_detector.reset()
                logger.info("视频源已连接")

            ret, frame = cap.read()
            if not ret:
                logger.warning("读取帧失败, 尝试重连...")
                cap.release()
                cap = None
                with self._lock:
                    self._is_connected = False
                self._stop_event.wait(self.cfg.reconnect_delay)
                continue

            # 缩放至处理分辨率
            frame = self._resize(frame)
            fps = self.cfg.fps

            # 瞌睡检测推理
            t0 = time.perf_counter()
            drowsiness_result = self._drowsiness_detector.process_frame(frame, fps=fps)

            # 火灾检测推理
            fire_result = FireResult(message="火灾检测未启用")
            if self._fire_detector:
                fire_result = self._fire_detector.process_frame(frame, fps=fps)

            elapsed = time.perf_counter() - t0

            # 更新共享状态
            with self._lock:
                self._latest_result = drowsiness_result
                self._latest_fire_result = fire_result
                self._history.append(drowsiness_result)
                self._fire_history.append(fire_result)
                self._frame_count += 1
                if elapsed > 0:
                    self._fps_actual = 0.9 * self._fps_actual + 0.1 * (1.0 / max(elapsed, 0.001))
                if drowsiness_result.is_drowsy:
                    self._alert_history.append(drowsiness_result)
                if fire_result.level != "normal":
                    self._fire_alert_history.append(fire_result)

        # 清理
        if cap is not None:
            cap.release()
        with self._lock:
            self._is_connected = False
        logger.info("视频处理循环退出")

    def _open_source(self) -> cv2.VideoCapture | None:
        src = self.cfg.source
        if src.isdigit():
            cap = cv2.VideoCapture(int(src))
        elif Path(src).exists():
            cap = cv2.VideoCapture(src)
        else:
            cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _resize(self, frame: np.ndarray) -> np.ndarray:
        w, h = self.cfg.frame_width, self.cfg.frame_height
        if frame.shape[1] != w or frame.shape[0] != h:
            return cv2.resize(frame, (w, h))
        return frame

    @staticmethod
    def _empty_drowsiness_result() -> DrowsinessResult:
        return DrowsinessResult(
            metrics=FaceMetrics(face_detected=False),
            message="等待视频流连接...",
        )


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

def _drowsiness_result_to_dict(r: DrowsinessResult) -> dict:
    m = r.metrics
    p = r.pose
    return {
        "timestamp": r.timestamp,
        "is_drowsy": r.is_drowsy,
        "level": r.level,
        "confidence": r.confidence,
        "alert_type": r.alert_type,
        "message": r.message,
        "face_detected": m.face_detected,
        "person_detected": p.person_detected,
        "ear_avg": round(m.ear_avg, 4),
        "mar": round(m.mar, 4),
        "head_pitch": round(m.head_pitch, 1),
        "head_yaw": round(m.head_yaw, 1),
        "head_roll": round(m.head_roll, 1),
        "eyes_closed_sec": r.eyes_closed_sec,
        "head_droop_sec": r.head_droop_sec,
        "posture_sleep_sec": r.posture_sleep_sec,
        "head_drop_ratio": p.head_drop_ratio,
        "torso_angle": p.torso_angle,
    }


def _fire_result_to_dict(r: FireResult) -> dict:
    return {
        "timestamp": r.timestamp,
        "has_fire": r.has_fire,
        "has_smoke": r.has_smoke,
        "level": r.level,
        "confidence": r.confidence,
        "fire_count": r.fire_count,
        "smoke_count": r.smoke_count,
        "fire_alert_sec": r.fire_alert_sec,
        "smoke_alert_sec": r.smoke_alert_sec,
        "message": r.message,
        "detections": [
            {
                "class": d.class_name,
                "confidence": d.confidence,
                "bbox": list(d.bbox),
            }
            for d in r.detections
        ],
    }
