"""
陌生人检测配置
"""
from dataclasses import dataclass


@dataclass
class StrangerConfig:
    """陌生人检测参数"""

    # 人脸角度过滤：偏航角绝对值超过此阈值 → 跳过匹配（侧脸不可靠）
    max_yaw_degrees: float = 45.0

    # 人脸最小尺寸（像素），太小的人脸不比对（远距离人脸特征不足）
    min_face_width: int = 40

    # 匹配阈值：余弦相似度 > 此值判定为已注册用户（RTSP低分辨率适当放宽）
    match_threshold: float = 0.40

    # 多帧确认：连续未匹配帧数超过此值才触发陌生人告警
    stranger_confirm_frames: int = 20

    # 匹配确认：连续匹配帧数超过此值才认为身份稳定（防止闪烁切换）
    match_confirm_frames: int = 3

    # 计数器衰减：人脸丢失时每帧减 N（防止快速切换）
    counter_decay: int = 3

    # 计数器上限
    counter_max: int = 300


stranger_cfg = StrangerConfig()
