"""
陌生人检测器 —— 摄像头实时人脸 → 与已注册人脸库比对 → 陌生人告警

核心防误报机制：
1. 偏航角过滤：|yaw| > 30° 视为侧脸，跳过匹配（侧脸特征不可靠）
2. 多帧确认：连续 N 帧未匹配才触发告警（防止单帧误检）
3. 匹配稳定：连续 M 帧匹配才确认身份（防止闪烁）
4. 计数器衰减：人脸短时丢失/遮挡时缓慢衰减，不立即重置
"""

from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from dataclasses import dataclass, field

from .config import stranger_cfg

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_FACE_MODEL = _MODEL_DIR / "face_landmarker.task"
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "door_faces.db"


@dataclass
class StrangerResult:
    """单帧陌生人检测结果"""
    timestamp: float = field(default_factory=time.time)

    # 核心判定
    stranger_alert: bool = False          # 是否触发陌生人告警（多帧确认后）
    is_stranger: bool = False             # 当前帧未匹配（单帧）
    face_reliable: bool = False           # 人脸角度是否适合匹配

    # 匹配信息
    matched_user_id: str = ""
    matched_user_name: str = ""
    similarity: float = 0.0
    best_unmatched_sim: float = 0.0       # 最接近的未匹配相似度

    # 人脸质量
    face_yaw: float = 0.0
    face_pitch: float = 0.0
    face_size: int = 0

    # 计数器
    unmatched_count: int = 0
    matched_count: int = 0

    # 描述
    level: str = "normal"                 # normal / warning / critical
    message: str = ""


class StrangerDetector:
    """陌生人检测器：检测到的人脸与 SQLite 人脸库比对"""

    def __init__(self, db_path: str | None = None, model_path: str | None = None):
        cfg = stranger_cfg
        self.max_yaw = cfg.max_yaw_degrees
        self.min_face_width = cfg.min_face_width
        self.match_threshold = cfg.match_threshold
        self.stranger_confirm = cfg.stranger_confirm_frames
        self.match_confirm = cfg.match_confirm_frames
        self.counter_decay = cfg.counter_decay
        self.counter_max = cfg.counter_max

        self._db_path = db_path or str(_DB_PATH)
        self._model_path = model_path or str(_FACE_MODEL)
        self._face_lm: vision.FaceLandmarker | None = None
        self._conn: sqlite3.Connection | None = None

        # 单脸跟踪状态
        self._unmatched = 0      # 连续未匹配帧数
        self._matched = 0        # 连续匹配帧数
        self._last_sim = 0.0
        self._last_user = ""
        self._last_name = ""
        self._last_yaw = 0.0
        self._last_pitch = 0.0

        # 告警冷却：触发陌生人告警后 2 分钟内不再重复告警
        self._alert_cooldown_sec = 120
        self._last_alert_time = 0.0

        # 侧脸对齐: eye cascade（用于仿射变换掰正侧脸）
        self._eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def check_frame(self, frame: np.ndarray) -> StrangerResult:
        """
        检测画面中所有人脸，逐一与数据库比对。
        任意一张人脸未匹配 → 计入陌生人累计；
        全部匹配或无人脸 → 衰减累计。

        返回聚合后的 StrangerResult（取最差情况）。
        """
        faces = self._detect_all_faces(frame)

        if not faces:
            # 无人脸 → 衰减
            self._unmatched = max(0, self._unmatched - self.counter_decay)
            self._matched = max(0, self._matched - self.counter_decay)
            return StrangerResult(
                face_reliable=False,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                message="画面中未检测到人脸",
            )

        # 检查每一张脸
        any_unmatched = False
        any_matched = False
        best_match_user = ""
        best_match_name = ""
        best_match_sim = 0.0
        worst_unmatched_msg = ""

        for fx, fy, fw, fh in faces:
            # 跳过太小的脸
            if fw < self.min_face_width:
                continue

            face_crop = frame[fy:fy + fh, fx:fx + fw]
            if face_crop.size == 0:
                continue

            emb = self._extract_embedding_from_crop(face_crop)
            if emb is None:
                continue

            match = self._match_face(emb)
            if match:
                any_matched = True
                if match["similarity"] > best_match_sim:
                    best_match_sim = match["similarity"]
                    best_match_user = match["user_id"]
                    best_match_name = match.get("user_name", "")
            else:
                any_unmatched = True
                worst_unmatched_msg = "画面中存在未注册人脸"

        # 更新累计计数器
        if any_unmatched:
            self._unmatched = min(self._unmatched + 1, self.counter_max)
            self._matched = max(0, self._matched - self.counter_decay)
        elif any_matched:
            self._matched = min(self._matched + 1, self.counter_max)
            self._unmatched = max(0, self._unmatched - self.counter_decay)
        # 如果既没匹配也没未匹配（所有脸都跳过了），计数器不变

        stranger_confirmed = self._unmatched >= self.stranger_confirm

        if stranger_confirmed:
            now = time.time()
            if now - self._last_alert_time < self._alert_cooldown_sec:
                # 冷却期内，不重复告警，但仍返回陌生人状态
                remaining = int(self._alert_cooldown_sec - (now - self._last_alert_time))
                return StrangerResult(
                    stranger_alert=False, is_stranger=True,
                    face_reliable=True,
                    matched_user_id=best_match_user,
                    matched_user_name=best_match_name,
                    similarity=best_match_sim,
                    face_yaw=0.0, face_pitch=0.0,
                    face_size=faces[0][2] if faces else 0,
                    unmatched_count=self._unmatched,
                    matched_count=self._matched,
                    level="normal",
                    message=f"陌生人冷却中 ({remaining}s)",
                )
            self._last_alert_time = now
            return StrangerResult(
                stranger_alert=True, is_stranger=True,
                face_reliable=True,
                matched_user_id=best_match_user,
                matched_user_name=best_match_name,
                similarity=best_match_sim,
                face_yaw=0.0, face_pitch=0.0,
                face_size=faces[0][2] if faces else 0,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                level="warning",
                message=f"⚠️ 陌生人警告！画面中存在未注册人员 (连续{self._unmatched}帧)",
            )
        elif any_unmatched:
            return StrangerResult(
                stranger_alert=False, is_stranger=True,
                face_reliable=True,
                matched_user_id=best_match_user,
                matched_user_name=best_match_name,
                similarity=best_match_sim,
                face_yaw=0.0, face_pitch=0.0,
                face_size=faces[0][2] if faces else 0,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                level="normal",
                message=f"未注册人员 ({self._unmatched}/{self.stranger_confirm}帧)",
            )
        elif any_matched:
            return StrangerResult(
                stranger_alert=False, is_stranger=False,
                face_reliable=True,
                matched_user_id=best_match_user,
                matched_user_name=best_match_name,
                similarity=best_match_sim,
                face_yaw=0.0, face_pitch=0.0,
                face_size=faces[0][2] if faces else 0,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                level="normal",
                message=f"已识别: {best_match_name or best_match_user}",
            )
        else:
            return StrangerResult(
                face_reliable=False,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                message="人脸过小/质量不足，跳过识别",
            )

    def check(self, frame: np.ndarray, face_bbox: tuple | None,
              head_yaw: float = 0.0, head_pitch: float = 0.0) -> StrangerResult:
        """
        对当前帧检测到的人脸进行陌生人判定。

        Args:
            frame: BGR 图像（用于裁剪人脸区域）
            face_bbox: 人脸边界框 (x, y, w, h)，None 表示未检测到人脸
            head_yaw: 头部偏航角（度），来自 DrowsinessDetector
            head_pitch: 头部俯仰角（度）

        Returns:
            StrangerResult
        """
        cfg = stranger_cfg

        if face_bbox is None:
            # 没有人脸 → 缓慢衰减计数器
            self._unmatched = max(0, self._unmatched - self.counter_decay)
            self._matched = max(0, self._matched - self.counter_decay)
            return StrangerResult(
                face_reliable=False,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                message="未检测到人脸",
            )

        x, y, w, h = face_bbox
        self._last_yaw = head_yaw
        self._last_pitch = head_pitch

        # --- 第1关：人脸尺寸检查 ---
        if w < self.min_face_width:
            return StrangerResult(
                face_reliable=False,
                face_yaw=round(head_yaw, 1),
                face_size=w,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                message="人脸过小，跳过识别",
            )

        # --- 第2关：偏航角检查（侧脸过滤）---
        face_reliable = abs(head_yaw) < self.max_yaw

        # --- 第3关：提取特征 ---
        face_crop = frame[y:y + h, x:x + w]
        if face_crop.size == 0:
            return self._no_face(frame, face_reliable, head_yaw, w)

        emb = self._extract_embedding_from_crop(face_crop)
        if emb is None:
            # 特征提取失败（可能是质量太差）
            return StrangerResult(
                face_reliable=face_reliable,
                face_yaw=round(head_yaw, 1),
                face_pitch=round(head_pitch, 1),
                face_size=w,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                message="人脸特征提取失败",
            )

        # --- 第4关：人脸匹配（仅正脸时生效）---
        if face_reliable:
            match = self._match_face(emb)

            if match:
                # 匹配成功 → 递增匹配计数，清零未匹配计数
                self._matched = min(self._matched + 1, self.counter_max)
                self._unmatched = max(0, self._unmatched - self.counter_decay)
                self._last_sim = match["similarity"]
                self._last_user = match["user_id"]
                self._last_name = match.get("user_name", "")

                identity_confirmed = self._matched >= self.match_confirm
                return StrangerResult(
                    stranger_alert=False,
                    is_stranger=False,
                    face_reliable=True,
                    matched_user_id=match["user_id"],
                    matched_user_name=match.get("user_name", ""),
                    similarity=match["similarity"],
                    face_yaw=round(head_yaw, 1),
                    face_pitch=round(head_pitch, 1),
                    face_size=w,
                    matched_count=self._matched,
                    unmatched_count=self._unmatched,
                    level="normal",
                    message=f"已识别: {match.get('user_name', match['user_id'])}"
                    if identity_confirmed else "匹配确认中...",
                )
            else:
                # 未匹配 → 递增未匹配计数
                self._unmatched = min(self._unmatched + 1, self.counter_max)
                self._matched = max(0, self._matched - self.counter_decay)

                stranger_confirmed = self._unmatched >= self.stranger_confirm
                return StrangerResult(
                    stranger_alert=stranger_confirmed,
                    is_stranger=True,
                    face_reliable=True,
                    similarity=0.0,
                    face_yaw=round(head_yaw, 1),
                    face_pitch=round(head_pitch, 1),
                    face_size=w,
                    unmatched_count=self._unmatched,
                    matched_count=self._matched,
                    level="warning" if stranger_confirmed else "normal",
                    message=f"⚠️ 陌生人警告！未匹配任何已注册用户 (连续{self._unmatched}帧)"
                    if stranger_confirmed else f"未匹配 ({self._unmatched}/{self.stranger_confirm}帧)",
                )
        else:
            # 侧脸：不更新计数器，维持当前状态
            return StrangerResult(
                stranger_alert=self._unmatched >= self.stranger_confirm,
                is_stranger=self._unmatched > 0,
                face_reliable=False,
                matched_user_id=self._last_user if self._matched >= self.match_confirm else "",
                matched_user_name=self._last_name if self._matched >= self.match_confirm else "",
                face_yaw=round(head_yaw, 1),
                face_pitch=round(head_pitch, 1),
                face_size=w,
                unmatched_count=self._unmatched,
                matched_count=self._matched,
                level="normal",
                message=f"侧脸({head_yaw:.0f}°)暂不识别，维持当前状态",
            )

    def reset(self):
        """重置跟踪状态"""
        self._unmatched = 0
        self._matched = 0
        self._last_sim = 0.0
        self._last_user = ""
        self._last_name = ""

    def close(self):
        if self._face_lm:
            self._face_lm.close()
            self._face_lm = None
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # 内部：多脸检测
    # ------------------------------------------------------------------

    def _detect_all_faces(self, frame: np.ndarray) -> list:
        """检测画面中所有人脸，返回 [(x, y, w, h), ...]"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # OpenCV 正面+侧脸 cascade，双重检测合并
        if not hasattr(self, '_front_cascade'):
            self._front_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if not hasattr(self, '_profile_cascade'):
            self._profile_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_profileface.xml")

        fronts = self._front_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
        profiles = self._profile_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))

        # 合并去重
        all_faces = list(fronts) + list(profiles)
        if len(all_faces) <= 1:
            return all_faces

        # 简单去重：IOU > 0.5 的框合并
        def iou(a, b):
            x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
            x2 = min(a[0]+a[2], b[0]+b[2]); y2 = min(a[1]+a[3], b[1]+b[3])
            if x2 <= x1 or y2 <= y1: return 0
            inter = (x2-x1)*(y2-y1)
            return inter / (a[2]*a[3] + b[2]*b[3] - inter)

        merged = []
        used = set()
        for i, a in enumerate(all_faces):
            if i in used: continue
            best = a
            for j, b in enumerate(all_faces):
                if j <= i or j in used: continue
                if iou(a, b) > 0.5:
                    # 取大的框
                    if b[2]*b[3] > best[2]*best[3]:
                        best = b
                    used.add(j)
            merged.append(tuple(best))
        return merged

    # ------------------------------------------------------------------
    # 内部：侧脸仿射对齐
    # ------------------------------------------------------------------

    def _align_face(self, face_crop: np.ndarray) -> np.ndarray | None:
        """检测眼部位置，通过仿射变换把侧脸'掰正'，提高 MediaPipe 检出率。
        返回对齐后的图片，失败返回 None。"""
        h, w = face_crop.shape[:2]
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

        # 在脸的上半部分找眼睛（下半部分可能是嘴/鼻子干扰）
        upper_half = gray[:h // 2, :]
        eyes = self._eye_cascade.detectMultiScale(
            upper_half, scaleFactor=1.05, minNeighbors=3,
            minSize=(w // 10, h // 10))

        if len(eyes) >= 2:
            # 取置信度最高的两只眼（按面积排序取前2）
            eyes = sorted(eyes, key=lambda e: e[2] * e[3], reverse=True)[:2]
            # 按 x 坐标排序，确保左眼在左
            eyes = sorted(eyes, key=lambda e: e[0])
            (lx, ly, lw, lh) = eyes[0]
            (rx, ry, rw, rh) = eyes[1]
            lcx, lcy = lx + lw / 2, ly + lh / 2
            rcx, rcy = rx + rw / 2, ry + rh / 2

            # 计算眼间角度
            dx, dy = rcx - lcx, rcy - lcy
            angle = math.degrees(math.atan2(dy, dx))
            eye_center = ((lcx + rcx) / 2, (lcy + rcy) / 2)
        elif len(eyes) == 1:
            # 只有一只眼：根据它在脸框中的水平位置估算偏航方向
            ex, ey, ew, eh = eyes[0]
            ecx = ex + ew / 2
            # 眼靠左 → 脸朝右（正角度旋转），眼靠右 → 脸朝左（负角度旋转）
            offset = (ecx - w / 2) / (w / 2)  # -1到1
            angle = offset * 20  # 最多旋转20度
            eye_center = (ecx, ey + eh / 2)
        else:
            return None  # 完全找不到眼睛，无法对齐

        # 仿射变换：绕眼中心旋转使眼线水平
        M = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
        # 旋转后需要的画布大小
        cos, sin = abs(M[0, 0]), abs(M[0, 1])
        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)
        M[0, 2] += new_w / 2 - eye_center[0]
        M[1, 2] += new_h / 2 - eye_center[1]
        aligned = cv2.warpAffine(face_crop, M, (new_w, new_h),
                                 borderMode=cv2.BORDER_REPLICATE)
        return aligned

    # ------------------------------------------------------------------
    # 内部：人脸特征提取（与 api_server.py 使用相同的算法）
    # ------------------------------------------------------------------

    def _get_lm(self) -> vision.FaceLandmarker:
        if self._face_lm is None:
            self._face_lm = vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=self._model_path),
                    running_mode=vision.RunningMode.IMAGE,
                    num_faces=1,
                    min_face_detection_confidence=0.15,  # 与 DrowsinessDetector 一致
                )
            )
        return self._face_lm

    def _get_db(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        return self._conn

    def _extract_embedding_from_crop(self, face_crop: np.ndarray) -> np.ndarray | None:
        """从人脸裁剪图提取 256 维归一化几何特征。
        先直接试 MediaPipe，失败则尝试仿射对齐后再试。"""
        if face_crop.shape[0] < 20 or face_crop.shape[1] < 20:
            return None

        # 小脸放大到至少 200px，帮助 MediaPipe 检测
        h, w = face_crop.shape[:2]
        if max(h, w) < 200:
            scale = 200.0 / max(h, w)
            face_crop = cv2.resize(face_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # 尝试1: 原图直接提取
        emb = self._try_extract(face_crop)
        if emb is not None:
            return emb

        # 尝试2: 仿射对齐后提取（侧脸 fallback）
        aligned = self._align_face(face_crop)
        if aligned is not None and aligned.size > 0 and min(aligned.shape[:2]) >= 40:
            # 对齐后也放大
            ah, aw = aligned.shape[:2]
            if max(ah, aw) < 200:
                ascale = 200.0 / max(ah, aw)
                aligned = cv2.resize(aligned, None, fx=ascale, fy=ascale, interpolation=cv2.INTER_CUBIC)
            emb = self._try_extract(aligned)
            if emb is not None:
                return emb

        return None

    def _try_extract(self, face_crop: np.ndarray) -> np.ndarray | None:
        """单次尝试从裁剪图提取特征"""
        rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        try:
            result = self._get_lm().detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        except Exception:
            return None

        if not result.face_landmarks:
            return None

        h, w = face_crop.shape[:2]
        pts = np.array([[l.x * w, l.y * h, l.z * w] for l in result.face_landmarks[0]], dtype=np.float32)
        nose = pts[1]
        eye_dist = np.linalg.norm(pts[33] - pts[263])
        if eye_dist < 1:
            return None

        pts = (pts - nose) / eye_dist
        idx = np.linspace(0, 467, 64, dtype=int)
        s = pts[idx]
        emb = np.concatenate([s.flatten(), np.linalg.norm(s, axis=1)]).astype(np.float32)
        return emb / (np.linalg.norm(emb) + 1e-8)

    def _match_face(self, emb: np.ndarray) -> dict | None:
        """在 SQLite 人脸库中查找最相似的人脸"""
        conn = self._get_db()
        try:
            rows = conn.execute("SELECT id, user_id, user_name, embedding FROM faces").fetchall()
        except sqlite3.OperationalError:
            return None

        best, best_sim = None, -1.0
        emb = emb / (np.linalg.norm(emb) + 1e-8)

        for row in rows:
            stored = np.frombuffer(row[3], dtype=np.float32)
            stored = stored / (np.linalg.norm(stored) + 1e-8)
            sim = float(np.dot(emb, stored))
            if sim > best_sim:
                best_sim = sim
                best = {"id": row[0], "user_id": row[1], "user_name": row[2], "similarity": round(sim, 4)}

        return best if best and best["similarity"] > self.match_threshold else None

    def _no_face(self, frame, face_reliable, head_yaw, face_w):
        return StrangerResult(
            face_reliable=face_reliable,
            face_yaw=round(head_yaw, 1),
            face_size=face_w,
            unmatched_count=self._unmatched,
            matched_count=self._matched,
            message="人脸裁剪失败",
        )
