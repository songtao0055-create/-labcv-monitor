"""本地摄像头实时烟火检测测试 —— 滑动窗口投票版"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.fire.detector import FireDetector
from src.fire.config import fire_cfg

# 可覆盖配置
# fire_cfg.model_confidence = 0.15
# fire_cfg.detection_width = 1280

SOURCE = sys.argv[1] if len(sys.argv) > 1 else "0"  # 默认摄像头, 或传视频文件路径
detector = FireDetector()

cap = cv2.VideoCapture(int(SOURCE) if SOURCE.isdigit() else SOURCE)
if not cap.isOpened():
    print(f"无法打开视频源: {SOURCE}")
    sys.exit(1)

fps_display = 30.0
print(f"视频源: {SOURCE}")
print(f"配置: fire_conf={fire_cfg.fire_confidence}, smoke_conf={fire_cfg.smoke_confidence}, res={fire_cfg.detection_width}px, "
      f"火焰窗口={fire_cfg.fire_window_size}/{fire_cfg.fire_min_votes}票, "
      f"烟雾窗口={fire_cfg.smoke_window_size}/{fire_cfg.smoke_min_votes}票")
print("按 q 退出\n")

while True:
    t0 = time.perf_counter()
    ok, frame = cap.read()
    if not ok:
        break

    result = detector.process_frame(frame, fps=fps_display)

    # 画框
    annotated = detector.annotate_frame(frame, result)

    # 叠加滑动窗口投票状态
    fire_votes = sum(detector._fire_history)
    smoke_votes = sum(detector._smoke_history)
    h, w = annotated.shape[:2]

    overlay_lines = [
        f"FPS: {fps_display:.1f} | Level: {result.level.upper()}",
        f"Fire  votes: {fire_votes}/{fire_cfg.fire_min_votes} (window={fire_cfg.fire_window_size})",
        f"Smoke votes: {smoke_votes}/{fire_cfg.smoke_min_votes} (window={fire_cfg.smoke_window_size})",
        f"Conf: {result.confidence:.2f}",
    ]
    for i, txt in enumerate(overlay_lines):
        y = 25 + i * 22
        color = (0, 0, 255) if result.level != "normal" else (0, 255, 0)
        cv2.putText(annotated, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, color, 1, cv2.LINE_AA)

    cv2.imshow("Fire & Smoke Detection", annotated)

    elapsed = time.perf_counter() - t0
    if elapsed > 0:
        fps_display = 0.9 * fps_display + 0.1 * (1.0 / elapsed)

    if result.level != "normal":
        print(f"[{result.level.upper()}] {result.message}  conf={result.confidence:.2f}")

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
detector.close()
