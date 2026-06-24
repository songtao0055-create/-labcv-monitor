"""无头视频测试脚本 —— 输出检测事件 + 保存标注视频"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.fire.detector import FireDetector
from src.fire.config import fire_cfg

VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "test.mp4"
OUT_PATH = Path(VIDEO_PATH).stem + "_annotated.mp4"

detector = FireDetector()
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
print(f"配置: fire_conf={fire_cfg.fire_confidence}, smoke_conf={fire_cfg.smoke_confidence}, res={fire_cfg.detection_width}px")
print(f"火焰窗口={fire_cfg.fire_window_size}/{fire_cfg.fire_min_votes}票")
print(f"烟雾窗口={fire_cfg.smoke_window_size}/{fire_cfg.smoke_min_votes}票")
print(f"输出: {OUT_PATH}")
print("=" * 60)

# 写视频
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(OUT_PATH, fourcc, fps, (width, height))

frame_idx = 0
events = []  # [(frame, timestamp_sec, level, message, conf)]
last_level = "normal"

t_start = time.perf_counter()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame_idx += 1

    result = detector.process_frame(frame, fps=fps)

    # 记录告警事件 (状态变化时)
    if result.level != last_level:
        ts = frame_idx / fps
        events.append((frame_idx, ts, result.level, result.message, result.confidence))
        if result.level != "normal":
            print(f"[第{frame_idx}帧 / {ts:.1f}s] {result.level.upper()} | "
                  f"fire_votes={sum(detector._fire_history)}/{fire_cfg.fire_min_votes} "
                  f"smoke_votes={sum(detector._smoke_history)}/{fire_cfg.smoke_min_votes} "
                  f"conf={result.confidence:.2f}")
        else:
            print(f"[第{frame_idx}帧 / {ts:.1f}s] 恢复正常")
        last_level = result.level

    # 画标注
    annotated = detector.annotate_frame(frame, result)

    # 叠加投票信息
    fire_votes = sum(detector._fire_history)
    smoke_votes = sum(detector._smoke_history)
    overlay = [
        f"FPS: {fps:.1f}  Level: {result.level.upper()}",
        f"Fire: {fire_votes}/{fire_cfg.fire_min_votes}  Smoke: {smoke_votes}/{fire_cfg.smoke_min_votes}",
        f"Conf: {result.confidence:.2f}",
    ]
    for i, txt in enumerate(overlay):
        y = 25 + i * 22
        color = (0, 0, 255) if result.level != "normal" else (0, 255, 0)
        cv2.putText(annotated, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, color, 1, cv2.LINE_AA)

    out.write(annotated)

    if frame_idx % 100 == 0:
        elapsed = time.perf_counter() - t_start
        pct = frame_idx / total_frames * 100 if total_frames else 0
        print(f"  进度: {frame_idx}/{total_frames} ({pct:.0f}%) 耗时: {elapsed:.1f}s")

cap.release()
out.release()
detector.close()

elapsed = time.perf_counter() - t_start
print("=" * 60)
print(f"处理完成! 总帧数: {frame_idx}, 耗时: {elapsed:.1f}s ({frame_idx/elapsed:.1f} FPS)")
print(f"检测到 {len([e for e in events if e[2] != 'normal'])} 次告警事件:")
for e in events:
    if e[2] != "normal":
        print(f"  [{e[1]:.1f}s] {e[2].upper()}: {e[3]} (conf={e[4]:.2f})")
print(f"标注视频已保存: {OUT_PATH}")
