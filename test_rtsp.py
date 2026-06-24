"""
摄像头 RTSP 流测试工具
用法:
    python test_rtsp.py rtsp://admin:12345@192.168.1.100:554/Streaming/Channels/101
    python test_rtsp.py 0    (USB摄像头)

按 Q 退出，终端实时打印检测结果
"""

import sys
import time
import cv2

sys.path.insert(0, str(__file__))

from src.drowsiness.detector import DrowsinessDetector


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "0"

    # RTSP 常用优化参数
    if source.startswith("rtsp"):
        # 用 TCP 传输，UDP 在公网/复杂网络容易丢包花屏
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 降低缓冲，减少延迟
    elif source.isdigit():
        cap = cv2.VideoCapture(int(source))
    else:
        cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print(f"无法连接: {source}")
        print("请检查: 1)IP是否能ping通  2)账号密码是否正确  3)RTSP路径是否匹配品牌")
        return

    print(f"已连接: {source}")
    print("运行中... 按 Q 退出\n")

    detector = DrowsinessDetector()
    frame_count = 0
    fps = 0.0
    alert_count = 0
    last_alert_time = 0

    while True:
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret:
            print("视频流中断, 尝试重连...")
            cap.release()
            time.sleep(3)
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            detector.reset()
            continue

        frame = cv2.resize(frame, (640, 480))
        result = detector.process_frame(frame, fps=max(fps, 1.0))

        frame_count += 1
        elapsed = time.perf_counter() - t0
        fps = 0.9 * fps + 0.1 * (1.0 / max(elapsed, 0.001))

        # 检测到瞌睡才打印
        if result.is_drowsy:
            alert_count += 1
            now = time.time()
            if now - last_alert_time > 2.0:
                print(f"[{result.level.upper()}] {result.message}")
                print(f"       Face={'有' if result.metrics.face_detected else '无'}  "
                      f"EAR={result.metrics.ear_avg:.3f}  MAR={result.metrics.mar:.3f}  "
                      f"HeadDrop={result.pose.head_drop_ratio:.2f}  "
                      f"TorsoAngle={result.pose.torso_angle:.0f}  conf={result.confidence:.2f}")
                last_alert_time = now

        # 每100帧打印一次心跳
        if frame_count % 100 == 0:
            norm = "正常" if not result.is_drowsy else result.level.upper()
            print(f"[{frame_count}帧 | FPS={fps:.1f}] 当前状态: {norm}  "
                  f"EAR={result.metrics.ear_avg:.3f}  累计告警:{alert_count}次")

        # 画面叠加
        _draw_overlay(frame, result, fps, frame_count, alert_count)
        cv2.imshow("瞌睡检测 - 按Q退出", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    print(f"\n共处理 {frame_count} 帧, 告警 {alert_count} 次")


def _draw_overlay(frame, result, fps, count, alerts):
    m = result.metrics
    p = result.pose
    h, w = frame.shape[:2]

    color = (0, 0, 255) if result.level == "critical" else (0, 180, 255) if result.is_drowsy else (0, 220, 0)

    texts = [
        f"FPS: {fps:.1f} | Frame: {count} | Alerts: {alerts}",
        f"Face: {'YES' if m.face_detected else 'NO'}  |  Person: {'YES' if p.person_detected else 'NO'}",
        f"EAR: {m.ear_avg:.3f}  |  MAR: {m.mar:.3f}",
        f"Pitch: {m.head_pitch:.0f}  Yaw: {m.head_yaw:.0f}  Roll: {m.head_roll:.0f}",
        f"EyesClosed: {result.eyes_closed_sec:.1f}s  HeadDroop: {result.head_droop_sec:.1f}s",
        f"PostureSleep: {result.posture_sleep_sec:.1f}s  HeadDrop: {p.head_drop_ratio:.2f}  TorsoAngle: {p.torso_angle:.0f}",
    ]
    if result.is_drowsy:
        texts.append(f">>> {result.message}")

    for i, txt in enumerate(texts):
        y = 25 + i * 22
        cv2.putText(frame, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, color, 1, cv2.LINE_AA)

    # 状态灯
    light = (0, 0, 255) if result.level == "critical" else (0, 180, 255) if result.is_drowsy else (0, 255, 0)
    cv2.circle(frame, (16, 14), 8, light, -1)


if __name__ == "__main__":
    main()
