"""
瞌睡检测配置 —— 所有阈值、MediaPipe 关键点索引、模型路径
"""

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"


@dataclass
class DrowsinessConfig:
    """瞌睡检测参数配置，阈值可根据实际场景微调"""

    # === 眼部纵横比 (EAR) ===
    ear_threshold: float = 0.18        # EAR 低于此值判定为闭眼
    ear_frames_consecutive: int = 80   # 连续闭眼帧数触发告警 (约8秒@10fps)

    # === 嘴部纵横比 (MAR) ===
    mar_threshold: float = 0.70        # MAR 高于此值判定为打哈欠

    # === 头部姿态 (单位: 度) ===
    head_pitch_droop: float = -45.0    # 俯仰角低于此值判定为低头/瞌睡（需明显低头）
    head_droop_frames: int = 80       # 连续低头帧数触发告警 (约8秒@10fps)
    head_roll_tilt: float = 15.0       # 头部侧倾超过此角度 → 疑似打瞌睡

    # === 置信度 (放宽以提高检出) ===
    face_detection_confidence: float = 0.6   # 提高以减少非人脸区域的误检
    pose_detection_confidence: float = 0.8   # 姿态检测置信度 (提高以减少误检)

    # === 趴睡检测 (人体姿态) ===
    head_below_shoulder_ratio: float = -0.4   # 头部需比肩低40%躯干长度以上才判趴睡
    torso_slouch_angle: float = 45.0           # 躯干前倾角超过此值 → 坐姿瞌睡
    pose_sleep_frames: int = 200               # 连续趴睡姿态帧数触发告警 (约20秒@10fps)

    # === MediaPipe Pose Landmarker 关键点索引 ===
    # 0:鼻子  7-10:耳朵/嘴  11-12:肩膀  23-24:髋部
    pose_nose_idx: int = 0
    pose_left_shoulder_idx: int = 11
    pose_right_shoulder_idx: int = 12
    pose_left_hip_idx: int = 23
    pose_right_hip_idx: int = 24

    # === MediaPipe 468 点 Face Mesh 关键点索引 ===
    # 左眼: 外角33, 内角133, 上158/159, 下153/145
    left_eye_indices: tuple = (33, 133, 158, 153, 159, 145)
    # 右眼: 外角362, 内角263, 上385/386, 下380/374
    right_eye_indices: tuple = (362, 263, 385, 380, 386, 374)
    # 嘴: 左角61, 右角291, 上唇13, 下唇14
    mouth_outer_indices: tuple = (61, 291, 13, 14)

    # === 头部姿态 2D→3D 对应点 ===
    # 选用的 2D 关键点索引
    head_pose_2d_indices: tuple = (1, 152, 33, 263, 61, 291)
    # 对应的 3D 通用人脸模型坐标 (鼻尖, 下巴, 左眼角, 右眼角, 左嘴角, 右嘴角)
    head_pose_3d_points: tuple = (
        (0.0,   0.0,   0.0),     # 鼻尖
        (0.0,  -63.6, -12.5),    # 下巴
        (-30.0, 20.0, -15.0),    # 左眼左角
        (30.0,  20.0, -15.0),    # 右眼右角
        (-25.0, -25.0, -10.0),   # 左嘴角
        (25.0,  -25.0, -10.0),   # 右嘴角
    )


@dataclass
class StreamConfig:
    """视频流配置"""
    source: str = "0"             # 默认摄像头; 支持 RTSP URL / 文件路径 / 数字索引
    fps: int = 30                 # 处理帧率
    frame_width: int = 640        # 处理分辨率宽
    frame_height: int = 480       # 处理分辨率高
    reconnect_delay: float = 5.0  # RTSP 断线重连间隔 (秒)


# 全局单例
drowsiness_cfg = DrowsinessConfig()
