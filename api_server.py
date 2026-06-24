"""
LabCV 统一 API 服务 —— 人脸门禁 + 瞌睡检测 + 火灾检测
========================================================
启动:    python api_server.py
         uvicorn api_server:app --host 0.0.0.0 --port 8000
"""

import json, time, sqlite3, os, threading
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "door_faces.db")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "face_landmarker.task")

app = FastAPI(title="LabCV API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 挂载 HLS 视频目录 & 告警截图目录
_HLS_DIR = os.path.join(os.path.dirname(__file__), "hls")
os.makedirs(_HLS_DIR, exist_ok=True)
app.mount("/hls", StaticFiles(directory=_HLS_DIR), name="hls")

_IMG_DIR = os.path.join(os.path.dirname(__file__), "alerts_img")
os.makedirs(_IMG_DIR, exist_ok=True)

# 用路由方式服务告警截图（兼容性更好）
from fastapi.responses import FileResponse as _FileResponse
@app.get("/alerts_img/{filename}")
async def serve_alert_img(filename: str):
    fp = os.path.join(_IMG_DIR, filename)
    if os.path.isfile(fp):
        return _FileResponse(fp)
    raise HTTPException(404)

_face_lm: vision.FaceLandmarker | None = None
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute("""CREATE TABLE IF NOT EXISTS faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL, user_name TEXT DEFAULT '',
    embedding BLOB NOT NULL, image_key TEXT DEFAULT '',
    created_at REAL DEFAULT (strftime('%s','now'))
)""")
_conn.commit()


def _get_lm():
    global _face_lm
    if _face_lm is None:
        _face_lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.IMAGE, num_faces=1,
            min_face_detection_confidence=0.5,
        ))
    return _face_lm


# ---------------------------------------------------------------------------
# 人脸特征提取 (256 维归一化几何特征)
# ---------------------------------------------------------------------------
def extract_embedding(img_bytes: bytes) -> np.ndarray | None:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    result = _get_lm().detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if not result.face_landmarks:
        return None

    h, w = img.shape[:2]
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


def match_face(emb: np.ndarray, threshold: float = 0.6) -> dict | None:
    best, best_sim = None, -1.0
    emb = emb / (np.linalg.norm(emb) + 1e-8)
    for row in _conn.execute("SELECT id, user_id, user_name, embedding FROM faces").fetchall():
        stored = np.frombuffer(row[3], dtype=np.float32)
        stored = stored / (np.linalg.norm(stored) + 1e-8)
        sim = float(np.dot(emb, stored))
        if sim > best_sim:
            best_sim = sim
            best = {"id": row[0], "user_id": row[1], "user_name": row[2], "similarity": round(sim, 4)}
    return best if best and best["similarity"] > threshold else None


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------
class RegisterResp(BaseModel):
    success: bool
    message: str = ""
    total_faces: int = 0

class VerifyResp(BaseModel):
    success: bool
    matched: bool = False
    user_id: str = ""
    user_name: str = ""
    similarity: float = 0.0
    message: str = ""

class DeleteResp(BaseModel):
    success: bool
    deleted_count: int = 0
    remaining: int = 0
    message: str = ""

class FaceListResp(BaseModel):
    total: int
    users: list


# ---------------------------------------------------------------------------
# API 1: 人脸注册
# ---------------------------------------------------------------------------
@app.post("/api/face/register", response_model=RegisterResp)
async def face_register(file: UploadFile = File(...), user_id: str = "", user_name: str = ""):
    """上传照片注册人脸。user_id 为空时自动用文件名"""
    img = await file.read()
    emb = extract_embedding(img)
    if emb is None:
        raise HTTPException(400, "未检测到人脸，请上传正面免冠照片")

    uid = user_id or os.path.splitext(file.filename)[0]
    _conn.execute(
        "INSERT INTO faces (user_id, user_name, embedding) VALUES (?, ?, ?)",
        (uid, user_name, emb.astype(np.float32).tobytes()),
    )
    _conn.commit()
    total = _conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    return RegisterResp(success=True, message=f"注册成功, {uid}", total_faces=total)


# ---------------------------------------------------------------------------
# API 2: 人脸验证
# ---------------------------------------------------------------------------
@app.post("/api/face/verify", response_model=VerifyResp)
async def face_verify(file: UploadFile = File(...)):
    """上传照片验证身份，返回匹配结果"""
    img = await file.read()
    emb = extract_embedding(img)
    if emb is None:
        raise HTTPException(400, "未检测到人脸")

    m = match_face(emb)
    if m:
        return VerifyResp(success=True, matched=True, user_id=m["user_id"],
                          user_name=m["user_name"], similarity=m["similarity"],
                          message=f"验证通过，相似度 {m['similarity']:.1%}")
    return VerifyResp(success=True, matched=False, message="未匹配到已注册用户")


# ---------------------------------------------------------------------------
# API 3: 删除人脸
# ---------------------------------------------------------------------------
@app.delete("/api/face/{user_id}", response_model=DeleteResp)
async def face_delete(user_id: str):
    """通过 user_id 删除注册的人脸"""
    cur = _conn.execute("DELETE FROM faces WHERE user_id = ?", (user_id,))
    _conn.commit()
    rem = _conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    return DeleteResp(success=True, deleted_count=cur.rowcount, remaining=rem,
                      message=f"已删除 {cur.rowcount} 条记录")


# ---------------------------------------------------------------------------
# API 4: 人脸列表
# ---------------------------------------------------------------------------
@app.get("/api/face/list")
async def face_list():
    """返回所有已注册人脸的用户列表"""
    rows = _conn.execute("SELECT id, user_id, user_name, created_at FROM faces ORDER BY id").fetchall()
    users = [{"id": r[0], "user_id": r[1], "user_name": r[2], "created_at": r[3]} for r in rows]
    return {"total": len(users), "users": users}


# ---------------------------------------------------------------------------
# API 5: 门禁开门 (MQTT 模拟)
# ---------------------------------------------------------------------------
@app.post("/api/door/open")
async def door_open(user_id: str = ""):
    """模拟开门。实际需对接 MQTT 继电器"""
    return {"success": True, "message": f"开门指令已发送 user={user_id}"}


# ---------------------------------------------------------------------------
# API 6: 系统状态
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def system_status():
    """系统概览"""
    face_count = _conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    return {
        "face_registered": face_count,
        "face_model": "MediaPipe Face Landmarker (468 pts → 256 dims)",
        "fire_model": "YOLOv8s (fire-yolov8s.pt)",
        "drowsiness_model": "MediaPipe Face + Pose Landmarker",
        "db_path": DB_PATH,
    }


# ---------------------------------------------------------------------------
# WebSocket: 实时检测推送 (瞌睡 + 火灾)
# ---------------------------------------------------------------------------
_ws_clients: set[WebSocket] = set()


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(ws)
    except Exception:
        _ws_clients.discard(ws)


def push_alert(data: dict):
    """外部检测模块调用，推送告警到所有 WebSocket 客户端"""
    import asyncio
    for ws in list(_ws_clients):
        try:
            asyncio.create_task(ws.send_json(data))
        except Exception:
            _ws_clients.discard(ws)


class AlertPush(BaseModel):
    """检测进程 → API 服务器 告警推送格式"""
    timestamp: float
    is_drowsy: bool = False
    level: str = "normal"       # normal / warning / critical
    message: str = ""
    face_detected: bool = False
    ear_avg: float = 0.0
    mar: float = 0.0
    eyes_closed_sec: float = 0.0
    head_droop_sec: float = 0.0
    fire: dict = {}
    stranger: dict = {}
    image: str = ""             # 告警截图文件名


_last_alert: dict = {}  # 缓存最新告警数据，供 HTTP 轮询


@app.post("/api/alerts/push")
async def alerts_push(alert: AlertPush):
    """检测进程 POST 告警到此端点 → 转发 WebSocket + 缓存 HTTP"""
    global _last_alert
    data = alert.model_dump()
    # 心跳不覆盖告警截图
    if not data.get("image") and _last_alert.get("image"):
        data["image"] = _last_alert["image"]
    _last_alert = data
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
    return {"success": True, "clients": len(_ws_clients)}


@app.get("/api/alerts/latest")
async def alerts_latest():
    """HTTP 轮询：获取最新告警数据（手机真机使用）"""
    return _last_alert


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
