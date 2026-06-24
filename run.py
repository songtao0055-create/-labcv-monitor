"""
启动入口 —— 瞌睡检测 API 服务
    python run.py              # 启动 API 服务 (默认端口 8000)
    python run.py --source 0   # 启动时自动连接 USB 摄像头
    python run.py --source "rtsp://192.168.1.100:554/stream"  # RTSP 摄像头
    python run.py --source "test.mp4"   # 本地视频文件测试
"""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="瞌睡检测服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════╗
║       瞌睡检测服务 v1.0                   ║
║       Drowsiness Detection API           ║
╠══════════════════════════════════════════╣
║  API 文档: http://{args.host}:{args.port}/docs      ║
║  状态接口: http://{args.host}:{args.port}/api/status ║
║  WebSocket: ws://{args.host}:{args.port}/ws/alerts   ║
╚══════════════════════════════════════════╝
""")
    uvicorn.run(
        "src.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
