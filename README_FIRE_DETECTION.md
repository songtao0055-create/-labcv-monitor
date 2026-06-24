# LabCV 火灾+烟雾检测模型 项目文档

## 项目概述

基于 YOLOv8s 训练的双类目标检测模型，用于实验室环境中**火焰（fire）**和**烟雾（smoke）**的实时检测。

---

## 模型性能

| 指标 | 值 | 说明 |
|------|-----|------|
| **总体 mAP50** | **0.779** | 综合检测精度 |
| **总体 mAP50-95** | **0.460** | 高 IoU 下精度 |
| **Precision** | **0.784** | 每 100 次报警约 22 次误报 |
| **Recall** | **0.711** | 约 71% 目标被检出 |
| **🔥 fire mAP50** | **0.735** | 火焰检测良好 |
| **💨 smoke mAP50** | **0.823** | 烟雾检测优秀 |
| **推理速度** | ~7.5ms/帧 (GPU) | 133 FPS，实时绰绰有余 |
| **模型大小** | 64 MB | YOLOv8s, 11M 参数 |

### 不同尺寸火焰检出率

| 尺寸 | 图幅占比 | 检出率 | 评估 |
|------|---------|--------|------|
| 超小 | <2% (1080p 上 <40×40px) | ~62% | ⚠️ 远距离小火苗会漏 |
| 小 | 2-5% | ~87% | 基本可检 |
| 中 | 5-15% | ~100% | ✅ |
| 大 | >15% | ~100% | ✅ |

---

## 项目文件说明

### 核心模型

| 文件 | 用途 |
|------|------|
| `models/fire-yolov8s.pt` | **最终训练好的烟火检测模型**（64MB，唯一需要的模型文件） |
| `models/fire-yolov8n.pt` | 旧版 nano 模型（精度较低，可删除） |
| `models/yolov8n.pt` | COCO 原始预训练模型（基底，保留备用） |

### 数据集

| 文件/目录 | 用途 |
|------|------|
| `data/fire_smoke_dataset/data.yaml` | 数据集配置文件（类别、路径） |
| `data/fire_smoke_dataset/train/` | 训练集（16181 张图片） |
| `data/fire_smoke_dataset/val/` | 验证集（3099 张图片） |
| `VOC2020/` | VOC2020 火焰标注数据（已合并到以上数据集） |

### 测试脚本

| 文件 | 用途 |
|------|------|
| `test_camera.py` | **摄像头实时检测测试**——连 USB 摄像头即可测试 |
| `test_rtsp.py` | RTSP 网络摄像头检测（适合连接实验室监控摄像头） |
| `run.py` | 主程序入口（包含摄像头/RTSP/图片三种模式） |
| `main.py` | 旧版主入口 |

### 预处理

| 文件 | 用途 |
|------|------|
| `prepare_dataset.py` | 数据预处理——合并 VOC2020 + archive 数据集，生成 YOLO 格式标注 |
| `convert_voc_to_yolo.py` | VOC XML → YOLO txt 格式转换 |

### 其他

| 文件 | 用途 |
|------|------|
| `requirements.txt` | Python 依赖列表 |
| `方案书_LabCV.md` | 原项目方案书 |

---

## 使用方法

### 1. 环境准备

```bash
pip install ultralytics torch opencv-python
```

### 2. 摄像头实时测试

```bash
python test_camera.py
```

- 使用默认摄像头
- 按 `q` 退出
- 可调整 `CONF` 变量控制灵敏度（默认 0.3，降低可减少漏检但增加误报）

### 3. RTSP 监控摄像头测试

```bash
python test_rtsp.py rtsp://your-camera-ip:554/stream
```

### 4. 在代码中调用

```python
from ultralytics import YOLO

model = YOLO("models/fire-yolov8s.pt")
results = model("image.jpg", conf=0.25)  # predict

for r in results:
    for box in r.boxes:
        cls_id = int(box.cls[0])
        name = "fire" if cls_id == 0 else "smoke"
        conf = float(box.conf[0])
        print(f"检测到 {name}, 置信度: {conf:.2f}")
```

---

## 实验室实景微调指南

> 不需要在实验室点火！核心思路是用**正常场景（负样本）**防止误报。

### 步骤 1：采集实验室实景图片

1. 用实验室摄像头对着正常环境录制视频
2. 每隔几秒抽一帧，收集 **200-500 张**正常场景图片
3. 确保覆盖不同时段（白天/晚上/开灯/关灯），不同角度

```bash
# 用 ffmpeg 从视频抽帧（每5秒1帧）
ffmpeg -i lab_video.mp4 -vf fps=1/5 lab_frames/img_%04d.jpg
```

### 步骤 2：标注（可选）

只需标注**可能被误判的场景**（如强光反射、发热设备、焊接光等）：

```bash
# 用 labelImg 标注工具
pip install labelImg
labelImg
```

### 步骤 3：加入训练集微调

把采集的图片和标注按目录结构放好，运行微调训练：

```python
from ultralytics import YOLO

# 加载现有模型继续训练
model = YOLO("models/fire-yolov8s.pt")

model.train(
    data="data/lab_custom/data.yaml",   # 新的数据集配置
    epochs=20,                          # 微调不需要太多轮
    lr0=0.0005,                         # 用更小的学习率
    freeze=10,                          # 冻结前 10 层，只微调检测头
    batch=4,                            # 根据显存调整
    device="cuda",
    name="lab_finetune",
)
```

### 步骤 4：验证

对比微调前后的误报率：

```python
# 在实景图片上测试
model = YOLO("models/fire-yolov8s.pt")  # 或微调后的模型
results = model("lab_images/", conf=0.3)

false_alarms = 0
for r in results:
    if len(r.boxes) > 0:
        false_alarms += 1
        print(f"⚠️ 误报: {r.path}")

print(f"误报率: {false_alarms}/{len(results)} ({false_alarms/len(results)*100:.1f}%)")
```

### 关键参数说明

| 参数 | 作用 | 建议值 |
|------|------|--------|
| `conf` | 置信度阈值 | 0.25（默认）/ 0.15（更敏感）/ 0.4（减少误报） |
| `imgsz` | 输入分辨率 | 640（默认）/ 1280（远距离检测，但慢 4 倍） |
| `freeze` | 冻结层数 | 10（微调时冻结 backbone，只训练检测头） |
| `lr0` | 学习率 | 微调用 0.0005 或更低 |
| `epochs` | 微调轮数 | 10-30 即可 |

---

> ★目前海康录像机、网络摄像机，网络球机的RTSP单播取流格式如下（车载录像机不支持RTSP取流）：
> rtsp://用户名:密码@IP:554/Streaming/Channels/101
> →录像机示例：
> 取第1个通道的主码流预览
> rtsp://admin:hik12345@10.16.4.25:554/Streaming/Channels/101
> 取第1个通道的子码流预览
> rtsp://admin:hik12345@10.16.4.25:554/Streaming/Channels/102
> 取第1个通道的第三码流预览
> rtsp://admin:hik12345@10.16.4.25:554/Streaming/Channels/103
> 取第12个通道的主码流预览
> rtsp://admin:hik12345@10.16.4.25:554/Streaming/Channels/1201
> →网络摄像机/网络球机示例：
> 取主码流的URL：
> rtsp://admin:hik123456@192.168.1.64:554/Streaming/Channels/101
>
> ★如果是多播取流的话，则使用以下路径
> rtsp://用户名:密码@IP:554/Streaming/Channels/101?transportmode=multicast
> →录像机示例：
> 取第1个通道的主码流预览
> rtsp://admin:hik12345@10.16.4.25:554/Streaming/Channels/101?transportmode=unicast
>
> 最后更新：2026-06-10
