"""
本地测试脚本 —— 打开摄像头运行瞌睡检测并实时显示结果
用于验证检测器功能是否正常，不依赖 API 服务

用法:
    python test_detector.py            # USB 摄像头
    python test_detector.py test.mp4   # 本地视频文件
    python test_detector.py rtsp://... # RTSP 网络流

按 Q 退出
"""

import sys
import time
import cv2
from pathlib import Path

# 确保 src 在导入路径中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.drowsiness.config import StreamConfig
from src.drowsiness.video_processor import VideoProcessor


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "0"

    print(f"视频源: {source}")
    print("启动中...")

    cfg = StreamConfig(source=source, fps=30, frame_width=640, frame_height=480)
    proc = VideoProcessor(cfg)
    proc._detector._frame_timestamp_ms = 0  # 重置时间戳

    # 直接用 OpenCV 读取 + 检测，不通过后台线程 (方便调试)
    cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not cap.isOpened():
        print("无法打开视频源")
        return

    detector = proc._detector
    fps_display = 30.0
    frame_count = 0

    print("运行中... 按 Q 退出\n")

    while True:
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret:
            print("视频流结束或断开")
            break

        frame = cv2.resize(frame, (640, 480))
        result = detector.process_frame(frame, fps=fps_display)

        # 在画面上叠加检测信息
        _draw_overlay(frame, result, fps_display)

        cv2.imshow("瞌睡检测测试 (按 Q 退出)", frame)
        frame_count += 1

        elapsed = time.perf_counter() - t0
        if elapsed > 0:
            fps_display = 0.9 * fps_display + 0.1 * (1.0 / elapsed)

        # 检测到瞌睡时在终端打印
        if result.is_drowsy:
            print(f"[{result.level.upper()}] {result.message}  "
                  f"conf={result.confidence:.2f}  "
                  f"EAR={result.metrics.ear_avg:.3f}  "
                  f"MAR={result.metrics.mar:.3f}  "
                  f"pitch={result.metrics.head_pitch:.1f}")

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    print(f"\n共处理 {frame_count} 帧, 测试完成")


def _draw_overlay(frame, result, fps):
    """在帧上绘制检测指标"""
    m = result.metrics
    h, w = frame.shape[:2]

    texts = [
        f"FPS: {fps:.1f}",
        f"Face: {'YES' if m.face_detected else 'NO'}",
        f"EAR: {m.ear_avg:.3f}  (thresh={drowsiness_cfg.ear_threshold:.2f})",
        f"MAR: {m.mar:.3f}  (thresh={drowsiness_cfg.mar_threshold:.2f})",
        f"Pitch: {m.head_pitch:.1f}  Yaw: {m.head_yaw:.1f}",
        f"EyesClosed: {result.eyes_closed_sec:.1f}s  HeadDroop: {result.head_droop_sec:.1f}s",
    ]

    if result.is_drowsy:
        color = (0, 0, 255) if result.level == "critical" else (0, 165, 255)
        texts.append(f">>> {result.message}")
    else:
        color = (0, 255, 0)
        texts.append("Status: NORMAL")

    for i, txt in enumerate(texts):
        y = 25 + i * 22
        cv2.putText(frame, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, color, 1, cv2.LINE_AA)

    # 状态指示灯 (左上角圆点)
    if result.is_drowsy:
        light_color = (0, 0, 255) if result.level == "critical" else (0, 165, 255)
    else:
        light_color = (0, 255, 0)
    cv2.circle(frame, (20, 12), 8, light_color, -1)


if __name__ == "__main__":
    from src.drowsiness.config import drowsiness_cfg
    main()
