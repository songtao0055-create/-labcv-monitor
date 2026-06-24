"""
LabCV 检测 API 服务 (FastAPI)
提供 REST 接口 + WebSocket 实时推送: 瞌睡检测 + 火灾检测

启动方式:
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
    python -m src.api.server
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..drowsiness.config import StreamConfig
from ..drowsiness.video_processor import VideoProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api")

# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

video_processor: VideoProcessor | None = None

# WebSocket 连接池
_ws_clients: set[WebSocket] = set()

# ---------------------------------------------------------------------------
# 应用生命周期
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期: 启动时不自动开始处理, 等待前端调用 /api/stream/start"""
    logger.info("LabCV 检测 API 服务启动 (瞌睡检测 + 火灾检测)")
    yield
    global video_processor
    if video_processor and video_processor.is_running:
        video_processor.stop()
    logger.info("LabCV 检测 API 服务关闭")


app = FastAPI(
    title="LabCV 检测服务",
    description="基于 MediaPipe 的瞌睡检测 + YOLOv8 火灾检测 API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 状态 / 历史
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def get_status():
    """获取当前检测状态快照 (瞌睡 + 火灾)"""
    if video_processor is None:
        return {"status": "idle", "message": "视频处理未启动"}
    return video_processor.snapshot()


@app.get("/api/history")
async def get_history(limit: int = 20):
    """获取最近瞌睡检测记录"""
    if video_processor is None:
        return {"history": []}
    return {"history": video_processor.get_history(limit)}


@app.get("/api/alerts")
async def get_alerts(limit: int = 20):
    """获取最近瞌睡告警记录"""
    if video_processor is None:
        return {"alerts": []}
    return {"alerts": video_processor.get_alerts(limit)}


# ---------------------------------------------------------------------------
# 火灾检测
# ---------------------------------------------------------------------------


@app.get("/api/fire/status")
async def fire_status():
    """获取火灾检测当前状态"""
    if video_processor is None:
        return {"status": "idle", "message": "视频处理未启动"}
    if not video_processor.fire_enabled:
        return {"status": "disabled", "message": "火灾检测模型未加载，功能不可用"}
    return video_processor.latest_fire_result


@app.get("/api/fire/history")
async def fire_history(limit: int = 20):
    """获取最近火灾检测记录"""
    if video_processor is None:
        return {"history": []}
    return {"history": video_processor.get_fire_history(limit)}


@app.get("/api/fire/alerts")
async def fire_alerts(limit: int = 20):
    """获取最近火灾告警记录"""
    if video_processor is None:
        return {"alerts": []}
    return {"alerts": video_processor.get_fire_alerts(limit)}


# ---------------------------------------------------------------------------
# 视频流控制
# ---------------------------------------------------------------------------


@app.post("/api/stream/start")
async def stream_start(source: str = "0", fps: int = 30, width: int = 640, height: int = 480):
    """
    启动视频流处理

    - source: 视频源 (默认 "0"=USB摄像头; 支持 RTSP URL 或本地文件路径)
    - fps: 处理帧率
    - width, height: 处理分辨率
    """
    global video_processor

    if video_processor and video_processor.is_running:
        return {"success": False, "message": "视频流已在运行, 请先调用 /api/stream/stop"}

    cfg = StreamConfig(source=source, fps=fps, frame_width=width, frame_height=height)
    video_processor = VideoProcessor(cfg)
    video_processor.start()

    logger.info(f"视频流已启动: source={source}, fps={fps}, {width}x{height}")
    return {
        "success": True,
        "message": "视频流已启动",
        "source": source,
        "fps": fps,
        "resolution": f"{width}x{height}",
        "fire_enabled": video_processor.fire_enabled,
    }


@app.post("/api/stream/stop")
async def stream_stop():
    """停止视频流处理"""
    global video_processor
    if video_processor is None or not video_processor.is_running:
        return {"success": False, "message": "视频流未在运行"}
    video_processor.stop()
    return {"success": True, "message": "视频流已停止"}


# ---------------------------------------------------------------------------
# WebSocket —— 实时推送检测结果
# ---------------------------------------------------------------------------


@app.websocket("/ws/alerts")
async def websocket_alerts(ws: WebSocket):
    """
    WebSocket 端点: 持续推送检测结果 JSON (含瞌睡 + 火灾)
    前端连接后每 500ms 自动推送最新一帧的检测数据
    """
    await ws.accept()
    _ws_clients.add(ws)
    logger.info(f"WebSocket 客户端连接, 当前连接数: {len(_ws_clients)}")
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

            if video_processor:
                data = video_processor.snapshot()
                await ws.send_json(data)
            else:
                await ws.send_json({"status": "idle", "message": "视频处理未启动"})

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开")
    except Exception:
        logger.exception("WebSocket 异常")
    finally:
        _ws_clients.discard(ws)


@app.websocket("/ws/stream")
async def websocket_stream(ws: WebSocket):
    """WebSocket 端点: 按需推送 (仅在检测到瞌睡或火灾时推送, 减少前端负担)"""
    await ws.accept()
    _ws_clients.add(ws)
    logger.info(f"WebSocket(alerts-only) 客户端连接, 当前连接数: {len(_ws_clients)}")
    last_drowsy_ts = 0.0
    last_fire_ts = 0.0
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

            if video_processor:
                r = video_processor.latest_result
                fr = video_processor.latest_fire_result
                should_send = False

                if r.is_drowsy and r.timestamp > last_drowsy_ts:
                    last_drowsy_ts = r.timestamp
                    should_send = True
                if fr.level != "normal" and fr.timestamp > last_fire_ts:
                    last_fire_ts = fr.timestamp
                    should_send = True

                if should_send:
                    await ws.send_json(video_processor.snapshot())

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("WebSocket(alerts-only) 客户端断开")
    except Exception:
        logger.exception("WebSocket 异常")
    finally:
        _ws_clients.discard(ws)


# ---------------------------------------------------------------------------
# 直接启动
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=8000, reload=True)
