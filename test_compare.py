"""两模型对比测试: 我们的 fire-yolov8s vs 外部 YOLOv8n"""
import sys
import time
from pathlib import Path
from collections import deque

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.fire.config import fire_cfg

VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "test.mp4"

# ── 模型 A: 我们的 ──
from ultralytics import YOLO
model_ours = YOLO("models/fire-yolov8s.pt")
OURS_NAME = "Ours(v8s-1280)"
OURS_CONF_FIRE = 0.15
OURS_CONF_SMOKE = 0.08
OURS_IMGSZ = 1280
FIRE_WIN = 30
FIRE_VOTES = 3
SMOKE_WIN = 30
SMOKE_VOTES = 3

# ── 模型 B: 外部 ──
model_ext = YOLO("models/external_best.pt")
EXT_NAME = "External(v8n-640)"
EXT_CONF_FIRE = 0.15
EXT_CONF_SMOKE = 0.08
EXT_IMGSZ = 640

# ── 视频 ──
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print(f"无法打开视频: {VIDEO_PATH}")
    sys.exit(1)

total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"视频: {VIDEO_PATH}")
print(f"帧数: {total_frames}, FPS: {fps:.1f}, 分辨率: {width}x{height}")
print(f"A: {OURS_NAME}  fire_conf={OURS_CONF_FIRE} smoke_conf={OURS_CONF_SMOKE} imgsz={OURS_IMGSZ}")
print(f"B: {EXT_NAME}   fire_conf={EXT_CONF_FIRE} smoke_conf={EXT_CONF_SMOKE} imgsz={EXT_IMGSZ}")
print("=" * 70)

# ── 滑动窗口状态 ──
fire_hist_ours = deque(maxlen=FIRE_WIN)
smoke_hist_ours = deque(maxlen=SMOKE_WIN)
fire_hist_ext = deque(maxlen=FIRE_WIN)
smoke_hist_ext = deque(maxlen=SMOKE_WIN)

frame_idx = 0
frame_skip = 2  # 每2帧推理一次

# 统计
events_ours = []
events_ext = []
total_det_fire_ours = 0
total_det_smoke_ours = 0
total_det_fire_ext = 0
total_det_smoke_ext = 0

t_start = time.perf_counter()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame_idx += 1

    if frame_idx % frame_skip != 0:
        continue

    # ── 模型 A 推理 ──
    h, w = frame.shape[:2]
    scale_ours = OURS_IMGSZ / w
    frame_ours = cv2.resize(frame, (OURS_IMGSZ, int(h * scale_ours)))
    res_ours = model_ours(frame_ours, conf=min(OURS_CONF_FIRE, OURS_CONF_SMOKE), iou=0.5, verbose=False)

    has_fire_ours = False
    has_smoke_ours = False
    if res_ours and res_ours[0].boxes is not None:
        for box in res_ours[0].boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if cls_id == 0 and conf >= OURS_CONF_FIRE:
                has_fire_ours = True
                total_det_fire_ours += 1
            elif cls_id == 1 and conf >= OURS_CONF_SMOKE:
                has_smoke_ours = True
                total_det_smoke_ours += 1

    fire_hist_ours.append(1 if has_fire_ours else 0)
    smoke_hist_ours.append(1 if has_smoke_ours else 0)

    # ── 模型 B 推理 ──
    scale_ext = EXT_IMGSZ / w
    frame_ext = cv2.resize(frame, (EXT_IMGSZ, int(h * scale_ext)))
    res_ext = model_ext(frame_ext, conf=min(EXT_CONF_FIRE, EXT_CONF_SMOKE), iou=0.5, verbose=False)

    has_fire_ext = False
    has_smoke_ext = False
    if res_ext and res_ext[0].boxes is not None:
        for box in res_ext[0].boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if cls_id == 0 and conf >= EXT_CONF_FIRE:
                has_fire_ext = True
                total_det_fire_ext += 1
            elif cls_id == 1 and conf >= EXT_CONF_SMOKE:
                has_smoke_ext = True
                total_det_smoke_ext += 1

    fire_hist_ext.append(1 if has_fire_ext else 0)
    smoke_hist_ext.append(1 if has_smoke_ext else 0)

    # ── 告警判定 ──
    ts = frame_idx / fps
    fv_ours = sum(fire_hist_ours)
    sv_ours = sum(smoke_hist_ours)
    fv_ext = sum(fire_hist_ext)
    sv_ext = sum(smoke_hist_ext)

    level_ours = "normal"
    if fv_ours >= FIRE_VOTES and sv_ours >= SMOKE_VOTES:
        level_ours = "CRITICAL(fire+smoke)"
    elif fv_ours >= FIRE_VOTES:
        level_ours = "CRITICAL(fire)"
    elif sv_ours >= SMOKE_VOTES:
        level_ours = "WARNING(smoke)"

    level_ext = "normal"
    if fv_ext >= FIRE_VOTES and sv_ext >= SMOKE_VOTES:
        level_ext = "CRITICAL(fire+smoke)"
    elif fv_ext >= FIRE_VOTES:
        level_ext = "CRITICAL(fire)"
    elif sv_ext >= SMOKE_VOTES:
        level_ext = "WARNING(smoke)"

    # 只在状态变化或每秒打印
    if frame_idx % 30 == 0 or level_ours != "normal" or level_ext != "normal":
        marker = ""
        if level_ours != level_ext:
            marker = " <<< DIFF!"
        print(f"[{ts:.1f}s] A:{level_ours:<22s} B:{level_ext:<22s} | "
              f"A fire={fv_ours}/{FIRE_VOTES} smoke={sv_ours}/{SMOKE_VOTES} | "
              f"B fire={fv_ext}/{FIRE_VOTES} smoke={sv_ext}/{SMOKE_VOTES}{marker}")

    if frame_idx % 300 == 0:
        elapsed = time.perf_counter() - t_start
        pct = frame_idx / total_frames * 100
        print(f"  进度: {frame_idx}/{total_frames} ({pct:.0f}%) 耗时: {elapsed:.1f}s")

cap.release()

elapsed = time.perf_counter() - t_start
detections_ours = frame_idx // frame_skip
print("=" * 70)
print(f"处理完成! 耗时: {elapsed:.1f}s")
print()

# ── 统计 ──
print("┌─────────────────────────────────────────────────────────────────────┐")
print("│                        对 比 统 计                                  │")
print("├──────────────────────┬──────────────────┬───────────────────────────┤")
print(f"│ 指标                 │ {OURS_NAME:<16s} │ {EXT_NAME:<18s} │")
print("├──────────────────────┼──────────────────┼───────────────────────────┤")
print(f"│ 模型参数量           │ ~11M (v8s)       │ ~3M (v8n)                 │")
print(f"│ 推理分辨率           │ {OURS_IMGSZ}              │ {EXT_IMGSZ}                        │")
print(f"│ 火焰检测帧数(命中率) │ {total_det_fire_ours:<5} ({total_det_fire_ours/detections_ours*100:.1f}%)       │ {total_det_fire_ext:<5} ({total_det_fire_ext/detections_ours*100:.1f}%)                 │")
print(f"│ 烟雾检测帧数(命中率) │ {total_det_smoke_ours:<5} ({total_det_smoke_ours/detections_ours*100:.1f}%)       │ {total_det_smoke_ext:<5} ({total_det_smoke_ext/detections_ours*100:.1f}%)                 │")
print("└──────────────────────┴──────────────────┴───────────────────────────┘")
