"""
瞌睡检测核心模块
集成 MediaPipe Face Landmarker + Pose Landmarker:
  人脸可见 → EAR / MAR / 头部姿态分析
  人脸不可见 → 身体姿态分析 (趴桌睡检测)
"""

from __future__ import annotations

import time
import math
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from dataclasses import dataclass, field

from .config import drowsiness_cfg

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_FACE_MODEL = _MODEL_DIR / "face_landmarker.task"
_POSE_MODEL = _MODEL_DIR / "pose_landmarker.task"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class FaceMetrics:
    """单帧面部指标"""
    ear_left: float = 0.0
    ear_right: float = 0.0
    ear_avg: float = 0.0
    mar: float = 0.0
    head_pitch: float = 0.0
    head_yaw: float = 0.0
    head_roll: float = 0.0
    face_detected: bool = False
    face_bbox: tuple = ()  # (x, y, w, h) 人脸边界框，供陌生人检测使用

    @property
    def eyes_closed(self) -> bool:
        return self.ear_avg < drowsiness_cfg.ear_threshold

    @property
    def yawning(self) -> bool:
        return self.mar > drowsiness_cfg.mar_threshold

    @property
    def head_drooping(self) -> bool:
        return self.head_pitch < drowsiness_cfg.head_pitch_droop


@dataclass
class PoseMetrics:
    """单帧身体姿态指标"""
    person_detected: bool = False
    head_below_shoulder: bool = False
    head_drop_ratio: float = 0.0
    torso_angle: float = 0.0
    torso_slouched: bool = False       # 躯干前倾超过阈值


@dataclass
class DrowsinessResult:
    """单帧检测输出"""
    timestamp: float = field(default_factory=time.time)
    is_drowsy: bool = False
    level: str = "normal"
    confidence: float = 0.0
    alert_type: str = ""            # eyes_closed / yawning / head_droop / posture_sleep / combined
    metrics: FaceMetrics = field(default_factory=FaceMetrics)
    pose: PoseMetrics = field(default_factory=PoseMetrics)
    eyes_closed_sec: float = 0.0
    head_droop_sec: float = 0.0
    posture_sleep_sec: float = 0.0
    message: str = ""


# ---------------------------------------------------------------------------
# 检测器
# ---------------------------------------------------------------------------

class DrowsinessDetector:
    """瞌睡检测器 —— Face Landmarker + Pose Landmarker 双模型"""

    def __init__(self, running_mode: str = "video"):
        if running_mode not in ("video", "image"):
            raise ValueError(f"running_mode 必须是 'video' 或 'image', 收到: {running_mode}")
        self._running_mode = running_mode

        cfg = drowsiness_cfg
        # 面部阈值
        self.ear_threshold = cfg.ear_threshold
        self.ear_consec = cfg.ear_frames_consecutive
        self.mar_threshold = cfg.mar_threshold
        self.head_droop_threshold = cfg.head_pitch_droop
        self.head_droop_consec = cfg.head_droop_frames
        self.head_roll_tilt = cfg.head_roll_tilt
        # 姿态阈值
        self.head_below_ratio = cfg.head_below_shoulder_ratio
        self.torso_slouch_angle = cfg.torso_slouch_angle
        self.pose_sleep_frames = cfg.pose_sleep_frames

        # 图像增强: CLAHE 自适应直方图均衡 (处理偏暗/偏亮图片)
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        # 侧脸检测 fallback: OpenCV profile face cascade (MediaPipe 对侧脸弱)
        _cascade_path = cv2.data.haarcascades + "haarcascade_profileface.xml"
        self._profile_cascade = cv2.CascadeClassifier(_cascade_path)
        _front_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._front_cascade = cv2.CascadeClassifier(_front_path)
        _eye_path = cv2.data.haarcascades + "haarcascade_eye.xml"
        self._eye_cascade = cv2.CascadeClassifier(_eye_path)

        # --- Face Landmarker (video 模式, 主力) ---
        if not _FACE_MODEL.exists():
            raise FileNotFoundError(f"人脸模型未找到: {_FACE_MODEL}\n请运行: python download_model.py")
        self._face_landmarker = self._create_face_landmarker()

        # --- Face Landmarker (image 模式, 侧脸 fallback) ---
        self._face_landmarker_img = self._create_face_landmarker_image()

        # --- Pose Landmarker ---
        if not _POSE_MODEL.exists():
            raise FileNotFoundError(f"姿态模型未找到: {_POSE_MODEL}\n请运行: python download_model.py")
        self._pose_landmarker = self._create_pose_landmarker()

        # 关键点索引
        self.left_eye_idx = cfg.left_eye_indices
        self.right_eye_idx = cfg.right_eye_indices
        self.mouth_idx = cfg.mouth_outer_indices
        self.hp_2d_idx = cfg.head_pose_2d_indices
        self.hp_3d = np.array(cfg.head_pose_3d_points, dtype=np.float64)

        # 累计状态 — 多人脸独立跟踪
        self._face_states: dict[str, dict] = {}  # face_id → counters dict
        self._posture_sleep_frames: int = 0       # 姿态计数器（共享）
        self._face_seen_frames: int = 0           # 是否曾检测到人脸的衰减计数
        self._fps: float = 30.0
        self._frame_timestamp_ms: int = 0
        self._camera_matrix: np.ndarray | None = None
        self._frame_idx: int = 0  # 用于清理过期 face state

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray, fps: float = 30.0) -> DrowsinessResult:
        self._fps = fps
        self._frame_idx += 1
        if self._camera_matrix is None:
            h, w = frame.shape[:2]
            self._camera_matrix = self._build_camera_matrix(w, h)

        # === 第1遍: CLAHE增强图像 ===
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_eq = self._clahe.apply(gray)
        frame_eq = frame.copy().astype(np.float32)
        scale = (gray_eq.astype(np.float32) + 1.0) / (gray.astype(np.float32) + 1.0)
        scale = np.clip(scale, 0.5, 2.0)
        for c in range(3):
            frame_eq[:, :, c] = np.clip(frame_eq[:, :, c] * scale, 0, 255)
        frame_eq = frame_eq.astype(np.uint8)

        result = self._detect(frame_eq)

        # === 第2遍兜底: 原图 (CLAHE可能在某些场景失效) ===
        if not result.metrics.face_detected and not result.pose.person_detected:
            result_raw = self._detect(frame)
            if result_raw.metrics.face_detected or result_raw.pose.person_detected:
                result = result_raw

        return result

    def _detect(self, frame: np.ndarray) -> DrowsinessResult:
        """单次检测: 传入一帧BGR图像, 处理多脸并返回最严重的结果"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        if self._running_mode == "image":
            face_result = self._face_landmarker.detect(mp_image)
            pose_result = self._pose_landmarker.detect(mp_image)
        else:
            self._frame_timestamp_ms += int(1000.0 / max(self._fps, 1.0))
            ts = self._frame_timestamp_ms
            face_result = self._face_landmarker.detect_for_video(mp_image, ts)
            pose_result = self._pose_landmarker.detect_for_video(mp_image, ts)

        face_metrics_list = self._extract_face_metrics(face_result, frame)
        # 过滤假脸
        face_metrics_list = [self._validate_face_metrics(fm) for fm in face_metrics_list]
        face_metrics_list = [fm for fm in face_metrics_list if fm.face_detected]

        pose_metrics = self._extract_pose_metrics(pose_result, frame.shape)
        return self._evaluate_multi(face_metrics_list, pose_metrics)

    def reset(self) -> None:
        self._face_states.clear()
        self._posture_sleep_frames = 0
        self._face_seen_frames = 0
        self._frame_timestamp_ms = 0
        self._frame_idx = 0
        self._face_landmarker.close()
        self._face_landmarker_img.close()
        self._pose_landmarker.close()
        self._face_landmarker = self._create_face_landmarker()
        self._face_landmarker_img = self._create_face_landmarker_image()
        self._pose_landmarker = self._create_pose_landmarker()

    def close(self) -> None:
        self._face_landmarker.close()
        self._face_landmarker_img.close()
        self._pose_landmarker.close()

    def _create_face_landmarker(self):
        cfg = drowsiness_cfg
        mp_mode = vision.RunningMode.IMAGE if self._running_mode == "image" else vision.RunningMode.VIDEO
        face_options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(_FACE_MODEL)),
            running_mode=mp_mode,
            num_faces=5,
            min_face_detection_confidence=cfg.face_detection_confidence,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
        )
        return vision.FaceLandmarker.create_from_options(face_options)

    def _create_face_landmarker_image(self):
        """侧脸 fallback: image 模式, 较低置信度阈值（不宜过低以免非人脸区域误检）"""
        face_options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(_FACE_MODEL)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=5,
            min_face_detection_confidence=0.35,  # 适度降低以抓侧脸，但不过低以防误检
            min_tracking_confidence=0.3,
            output_face_blendshapes=False,
        )
        return vision.FaceLandmarker.create_from_options(face_options)

    def _create_pose_landmarker(self):
        cfg = drowsiness_cfg
        mp_mode = vision.RunningMode.IMAGE if self._running_mode == "image" else vision.RunningMode.VIDEO
        pose_options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(_POSE_MODEL)),
            running_mode=mp_mode,
            num_poses=3,
            min_pose_detection_confidence=cfg.pose_detection_confidence,
            min_tracking_confidence=0.5,
            output_segmentation_masks=False,
        )
        return vision.PoseLandmarker.create_from_options(pose_options)

    def _validate_face_metrics(self, fm: FaceMetrics) -> FaceMetrics:
        """过滤假脸: EAR/MAR 异常说明 landmarks 踩到了非人脸区域"""
        if fm.face_detected:
            # EAR 在 [0.05, 0.6] 之外大概率是误检（闭眼可低至 ~0.10，睁眼一般 ~0.25-0.40）
            if fm.ear_avg < 0.02 or fm.ear_avg > 0.65:
                return FaceMetrics(face_detected=False)
            if fm.mar > 0.85:
                return FaceMetrics(face_detected=False)
        return fm

    # ------------------------------------------------------------------
    # 多人脸跟踪
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox_iou(a: tuple, b: tuple) -> float:
        """两个 bbox (x, y, w, h) 的 IoU"""
        ax1, ay1, aw, ah = a
        ax2, ay2 = ax1 + aw, ay1 + ah
        bx1, by1, bw, bh = b
        bx2, by2 = bx1 + bw, by1 + bh
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        union = aw * ah + bw * bh - inter
        return inter / union if union > 0 else 0.0

    def _match_faces(self, current_bboxes: list[tuple]) -> list[str]:
        """将当前帧的人脸 bbox 匹配到已有的 face_id，新脸分配新 ID。
        返回与 current_bboxes 等长的 face_id 列表。"""
        ids = []
        used_ids: set[str] = set()
        for bbox in current_bboxes:
            best_id, best_iou = None, 0.3  # IoU 阈值
            for fid, state in self._face_states.items():
                if fid in used_ids:
                    continue
                last_bbox = state.get("last_bbox")
                if last_bbox is None:
                    continue
                iou = self._bbox_iou(bbox, last_bbox)
                if iou > best_iou:
                    best_iou, best_id = iou, fid
            if best_id:
                used_ids.add(best_id)
                ids.append(best_id)
            else:
                new_id = f"f{self._frame_idx}_{len(ids)}"
                used_ids.add(new_id)
                ids.append(new_id)
        # 清理超过 90 帧未出现的 face state
        stale = [fid for fid, s in self._face_states.items()
                  if self._frame_idx - s.get("last_frame", 0) > 90]
        for fid in stale:
            del self._face_states[fid]
        return ids

    def _ensure_face_state(self, face_id: str) -> dict:
        """获取或创建某个 face 的独立计数器"""
        if face_id not in self._face_states:
            self._face_states[face_id] = {
                "eyes": 0, "head": 0, "yawn": 0, "seen": 0,
                "last_bbox": None, "last_frame": self._frame_idx,
            }
        return self._face_states[face_id]

    # ------------------------------------------------------------------
    # 面部特征提取（多人脸版本）
    # ------------------------------------------------------------------

    def _extract_face_metrics(self, mp_result, frame: np.ndarray) -> list[FaceMetrics]:
        """从 MediaPipe 结果提取所有人脸的 FaceMetrics"""
        results: list[FaceMetrics] = []
        h, w = frame.shape[:2]

        if mp_result.face_landmarks:
            for landmarks in mp_result.face_landmarks:
                def pixel(idx: int) -> tuple[float, float]:
                    lm = landmarks[idx]
                    return (lm.x * w, lm.y * h)

                ear_l = self._calc_ear([pixel(i) for i in self.left_eye_idx])
                ear_r = self._calc_ear([pixel(i) for i in self.right_eye_idx])
                mar = self._calc_mar([pixel(i) for i in self.mouth_idx])
                pitch, yaw, roll = self._estimate_head_pose(landmarks, w, h)

                xs = [lm.x * w for lm in landmarks]
                ys = [lm.y * h for lm in landmarks]
                fx, fy = int(min(xs)), int(min(ys))
                fw, fh = int(max(xs) - min(xs)), int(max(ys) - min(ys))
                pad_x, pad_y = int(fw * 0.15), int(fh * 0.15)
                fx, fy = max(0, fx - pad_x), max(0, fy - pad_y)
                fw, fh = min(w - fx, fw + pad_x * 2), min(h - fy, fh + pad_y * 2)

                results.append(FaceMetrics(
                    ear_left=ear_l, ear_right=ear_r, ear_avg=(ear_l + ear_r) / 2.0,
                    mar=mar, head_pitch=pitch, head_yaw=yaw, head_roll=roll,
                    face_detected=True, face_bbox=(fx, fy, fw, fh),
                ))
            return results

        # --- 侧脸 fallback: OpenCV cascade 兜底 ---
        if self._profile_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            profiles = list(self._profile_cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=3, minSize=(30, 30)))
            fronts = list(self._front_cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=3, minSize=(30, 30)))
            all_faces = profiles + fronts
            # 去重
            merged = self._merge_bboxes(all_faces)
            for fx, fy, fw, fh in merged[:5]:  # 最多 5 张脸
                pad = int(max(fw, fh) * 0.4)
                x1, y1 = max(0, fx - pad), max(0, fy - pad)
                x2, y2 = min(w, fx + fw + pad), min(h, fy + fh + pad)
                face_crop = frame[y1:y2, x1:x2]
                if face_crop.size == 0:
                    continue
                if max(face_crop.shape[:2]) < 120:
                    face_crop = cv2.resize(face_crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                rgb_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_crop)
                try:
                    crop_result = self._face_landmarker_img.detect(mp_img)
                except Exception:
                    continue
                if crop_result.face_landmarks:
                    landmarks = crop_result.face_landmarks[0]
                    ch, cw = face_crop.shape[:2]

                    def _pixel(idx):
                        return (landmarks[idx].x * cw, landmarks[idx].y * ch)

                    ear_l = self._calc_ear([_pixel(i) for i in self.left_eye_idx])
                    ear_r = self._calc_ear([_pixel(i) for i in self.right_eye_idx])
                    ear_avg = max(ear_l, ear_r)
                    mar = self._calc_mar([_pixel(i) for i in self.mouth_idx])
                    pitch, yaw, roll = self._estimate_head_pose(landmarks, cw, ch)

                    results.append(FaceMetrics(
                        ear_left=ear_l, ear_right=ear_r, ear_avg=ear_avg,
                        mar=mar, head_pitch=pitch, head_yaw=yaw, head_roll=roll,
                        face_detected=True, face_bbox=(fx, fy, fw, fh),
                    ))
            return results

        return []  # 无人脸

    @staticmethod
    def _merge_bboxes(bboxes: list) -> list:
        """去重合并重叠的人脸框"""
        if len(bboxes) <= 1:
            return [tuple(b) for b in bboxes]
        # 按面积排序
        sorted_boxes = sorted(bboxes, key=lambda b: b[2] * b[3], reverse=True)
        kept = []
        for box in sorted_boxes:
            overlap = False
            for k in kept:
                # 简单中心距离判断
                cx1, cy1 = box[0] + box[2] / 2, box[1] + box[3] / 2
                cx2, cy2 = k[0] + k[2] / 2, k[1] + k[3] / 2
                if abs(cx1 - cx2) < min(box[2], k[2]) * 0.5 and abs(cy1 - cy2) < min(box[3], k[3]) * 0.5:
                    overlap = True
                    break
            if not overlap:
                kept.append(tuple(box))
        return kept

    # ------------------------------------------------------------------
    # 身体姿态提取 (趴睡检测)
    # ------------------------------------------------------------------

    def _extract_pose_metrics(self, mp_result, shape: tuple) -> PoseMetrics:
        """从 Pose Landmarker 结果中提取趴桌睡觉特征"""
        if not mp_result.pose_landmarks:
            return PoseMetrics(person_detected=False)

        h, w = shape[:2]
        lm = mp_result.pose_landmarks[0]

        def y(idx: int) -> float:
            """返回归一化 Y 坐标 (0=顶, 1=底)"""
            return lm[idx].y

        def xy(idx: int) -> tuple[float, float]:
            return (lm[idx].x * w, lm[idx].y * h)

        cfg = drowsiness_cfg
        nose_y = y(cfg.pose_nose_idx)
        shoulder_l = y(cfg.pose_left_shoulder_idx)
        shoulder_r = y(cfg.pose_right_shoulder_idx)
        shoulder_mid_y = (shoulder_l + shoulder_r) / 2.0
        hip_l = y(cfg.pose_left_hip_idx)
        hip_r = y(cfg.pose_right_hip_idx)
        hip_mid_y = (hip_l + hip_r) / 2.0

        # 关键指标: 头部下沉比例
        # 分母是躯干长度(髋→肩), 分子是头低于肩的幅度
        torso_len = hip_mid_y - shoulder_mid_y
        if torso_len > 0.02:
            head_drop_ratio = (nose_y - shoulder_mid_y) / torso_len
        else:
            head_drop_ratio = 0.0

        head_below = head_drop_ratio > cfg.head_below_shoulder_ratio

        # 躯干前倾角 (肩-髋连线 偏离竖直方向的角度)
        nose_px = xy(cfg.pose_nose_idx)
        shoulder_mid_px = (
            (xy(cfg.pose_left_shoulder_idx)[0] + xy(cfg.pose_right_shoulder_idx)[0]) / 2,
            (xy(cfg.pose_left_shoulder_idx)[1] + xy(cfg.pose_right_shoulder_idx)[1]) / 2,
        )
        torso_angle = math.degrees(
            math.atan2(
                abs(nose_px[0] - shoulder_mid_px[0]),
                abs(shoulder_mid_px[1] - nose_px[1]) + 1e-6,
            )
        )

        return PoseMetrics(
            person_detected=True,
            head_below_shoulder=head_below,
            head_drop_ratio=round(head_drop_ratio, 3),
            torso_angle=round(torso_angle, 1),
            torso_slouched=torso_angle > self.torso_slouch_angle,
        )

    # ------------------------------------------------------------------
    # EAR / MAR 计算
    # ------------------------------------------------------------------

    @staticmethod
    def _euclidean(a, b) -> float:
        return float(math.hypot(a[0] - b[0], a[1] - b[1]))

    def _calc_ear(self, pts: list) -> float:
        v1 = self._euclidean(pts[2], pts[3])
        v2 = self._euclidean(pts[4], pts[5])
        h = self._euclidean(pts[0], pts[1])
        if h < 1e-6:
            return 0.0
        return (v1 + v2) / (2.0 * h)

    def _calc_mar(self, pts: list) -> float:
        v = self._euclidean(pts[2], pts[3])
        h = self._euclidean(pts[0], pts[1])
        if h < 1e-6:
            return 0.0
        return v / h

    # ------------------------------------------------------------------
    # 头部姿态估计
    # ------------------------------------------------------------------

    def _estimate_head_pose(self, landmarks, w: int, h: int) -> tuple[float, float, float]:
        points_2d = np.array(
            [(landmarks[i].x * w, landmarks[i].y * h) for i in self.hp_2d_idx],
            dtype=np.float64,
        )
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)
        success, rvec, _ = cv2.solvePnP(
            self.hp_3d, points_2d, self._camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            return 0.0, 0.0, 0.0
        rmat, _ = cv2.Rodrigues(rvec)
        return self._rotation_to_euler(rmat)

    @staticmethod
    def _rotation_to_euler(R: np.ndarray) -> tuple[float, float, float]:
        sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        singular = sy < 1e-6
        if not singular:
            pitch = math.atan2(R[2, 1], R[2, 2])
            yaw = math.atan2(-R[2, 0], sy)
            roll = math.atan2(R[1, 0], R[0, 0])
        else:
            pitch = math.atan2(-R[1, 2], R[1, 1])
            yaw = math.atan2(-R[2, 0], sy)
            roll = 0.0
        return math.degrees(pitch), math.degrees(yaw), math.degrees(roll)

    @staticmethod
    def _build_camera_matrix(w: int, h: int) -> np.ndarray:
        focal = float(w)
        return np.array([[focal, 0, w / 2.0], [0, focal, h / 2.0], [0, 0, 1]], dtype=np.float64)

    # ------------------------------------------------------------------
    # 综合判定（多人脸版本）
    # ------------------------------------------------------------------

    def _evaluate_multi(self, face_list: list[FaceMetrics], pm: PoseMetrics) -> DrowsinessResult:
        """处理多脸：为每张脸独立维护计数器，返回最严重的瞌睡结果"""
        fps = max(self._fps, 1.0)
        is_image_mode = self._running_mode == "image"

        best: DrowsinessResult | None = None  # 跟踪最差的脸

        # --- 多人脸匹配 & 独立累计 ---
        current_bboxes = [fm.face_bbox for fm in face_list if fm.face_bbox]
        face_ids = self._match_faces(current_bboxes)

        for i, fm in enumerate(face_list):
            fid = face_ids[i] if i < len(face_ids) else f"f{self._frame_idx}_{i}"
            state = self._ensure_face_state(fid)
            state["last_bbox"] = fm.face_bbox
            state["last_frame"] = self._frame_idx
            state["seen"] = min(state["seen"] + 1, 300)

            # 闭眼累计
            if fm.eyes_closed:
                state["eyes"] += 1
                if state["eyes"] % 5 == 1:
                    print(f"[瞌睡DEBUG fid={fid}] EAR={fm.ear_avg:.4f} 闭眼累计={state['eyes']}帧 "
                          f"(需>{self.ear_consec}触发)", flush=True)
            else:
                state["eyes"] = max(0, state["eyes"] - 1)

            # 低头累计（闭眼时不累加，防止眼部漂移误判）
            if fm.head_drooping and not fm.eyes_closed:
                state["head"] += 1
            elif not fm.head_drooping:
                state["head"] = max(0, state["head"] - 1)

            # 哈欠累计
            if fm.yawning:
                state["yawn"] += 1
            else:
                state["yawn"] = max(0, state["yawn"] - 1)

            # --- 判定当前人脸 ---
            eyes_alert = state["eyes"] >= self.ear_consec
            head_alert = state["head"] >= self.head_droop_consec
            yawn_consec = state["yawn"] >= 10
            eyes_sec = state["eyes"] / fps
            head_sec = state["head"] / fps

            r = DrowsinessResult(metrics=fm, pose=pm,
                                 eyes_closed_sec=round(eyes_sec, 2),
                                 head_droop_sec=round(head_sec, 2))
            if eyes_alert and head_alert:
                r.is_drowsy = True; r.level = "critical"; r.confidence = 0.95
                r.alert_type = "combined"
                r.message = "严重瞌睡: 闭眼+低头，请立即干预!"
            elif eyes_alert:
                r.is_drowsy = True
                r.level = "critical" if not is_image_mode else "warning"
                r.confidence = min(0.95, 0.5 + eyes_sec / 10.0)
                r.alert_type = "eyes_closed"
                r.message = f"闭眼告警: 持续闭眼 {eyes_sec:.1f} 秒"
            elif head_alert:
                r.is_drowsy = True; r.level = "warning"
                r.confidence = min(0.90, 0.5 + head_sec / 10.0)
                r.alert_type = "head_droop"
                r.message = f"低头告警: 持续低头 {head_sec:.1f} 秒"
            elif yawn_consec:
                r.is_drowsy = True; r.level = "warning"
                r.confidence = min(0.80, 0.4 + state["yawn"] / 30)
                r.alert_type = "yawning"
                r.message = f"多次打哈欠: 连续{state['yawn']}帧"

            if r.is_drowsy and (best is None or
                (r.level == "critical" and best.level != "critical") or
                r.confidence > best.confidence):
                best = r

        # --- 衰减未匹配的人脸计数器 ---
        matched_ids = set(face_ids)
        for fid in list(self._face_states.keys()):
            if fid not in matched_ids:
                s = self._face_states[fid]
                s["eyes"] = max(0, s["eyes"] - 2)
                s["head"] = max(0, s["head"] - 2)
                s["yawn"] = max(0, s["yawn"] - 1)
                s["seen"] = max(0, s["seen"] - 1)

        # --- 全局 face_seen 衰减 ---
        if face_list:
            self._face_seen_frames = min(self._face_seen_frames + 1, 300)
        else:
            self._face_seen_frames = max(0, self._face_seen_frames - 1)

        # --- 姿态累计（共享） ---
        posture_abnormal = pm.head_below_shoulder and pm.torso_slouched
        if posture_abnormal:
            self._posture_sleep_frames += 1
        else:
            self._posture_sleep_frames = max(0, self._posture_sleep_frames - 2)

        posture_sec = self._posture_sleep_frames / fps
        posture_alert = self._posture_sleep_frames >= self.pose_sleep_frames
        posture_sleep = posture_alert and not face_list and pm.person_detected and self._face_seen_frames > 0

        if best is None and posture_sleep:
            fm = FaceMetrics(face_detected=False)
            reason = "头低于肩" if pm.head_below_shoulder else "躯干前倾"
            best = DrowsinessResult(
                is_drowsy=True, level="critical",
                confidence=min(0.95, 0.6 + posture_sec / 10.0),
                alert_type="posture_sleep", metrics=fm, pose=pm,
                posture_sleep_sec=round(posture_sec, 2),
                message=f"趴睡告警: {reason} {posture_sec:.1f} 秒，疑似趴桌睡觉",
            )

        if best is None:
            # 取第一张脸的信息作为默认（无告警时展示用）
            if face_list:
                fm = face_list[0]
                eyes_sec = 0.0; head_sec = 0.0
                if face_ids and face_ids[0] in self._face_states:
                    s = self._face_states[face_ids[0]]
                    eyes_sec = s["eyes"] / fps
                    head_sec = s["head"] / fps
                best = DrowsinessResult(metrics=fm, pose=pm,
                                        eyes_closed_sec=round(eyes_sec, 2),
                                        head_droop_sec=round(head_sec, 2),
                                        posture_sleep_sec=round(posture_sec, 2))
            else:
                best = DrowsinessResult(metrics=FaceMetrics(face_detected=False),
                                        pose=pm, posture_sleep_sec=round(posture_sec, 2),
                                        message="画面中未检测到人脸")

        best.posture_sleep_sec = round(posture_sec, 2)
        return best
