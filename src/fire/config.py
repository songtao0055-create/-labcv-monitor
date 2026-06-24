"""
火灾检测配置 —— YOLOv8 火焰/烟雾检测阈值与参数
"""

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"


@dataclass
class FireConfig:
    """火灾检测参数配置"""

    # === YOLO 模型 ===
    model_path: str = str(MODELS_DIR / "fire-yolov8s.pt")  # v8s 准确率远好于 nano
    fire_confidence: float = 0.6        # 火焰单帧置信度阈值
    smoke_confidence: float = 0.80       # 烟雾单帧置信度阈值 (实验室场景需极高以避免误报)
    model_iou: float = 0.5              # NMS IOU 阈值

    # === 多帧滑动窗口投票 ===
    fire_window_size: int = 30           # 滑动窗口大小 (检测次数)
    fire_min_votes: int = 15             # 窗口内最少命中次数 → 火焰告警
    smoke_window_size: int = 30          # 烟雾滑动窗口
    smoke_min_votes: int = 25            # 窗口内最少命中次数 → 烟雾告警

    # === 火焰/烟雾类别 ID ===
    fire_class_id: int = 0
    smoke_class_id: int = 1

    # === 视频分析参数 ===
    frame_skip: int = 3                  # 每 N 帧跑一次火灾检测（与滑动窗口配合）
    detection_width: int = 480           # 检测输入分辨率


# 全局单例
fire_cfg = FireConfig()
