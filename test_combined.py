"""
RTSP 联调测试 —— 瞌睡检测 + 火灾检测 + 陌生人检测 (同一路视频流)

多脸支持：瞌睡检测最多 5 张脸独立跟踪，陌生人检测对画面中所有脸逐一比对。
任意一人触发告警即上报。

用法:
    python test_combined.py
    python test_combined.py "rtsp://admin:password@192.168.1.64:554/Streaming/Channels/102"
    python test_combined.py 0    (USB摄像头)

按 Q 随时退出
"""

import sys
import os
import time
import json
import urllib.request
import threading
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.drowsiness.detector import DrowsinessDetector
from src.fire.detector import FireDetector
from src.stranger.detector import StrangerDetector

DEFAULT_RTSP = "rtsp://admin:yuntao888@192.168.1.64:554/Streaming/Channels/102"  # 子码流 640x360 H.264
API_SERVER = "http://localhost:8000"   # API 服务器地址（与 api_server.py 端口一致）
PROCESS_FPS = 10  # AI 推理帧率
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts_img")
os.makedirs(IMG_DIR, exist_ok=True)

_current_frame = None  # 当前处理帧，告警时截取用
_last_saved_img = ""   # 上次保存的图片路径


# ---------------------------------------------------------------------------
# 多线程 RTSP 取流
# ---------------------------------------------------------------------------

class RealTimeRTSP:
    def __init__(self, rtsp_url: str):
        # 强制 TCP 拉流，彻底解决 H.264 UDP 丢包
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        self.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        # RTSP 首帧可能失败，重试几次
        self.ret = False
        self.frame = None
        for attempt in range(10):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.ret, self.frame = True, frame
                break
            print(f"[RTSP] 连接重试 {attempt + 1}/10...", flush=True)
            time.sleep(1)
        self.running = True
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    # 清空底层缓冲区，保证拿到的永远是最新的帧
                    for _ in range(3):
                        r, f = self.cap.read()
                        if r: frame = f
                    with self._lock:
                        self.frame = frame
                        self.ret = True
                else:
                    # ★ 拉流失败必须标记，否则主循环一直吃旧帧！
                    with self._lock:
                        self.ret = False
                        self.frame = None
                    time.sleep(0.01)
            else:
                with self._lock:
                    self.ret = False
                    self.frame = None
                time.sleep(0.1)

    def read(self):
        with self._lock:
            if not self.ret or self.frame is None:
                return False, None
            # 阅后即焚：拿走当前帧后立刻清空，绝不让 AI 读第二遍
            current_frame = self.frame.copy()
            self.frame = None
            self.ret = False
            return True, current_frame

    def release(self):
        self.running = False
        self.thread.join(timeout=1.0)
        self.cap.release()


# ---------------------------------------------------------------------------
# 告警推送至 API 服务器
# ---------------------------------------------------------------------------

def push_to_server(data: dict, timeout: float = 2.0):
    """POST 告警数据到 api_server，由 api_server 转发给所有小程序 WebSocket 客户端"""
    try:
        body = json.dumps(data)
        req = urllib.request.Request(
            f"{API_SERVER}/api/alerts/push",
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:
        print(f"[推送失败] {e}", flush=True)
        return False


def _build_alert_payload(dr, fr, sr) -> dict:
    """构造标准告警 payload"""
    m = dr.metrics

    # 综合判定
    if dr.is_drowsy and dr.level == "critical":
        overall_level, overall_msg = "critical", str(dr.message)
    elif dr.is_drowsy:
        overall_level, overall_msg = "warning", str(dr.message)
    elif sr and sr.stranger_alert:
        overall_level, overall_msg = "warning", str(sr.message)
    elif fr and fr.level != "normal":
        overall_level, overall_msg = str(fr.level), str(fr.message)
    else:
        overall_level, overall_msg = "normal", "正常"

    return {
        "timestamp": float(time.time()),
        "is_drowsy": bool(dr.is_drowsy),
        "level": str(overall_level),
        "message": str(overall_msg),
        "face_detected": bool(m.face_detected),
        "ear_avg": round(float(m.ear_avg), 4),
        "mar": round(float(m.mar), 4),
        "eyes_closed_sec": round(float(dr.eyes_closed_sec), 1),
        "head_droop_sec": round(float(dr.head_droop_sec), 1),
        "fire": {
            "has_fire": bool(fr.has_fire) if fr else False,
            "has_smoke": bool(fr.has_smoke) if fr else False,
            "level": str(fr.level) if fr else "normal",
            "message": str(fr.message) if fr else "",
            "fire_count": int(fr.fire_count) if fr else 0,
            "smoke_count": int(fr.smoke_count) if fr else 0,
        },
        "stranger": {
            "stranger_alert": bool(sr.stranger_alert) if sr else False,
            "is_stranger": bool(sr.is_stranger) if sr else False,
            "face_reliable": bool(sr.face_reliable) if sr else False,
            "matched_user_id": str(sr.matched_user_id) if sr else "",
            "matched_user_name": str(sr.matched_user_name) if sr else "",
            "similarity": float(sr.similarity) if sr else 0.0,
            "face_yaw": round(float(sr.face_yaw), 1) if sr else 0.0,
            "face_pitch": round(float(sr.face_pitch), 1) if sr else 0.0,
            "face_size": int(sr.face_size) if sr else 0,
            "unmatched_count": int(sr.unmatched_count) if sr else 0,
            "matched_count": int(sr.matched_count) if sr else 0,
            "level": str("warning" if sr and sr.stranger_alert else "normal"),
            "message": str(sr.message) if sr else "",
        },
    }


def _push_combined(dr, fr, sr, drowsy_count, fire_count, stranger_count):
    """构造并推送综合告警，截图用时间戳命名避免被覆盖"""
    payload = _build_alert_payload(dr, fr, sr)
    img_name = ""
    if _current_frame is not None:
        img_name = f"alert_{int(time.time())}.jpg"
        cv2.imwrite(os.path.join(IMG_DIR, img_name), _current_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    payload["image"] = img_name
    push_to_server(payload)


def _push_status(dr, fr, sr):
    """构造并推送心跳状态"""
    m = dr.metrics
    face_ok = bool(m.face_detected)
    payload = {
        "timestamp": float(time.time()),
        "is_drowsy": bool(dr.is_drowsy),
        "level": str(dr.level),
        "message": "heartbeat",
        "face_detected": face_ok,
        "ear_avg": round(float(m.ear_avg), 4) if face_ok else 0.0,
        "mar": round(float(m.mar), 4) if face_ok else 0.0,
        "eyes_closed_sec": round(float(dr.eyes_closed_sec), 1),
        "head_droop_sec": round(float(dr.head_droop_sec), 1),
        "fire": {
            "has_fire": bool(fr.has_fire) if fr else False,
            "has_smoke": bool(fr.has_smoke) if fr else False,
            "level": str(fr.level) if fr else "normal",
            "message": str(fr.message) if fr else "",
            "fire_count": int(fr.fire_count) if fr else 0,
            "smoke_count": int(fr.smoke_count) if fr else 0,
        },
        "stranger": {
            "stranger_alert": bool(sr.stranger_alert) if sr else False,
            "is_stranger": bool(sr.is_stranger) if sr else False,
            "face_reliable": bool(sr.face_reliable) if sr else False,
            "matched_user_id": str(sr.matched_user_id) if sr else "",
            "matched_user_name": str(sr.matched_user_name) if sr else "",
            "similarity": float(sr.similarity) if sr else 0.0,
            "face_yaw": round(float(sr.face_yaw), 1) if sr else 0.0,
            "face_pitch": round(float(sr.face_pitch), 1) if sr else 0.0,
            "face_size": int(sr.face_size) if sr else 0,
            "unmatched_count": int(sr.unmatched_count) if sr else 0,
            "matched_count": int(sr.matched_count) if sr else 0,
            "level": "normal",
            "message": "",
        },
    }
    ok = push_to_server(payload)
    if not ok:
        print("[心跳推送失败]", flush=True)


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

def main():
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RTSP
    print(f"视频源: {source}")

    # 初始化 RTSP
    if source.startswith("rtsp"):
        rtsp = RealTimeRTSP(source)
        if not rtsp.ret:
            print(f"无法连接: {source}")
            return
    else:
        rtsp = None

    print(f"已连接: {source}")

    # 加载模型
    print("加载瞌睡检测模型 (IMAGE 模式，逐帧检测更稳定)...")
    drowsiness = DrowsinessDetector(running_mode="video")
    print("加载火灾检测模型...")
    try:
        fire = FireDetector()
        fire_enabled = True
        print("火灾检测模型已加载")
    except FileNotFoundError as e:
        print(f"火灾检测模型未找到, 仅运行瞌睡检测: {e}")
        fire = None
        fire_enabled = False

    print("加载陌生人检测模型...")
    stranger = StrangerDetector()
    print(f"陌生人检测已启用 | yaw阈值={stranger.max_yaw}° | 多帧确认={stranger.stranger_confirm}帧")

    print("运行中... 按 Q 退出\n")

    frame_count = 0
    fps = 0.0
    drowsy_alert_count = 0
    fire_alert_count = 0
    stranger_alert_count = 0
    _last_pushed_state = ""
    last_drowsy_print = 0.0
    last_fire_print = 0.0
    last_stranger_print = 0.0
    last_drowsy_alert_time = 0.0
    last_fire_alert_time = 0.0
    last_stranger_alert_time = 0.0
    ALERT_HOLD = 3.0
    process_interval = 1.0 / PROCESS_FPS
    last_process_time = 0.0
    last_hb_time = 0.0  # 时间心跳，确保每 5s 推一次

    while True:
        # FPS 限制
        if time.perf_counter() - last_process_time < process_interval:
            time.sleep(0.01)
            continue
        last_process_time = time.perf_counter()

        ret, frame = rtsp.read() if source.startswith("rtsp") else (False, None)
        if not ret or frame is None:
            time.sleep(0.1)
            continue

        frame = cv2.resize(frame, (640, 480))  # 降分辨率提速，人脸检测够用
        global _current_frame
        _current_frame = frame.copy()  # 保存引用，告警时截取用
        frame_count += 1
        now = time.time()

        # AI 推理: 瞌睡每帧都跑（多人脸支持），火灾由FireDetector内部控制跳帧，陌生人独立检测多人脸
        dr = None
        try:
            dr = drowsiness.process_frame(frame, fps=PROCESS_FPS)
        except Exception as e:
            print(f"[瞌睡检测异常] {e}", flush=True)

        fr = None
        if fire_enabled and fire:
            try:
                fr = fire.process_frame(frame, fps=PROCESS_FPS)
            except Exception as e:
                print(f"[火灾检测异常] {e}", flush=True)

        sr = None
        try:
            sr = stranger.check_frame(frame)
        except Exception as e:
            print(f"[陌生人检测异常] {e}", flush=True)

        if dr is None or sr is None:
            continue

        if dr.is_drowsy:
            drowsy_alert_count += 1
            last_drowsy_alert_time = now
            if now - last_drowsy_print > 2.0:
                print(f"[瞌睡 {dr.level.upper()}] {dr.message}")
                last_drowsy_print = now

        if fr and fr.level != "normal":
            fire_alert_count += 1
            last_fire_alert_time = now
            if now - last_fire_print > 2.0:
                print(f"[火灾 {fr.level.upper()}] {fr.message}")
                last_fire_print = now

        if sr and sr.stranger_alert:
            stranger_alert_count += 1
            last_stranger_alert_time = now
            if now - last_stranger_print > 2.0:
                print(f"[陌生人 WARNING] {sr.message}")
                last_stranger_print = now

        # 时间心跳：每 5s 推一次，不受 AI 处理速度影响
        now = time.time()
        if now - last_hb_time > 5.0:
            last_hb_time = now
            _push_status(dr, fr, sr)

        # 帧心跳：每 100 帧推一次状态，仅在存在异常时打印日志
        if frame_count > 0 and frame_count % 100 == 0:
            has_any_alert = (dr and dr.is_drowsy) or (fr and fr.level != "normal") or (sr and sr.stranger_alert)
            if has_any_alert:
                d_status = dr.level.upper() if (dr and dr.is_drowsy) else "正常"
                f_status = fr.level.upper() if (fr and fr.level != "normal") else "正常"
                s_status = "陌生人!" if (sr and sr.stranger_alert) else "正常"
                print(f"[{frame_count}帧] 瞌睡:{d_status} 火灾:{f_status} 陌生人:{s_status}  "
                      f"瞌睡:{drowsy_alert_count}次 火灾:{fire_alert_count}次 陌生人:{stranger_alert_count}次")
            _push_status(dr, fr, sr)

        # 状态变化推送
        current_state = f"d{int(dr.is_drowsy)}_f{int(fr.level != 'normal' if fr else False)}_s{int(sr.stranger_alert if sr else False)}"
        if current_state != _last_pushed_state:
            _last_pushed_state = current_state
            _push_combined(dr, fr, sr, drowsy_alert_count, fire_alert_count, stranger_alert_count)
            print(f"[推送] 状态变化 → {current_state}", flush=True)

    # 清理
    if rtsp:
        rtsp.release()
    drowsiness.close()
    if fire:
        fire.close()
    stranger.close()


# ---------------------------------------------------------------------------
# 画面叠加
# ---------------------------------------------------------------------------

def _draw_overlay(frame, dr, fr, sr, fps, count, drowsy_alerts, fire_alerts, stranger_alerts,
                  last_drowsy_time, last_fire_time, last_stranger_time, hold):
    now = time.time()
    m = dr.metrics
    h, w = frame.shape[:2]

    drowsy_active = dr.is_drowsy or (now - last_drowsy_time < hold)
    fire_active = (fr and fr.level != "normal") or (now - last_fire_time < hold)
    stranger_active = (sr and sr.stranger_alert) or (now - last_stranger_time < hold)

    # --- 瞌睡检测 (左上) ---
    if dr.level == "critical" or (drowsy_active and dr.is_drowsy and dr.level == "critical"):
        d_color = (0, 0, 255)
    elif drowsy_active:
        d_color = (0, 180, 255)
    else:
        d_color = (0, 220, 0)

    d_texts = [
        f"=== 瞌睡检测 ===",
        f"FPS:{fps:.1f} | Alerts:{drowsy_alerts}",
        f"Face:{'YES' if m.face_detected else 'NO'} | EAR:{m.ear_avg:.3f} MAR:{m.mar:.3f}",
        f"EyesClosed:{dr.eyes_closed_sec:.1f}s HeadDroop:{dr.head_droop_sec:.1f}s",
    ]
    if dr.is_drowsy:
        d_texts.append(f">>> {dr.message}")

    for i, txt in enumerate(d_texts):
        y = 20 + i * 20
        cv2.putText(frame, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, d_color, 1, cv2.LINE_AA)
    cv2.circle(frame, (10, 10), 6, d_color, -1)

    # --- 火灾检测 (右上) ---
    if fr is not None:
        if fr.level == "critical" or (fire_active and fr.level == "critical"):
            f_color = (0, 0, 255)
        elif fire_active:
            f_color = (0, 180, 255)
        else:
            f_color = (0, 220, 0)

        f_texts = [
            f"=== 火灾检测 ===",
            f"Fire:{'YES' if fr.has_fire else 'NO'} Smoke:{'YES' if fr.has_smoke else 'NO'}",
            f"Level:{fr.level} Fire:{fr.fire_count} Smoke:{fr.smoke_count}",
        ]
        if fr.message:
            f_texts.append(f">>> {fr.message}")

        for i, txt in enumerate(f_texts):
            y = 20 + i * 20
            (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            x = w - tw - 10
            cv2.putText(frame, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, f_color, 1, cv2.LINE_AA)
        cv2.circle(frame, (w - 10, 10), 6, f_color, -1)

        for d in fr.detections:
            x1, y1, x2, y2 = d.bbox
            box_color = (0, 0, 255) if d.class_name == "fire" else (128, 128, 128)
            label = f"{'FIRE' if d.class_name == 'fire' else 'SMOKE'} {d.confidence:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 1)

    # --- 陌生人检测 (左下) ---
    if sr is not None:
        if sr.stranger_alert or stranger_active:
            s_color = (0, 140, 255)  # 橙色
        elif sr.is_stranger and sr.face_reliable:
            s_color = (0, 200, 255)  # 黄色（未匹配但未达告警帧数）
        elif sr.matched_user_id:
            s_color = (0, 255, 100)  # 绿色（已识别）
        else:
            s_color = (150, 150, 150)  # 灰色（侧脸/无脸/过小）

        s_texts = [
            f"=== 陌生人检测 ===",
            f"Face:{'YES' if m.face_detected else 'NO'} Bbox:{'有' if m.face_bbox else '空'} Alerts:{stranger_alerts}",
            f"Yaw:{sr.face_yaw:.0f} Reliable:{'YES' if sr.face_reliable else 'NO'} Unmatched:{sr.unmatched_count} Sim:{sr.similarity:.3f}",
        ]
        if sr.matched_user_id:
            s_texts.append(f">>> Match: {sr.matched_user_name or sr.matched_user_id} sim={sr.similarity:.3f}")
        else:
            s_texts.append(f">>> {sr.message}")

        base_y = h - 20 - len(s_texts) * 20
        for i, txt in enumerate(s_texts):
            y = base_y + i * 20
            cv2.putText(frame, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, s_color, 1, cv2.LINE_AA)
        cv2.circle(frame, (10, h - 10), 6, s_color, -1)

        # 陌生人告警时在画面中央闪烁提示
        if sr.stranger_alert:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 255), -1)
            alpha = 0.1 + 0.05 * (math.sin(now * 4) if 'math' in dir() else 0)
            cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)


if __name__ == "__main__":
    import math
    main()
