"""
图片批量测试脚本 —— 对文件夹内的图片运行瞌睡检测，标注后输出到 out/ 目录

用法:
    python test_images.py D:/path/to/images          # 处理整个文件夹
    python test_images.py D:/path/to/images --show    # 逐张弹窗显示
    python test_images.py D:/path/to/img.jpg          # 单张图片

输出: 项目目录下 out/ 文件夹，包含标注后的图片和 results.json
"""

import sys
import json
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.drowsiness.detector import DrowsinessDetector
from src.drowsiness.config import drowsiness_cfg

OUT_DIR = Path(__file__).resolve().parent / "out"


def main():
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    show = "--show" in sys.argv

    if input_path is None:
        print("用法: python test_images.py <图片路径或文件夹> [--show]")
        return

    # 收集图片
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if input_path.is_file():
        images = [input_path]
    elif input_path.is_dir():
        images = sorted([p for p in input_path.iterdir() if p.suffix.lower() in exts])
    else:
        print(f"路径不存在: {input_path}")
        return

    if not images:
        print("没有找到图片文件")
        return

    print(f"共 {len(images)} 张图片")
    OUT_DIR.mkdir(exist_ok=True)

    detector = DrowsinessDetector(running_mode="image")
    results = []
    eyes_closed_count = 0
    yawn_count = 0
    head_droop_count = 0

    for i, img_path in enumerate(images):
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"  [{i+1}/{len(images)}] 跳过 (无法读取): {img_path.name}")
            continue

        result = detector.process_frame(frame, fps=30.0)
        results.append({
            "file": img_path.name,
            "is_drowsy": result.is_drowsy,
            "level": result.level,
            "confidence": result.confidence,
            "alert_type": result.alert_type,
            "message": result.message,
            "ear_avg": round(result.metrics.ear_avg, 4),
            "mar": round(result.metrics.mar, 4),
            "head_pitch": round(result.metrics.head_pitch, 1),
            "head_roll": round(result.metrics.head_roll, 1),
            "face_detected": result.metrics.face_detected,
            "person_detected": result.pose.person_detected,
            "head_drop_ratio": result.pose.head_drop_ratio,
            "torso_angle": result.pose.torso_angle,
        })
        if result.is_drowsy:
            if "eyes" in result.alert_type:
                eyes_closed_count += 1
            if result.alert_type == "yawning":
                yawn_count += 1
            if "head" in result.alert_type:
                head_droop_count += 1

        # 标注并保存
        out_path = OUT_DIR / f"annotated_{img_path.name}"
        _draw_annotation(frame, result)
        cv2.imwrite(str(out_path), frame)

        status = f"[{result.level.upper()}] {result.message}" if result.is_drowsy else "NORMAL"
        print(f"  [{i+1}/{len(images)}] {img_path.name} → {status}  "
              f"EAR={result.metrics.ear_avg:.3f}  MAR={result.metrics.mar:.3f}  "
              f"pitch={result.metrics.head_pitch:.1f}")

        if show:
            cv2.imshow(f"{img_path.name} - 按任意键继续, Q 退出", frame)
            key = cv2.waitKey(0) & 0xFF
            if key == ord("q"):
                break

    detector.close()
    cv2.destroyAllWindows()

    # 写汇总
    summary = {
        "total": len(images),
        "face_detected": sum(1 for r in results if r["face_detected"]),
        "person_detected": sum(1 for r in results if r["person_detected"]),
        "drowsy": sum(1 for r in results if r["is_drowsy"]),
        "eyes_closed": eyes_closed_count,
        "yawning": yawn_count,
        "head_droop": head_droop_count,
        "results": results,
    }
    posture_count = sum(1 for r in results if r.get("alert_type") == "posture_sleep")
    tilt_count = sum(1 for r in results if r.get("alert_type") == "head_tilt")
    summary_path = OUT_DIR / "results.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'='*50}")
    print(f"完成! {summary['drowsy']}/{summary['total']} 张检出瞌睡特征 ({summary['drowsy']/summary['total']*100:.1f}%)")
    print(f"  闭眼: {eyes_closed_count}  打哈欠: {yawn_count}  低头/侧倾: {head_droop_count + tilt_count}")
    print(f"  趴睡(姿态): {posture_count}")
    print(f"  未检测到人脸: {summary['total'] - summary['face_detected']}  未检测到人体: {summary['total'] - summary['person_detected']}")
    print(f"  标注图片: {OUT_DIR}/")
    print(f"  结果 JSON: {summary_path}")


def _draw_annotation(frame, result):
    """在图片上绘制检测信息"""
    m = result.metrics
    h, w = frame.shape[:2]

    if result.is_drowsy:
        color = (0, 0, 255) if result.level == "critical" else (0, 140, 255)
    else:
        color = (0, 200, 0)

    texts = [
        f"Status: {result.level.upper()}" if result.is_drowsy else "Status: NORMAL",
        f"Face: {'YES' if m.face_detected else 'NO'}",
        f"EAR: {m.ear_avg:.3f}  (threshold: {drowsiness_cfg.ear_threshold})",
        f"MAR: {m.mar:.3f}  (threshold: {drowsiness_cfg.mar_threshold})",
        f"Pitch: {m.head_pitch:.1f}  Yaw: {m.head_yaw:.1f}  Roll: {m.head_roll:.1f}",
    ]
    if result.is_drowsy:
        texts.append(f">> {result.message}  (conf={result.confidence:.2f})")

    for i, txt in enumerate(texts):
        y = 28 + i * 24
        # 半透明背景
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (8, y - th - 4), (8 + tw + 8, y + 4), (40, 40, 40), -1)
        cv2.putText(frame, txt, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 1, cv2.LINE_AA)

    # 左上角状态灯
    light = (0, 0, 255) if result.level == "critical" else (0, 140, 255) if result.is_drowsy else (0, 255, 0)
    cv2.circle(frame, (16, 14), 8, light, -1)


if __name__ == "__main__":
    main()
