"""
飞书机器人 —— 门禁人脸识别 (SDK 长连接 + MediaPipe 人脸特征 + SQLite)
====================================================================
启动:    python feishu_bot.example.py

⚠️ 使用前请设置环境变量:
  export FEISHU_APP_ID=cli_xxxxxxxx
  export FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx

或者将此文件复制为 feishu_bot.py 并填入真实的 APP_ID / APP_SECRET。
feishu_bot.py 已在 .gitignore 中，不会被上传到 GitHub。
"""

import json, time, sys, threading, queue, sqlite3, os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

import lark_oapi as lark
from lark_oapi.api.im.v1 import *


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# 配置（通过环境变量加载，避免硬编码密钥）
# ---------------------------------------------------------------------------
APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

if not APP_ID or not APP_SECRET:
    _log("[ERROR] 请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
    _log("[提示] 或将此文件复制为 feishu_bot.py，直接填入真实的 APP_ID 和 APP_SECRET")
    _log("[提示] feishu_bot.py 已在 .gitignore 中，不会被上传到 GitHub")
    sys.exit(1)

DB_PATH = "door_faces.db"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "face_landmarker.task")

# ---------------------------------------------------------------------------
# SQLite: 人脸特征库
# ---------------------------------------------------------------------------
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute("""
    CREATE TABLE IF NOT EXISTS faces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,              -- 飞书用户 open_id
        user_name TEXT DEFAULT '',          -- 飞书用户名 (可选)
        embedding BLOB NOT NULL,            -- 人脸特征向量 (float32 二进制)
        image_key TEXT DEFAULT '',          -- 飞书图片 key (溯源)
        created_at REAL DEFAULT (strftime('%s','now'))
    )
""")
_conn.commit()


def _save_embedding(user_id: str, emb: np.ndarray, image_key: str = ""):
    """保存人脸特征到 SQLite"""
    _conn.execute(
        "INSERT INTO faces (user_id, embedding, image_key) VALUES (?, ?, ?)",
        (user_id, emb.astype(np.float32).tobytes(), image_key),
    )
    _conn.commit()
    _log(f"[DB] 特征已入库 user={user_id} dim={len(emb)}")


# ---------------------------------------------------------------------------
# MediaPipe Face Landmarker (IMAGE 模式, 单次检测)
# ---------------------------------------------------------------------------
_face_landmarker: vision.FaceLandmarker | None = None


def _get_landmarker():
    global _face_landmarker
    if _face_landmarker is None:
        if not os.path.exists(MODEL_PATH):
            _log("[AI] 模型文件未找到, 使用模拟模式")
            return None
        opts = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
        )
        _face_landmarker = vision.FaceLandmarker.create_from_options(opts)
    return _face_landmarker


# ---------------------------------------------------------------------------
# 人脸特征提取: MediaPipe 468 landmarks → 归一化几何特征向量 (256 维)
# ---------------------------------------------------------------------------
def _extract_embedding(image_bytes: bytes) -> np.ndarray | None:
    lm = _get_landmarker()
    if lm is None:
        _log("[AI] 模型未找到, 模拟模式")
        return np.random.randn(256).astype(np.float32)

    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        _log("[AI] 图片解码失败")
        return None

    _log(f"[AI] 图片尺寸 {img.shape[1]}x{img.shape[0]}")

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = lm.detect(mp_img)

    if not result.face_landmarks:
        _log("[AI] MediaPipe 未检测到人脸")
        return None

    _log(f"[AI] 检测到人脸, landmarks={len(result.face_landmarks[0])}")

    h, w = img.shape[:2]
    pts = np.array([[lm.x * w, lm.y * h, lm.z * w] for lm in result.face_landmarks[0]], dtype=np.float32)
    nose_tip = pts[1]
    left_eye = pts[33]
    right_eye = pts[263]
    eye_dist = np.linalg.norm(left_eye - right_eye)
    if eye_dist < 1:
        _log("[AI] 眼距过小, 人脸质量不合格")
        return None

    pts -= nose_tip
    pts /= eye_dist
    indices = np.linspace(0, 467, 64, dtype=int)
    sampled = pts[indices]
    feat1 = sampled.flatten()
    feat2 = np.linalg.norm(sampled, axis=1)
    emb = np.concatenate([feat1, feat2]).astype(np.float32)
    emb = emb / (np.linalg.norm(emb) + 1e-8)
    _log(f"[AI] 特征向量 {len(emb)} 维, norm={np.linalg.norm(emb):.3f}")
    return emb


# ---------------------------------------------------------------------------
# 人脸验证: 与库中所有特征比对, 返回最佳匹配
# ---------------------------------------------------------------------------
def _match_face(emb: np.ndarray, threshold: float = 0.6) -> dict | None:
    """在 SQLite 中查找最相似的人脸, 相似度 > threshold 返回匹配"""
    rows = _conn.execute("SELECT id, user_id, user_name, embedding FROM faces").fetchall()
    best = None
    best_sim = -1.0
    emb = emb / (np.linalg.norm(emb) + 1e-8)

    for row in rows:
        stored = np.frombuffer(row[3], dtype=np.float32)
        stored = stored / (np.linalg.norm(stored) + 1e-8)
        sim = float(np.dot(emb, stored))  # cosine similarity (归一化后即点积)
        if sim > best_sim:
            best_sim = sim
            best = {"id": row[0], "user_id": row[1], "user_name": row[2], "similarity": sim}

    if best and best["similarity"] > threshold:
        return best
    return None


# ---------------------------------------------------------------------------
# SDK 初始化
# ---------------------------------------------------------------------------
_api = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).log_level(lark.LogLevel.INFO).build()
_q = queue.Queue()


def _worker():
    while True:
        t = _q.get()
        try:
            if t["tp"] == "text":
                h_text(t["mid"], t["ct"])
            elif t["tp"] == "register":
                h_register(t["mid"], t["ik"], t["uid"])
            elif t["tp"] == "verify":
                h_verify(t["mid"], t["ik"])
            elif t["tp"] == "delete":
                h_delete(t["mid"], t["ik"], t["uid"])
        except Exception as e:
            _log(f"[W] {type(e).__name__}: {e}")
            import traceback; traceback.print_exc(file=sys.stderr)
        finally:
            _q.task_done()


threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# 事件接收 (< 0.1s 入队)
# ---------------------------------------------------------------------------
_user_intent: dict = {}


def on_message(ev):
    try:
        msg = ev.event.get("message", {})
        mt, mid, ct = msg.get("message_type"), msg.get("message_id"), msg.get("content", "{}")
        sd = ev.event.get("sender", {}).get("sender_id", {})
        uid = sd.get("open_id") or sd.get("union_id") or "unknown"
        _log(f"[收] {mt} {mid} user={uid}")

        if mt == "text":
            txt = json.loads(ct).get("text", "").strip()
            if txt == "开门":
                _user_intent[uid] = "verify"
                _log(f"[意图] {uid} → 验证模式")
            elif txt in ("离职", "删除"):
                _user_intent[uid] = "delete"
                _log(f"[意图] {uid} → 删除模式")
            _q.put({"tp": "text", "mid": mid, "ct": ct, "uid": uid})

        elif mt == "image":
            ik = json.loads(ct).get("image_key", "")
            if ik:
                intent = _user_intent.pop(uid, "register")
                _q.put({"tp": intent, "mid": mid, "ik": ik, "uid": uid})

        elif mt == "post":
            for para in json.loads(ct).get("content", [[]]):
                for e in para:
                    if e.get("tag") == "img":
                        intent = _user_intent.pop(uid, "register")
                        _q.put({"tp": intent, "mid": mid, "ik": e.get("image_key", ""), "uid": uid})
    except Exception as ex:
        _log(f"[收] err: {ex}")


# ---------------------------------------------------------------------------
# 文本
# ---------------------------------------------------------------------------
def h_text(mid, ct):
    try:
        txt = json.loads(ct).get("text", "").strip()
    except json.JSONDecodeError:
        txt = ""
    _log(f"[文] {txt[:30]}")

    if txt == "开门":
        reply(mid, "请发送一张你的正面照片用于身份验证。")
    elif txt == "离职" or txt == "删除":
        reply(mid, "请发送一张你的正面照片以确认身份，验证通过后将删除你的门禁权限。")
    else:
        reply(mid, "发送照片即可开通门禁权限。\n发送「开门」进行人脸验证开门。")


# ---------------------------------------------------------------------------
# 注册: 发照片 → 提取特征 → 入库
# ---------------------------------------------------------------------------
def h_register(mid, ik, uid):
    _log(f"[注册] mid={mid} key={ik} user={uid}")

    data = _download(mid, ik)
    if not data:
        _log("[注册] 下载失败")
        return reply(mid, "图片下载失败，请稍后重试。")
    _log(f"[注册] 下载成功 {len(data)} bytes")

    emb = _extract_embedding(data)
    if emb is None:
        _log("[注册] 未检测到人脸")
        return reply(mid, "未检测到人脸，请发送一张正面免冠照片。")
    _log(f"[注册] 特征提取成功 dim={len(emb)}")

    _save_embedding(uid, emb, ik)
    count = _conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    _log(f"[注册] 入库完成, 当前共 {count} 人")
    reply(mid, f"人脸注册成功！当前门禁系统已录入 {count} 人。")


# ---------------------------------------------------------------------------
# 验证: 发照片 → 提取特征 → 比对 → 开门
# ---------------------------------------------------------------------------
def h_verify(mid, ik):
    _log(f"[验证] {mid} {ik}")

    if not ik:
        reply(mid, "请发送一张你的正面照片用于验证。")
        return

    data = _download(mid, ik)
    if not data:
        return reply(mid, "图片下载失败，请稍后重试。")

    emb = _extract_embedding(data)
    if emb is None:
        return reply(mid, "未检测到人脸，请重新发送。")

    match = _match_face(emb)
    if match:
        _log(f"[MQTT] 开门! user={match['user_id']} sim={match['similarity']:.3f}")
        reply(mid, f"身份验证通过，门禁已开启。\n相似度: {match['similarity']:.1%}")
    else:
        reply(mid, "人脸验证失败，未在门禁系统中找到匹配记录。")


# ---------------------------------------------------------------------------
# 删除: 发「离职」→ 发照片验证 → 匹配成功则删除
# ---------------------------------------------------------------------------
def h_delete(mid, ik, uid):
    _log(f"[删除] {mid} {ik} user={uid}")

    data = _download(mid, ik)
    if not data:
        return reply(mid, "图片下载失败，请稍后重试。")

    emb = _extract_embedding(data)
    if emb is None:
        return reply(mid, "未检测到人脸，请重新发送。")

    match = _match_face(emb, threshold=0.6)
    if not match:
        return reply(mid, "人脸验证失败，无法确认身份，删除已取消。")

    _conn.execute("DELETE FROM faces WHERE user_id = ?", (match["user_id"],))
    _conn.commit()
    remaining = _conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    _log(f"[删除] 已删除 user={match['user_id']} 剩余 {remaining} 人")
    reply(mid, f"身份确认成功。你的门禁权限已被删除。\n当前系统剩余 {remaining} 人。")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _download(mid, ik):
    try:
        req = lark.BaseRequest.builder() \
            .http_method(lark.HttpMethod.GET) \
            .uri(f"/open-apis/im/v1/messages/{mid}/resources/{ik}") \
            .token_types({lark.AccessTokenType.TENANT}) \
            .queries([("type", "image")]) \
            .build()
        resp = _api.request(req)
        if resp.code != 0:
            _log(f"[下] code={resp.code}")
            return None
        return resp.raw.content
    except Exception as e:
        _log(f"[下] {e}")
        return None


def reply(mid, text):
    try:
        req = ReplyMessageRequest.builder().message_id(mid) \
            .request_body(ReplyMessageRequestBody.builder()
                          .content(json.dumps({"text": text})).msg_type("text").build()).build()
        resp = _api.im.v1.message.reply(req)
        _log(f"[复] {'OK' if resp.success() else f'FAIL {resp.code}'}")
    except Exception as e:
        _log(f"[复] {e}")


# ---------------------------------------------------------------------------
# 飞书组织事件: 员工离职 → 自动删除门禁
# ---------------------------------------------------------------------------
def on_user_deleted(ev):
    try:
        uid = ev.event.get("open_id") or ev.event.get("user_id", "unknown")
        _log(f"[离职] 员工离开组织 user={uid}")

        cnt = _conn.execute("SELECT COUNT(*) FROM faces WHERE user_id = ?", (uid,)).fetchone()[0]
        if cnt > 0:
            _conn.execute("DELETE FROM faces WHERE user_id = ?", (uid,))
            _conn.commit()
            rem = _conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
            _log(f"[离职] 已删除 {cnt} 条记录, 剩余 {rem} 人")
        else:
            _log(f"[离职] user={uid} 未注册门禁, 跳过")
    except Exception as ex:
        _log(f"[离职] err: {ex}")


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_customized_event("im.message.receive_v1", on_message) \
        .register_p2_contact_user_deleted_v3(on_user_deleted) \
        .build()
    ws = lark.ws.Client(app_id=APP_ID, app_secret=APP_SECRET,
                        event_handler=handler, log_level=lark.LogLevel.INFO)
    ws.on_reconnecting = lambda: _log("[WS] 重连中...")
    ws.on_reconnected = lambda: _log("[WS] 已重连")
    _log("门禁机器人启动 (长连接 + MediaPipe + SQLite)")
    ws.start()
