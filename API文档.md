# LabCV API 对接文档 v3.0

> 服务地址: `http://<服务器IP>:8000`  
> Swagger 文档: `http://<服务器IP>:8000/docs`  
> 所有接口返回 JSON, 跨域已放开

---

## 1. 人脸注册

上传照片，提取人脸特征并入库。

```
POST /api/face/register
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 正面免冠照片 (jpg/png) |
| user_id | String | 否 | 用户标识，为空则用文件名 |
| user_name | String | 否 | 用户姓名 |

**请求示例 (curl):**
```bash
curl -X POST http://localhost:8000/api/face/register \
  -F "file=@photo.jpg" \
  -F "user_id=zhangsan" \
  -F "user_name=张三"
```

**请求示例 (JS fetch):**
```js
const form = new FormData();
form.append("file", fileInput.files[0]);
form.append("user_id", "zhangsan");
form.append("user_name", "张三");

const res = await fetch("http://localhost:8000/api/face/register", {
  method: "POST",
  body: form,
});
const data = await res.json();
// { success: true, message: "注册成功, zhangsan", total_faces: 10 }
```

**成功响应:**
```json
{
  "success": true,
  "message": "注册成功, zhangsan",
  "total_faces": 10
}
```

**失败响应 (HTTP 400):**
```json
{
  "detail": "未检测到人脸，请上传正面免冠照片"
}
```

---

## 2. 人脸验证

上传照片，与库中已注册人脸比对，返回匹配结果。

```
POST /api/face/verify
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 人脸照片 |

**请求示例:**
```js
const form = new FormData();
form.append("file", fileInput.files[0]);

const res = await fetch("http://localhost:8000/api/face/verify", {
  method: "POST",
  body: form,
});
const data = await res.json();
```

**匹配成功:**
```json
{
  "success": true,
  "matched": true,
  "user_id": "zhangsan",
  "user_name": "张三",
  "similarity": 0.9876,
  "message": "验证通过，相似度 98.8%"
}
```

**未匹配:**
```json
{
  "success": true,
  "matched": false,
  "user_id": "",
  "user_name": "",
  "similarity": 0,
  "message": "未匹配到已注册用户"
}
```

---

## 3. 删除人脸

通过 user_id 删除已注册的人脸记录。

```
DELETE /api/face/{user_id}
```

**请求示例:**
```js
const res = await fetch("http://localhost:8000/api/face/zhangsan", {
  method: "DELETE",
});
const data = await res.json();
```

**响应:**
```json
{
  "success": true,
  "deleted_count": 1,
  "remaining": 9,
  "message": "已删除 1 条记录"
}
```

---

## 4. 人脸列表

获取所有已注册用户。

```
GET /api/face/list
```

**响应:**
```json
{
  "total": 10,
  "users": [
    {
      "id": 1,
      "user_id": "zhangsan",
      "user_name": "张三",
      "created_at": 1718400000
    }
  ]
}
```

---

## 5. 开门指令

触发门禁开门 (当前为模拟，实际需对接 MQTT)。

```
POST /api/door/open
Content-Type: application/x-www-form-urlencoded
```

| 参数 | 类型 | 说明 |
|------|------|------|
| user_id | String | 开门用户标识 |

**响应:**
```json
{
  "success": true,
  "message": "开门指令已发送 user=zhangsan"
}
```

---

## 6. 系统状态

```
GET /api/status
```

**响应:**
```json
{
  "face_registered": 10,
  "face_model": "MediaPipe Face Landmarker (468 pts → 256 dims)",
  "fire_model": "YOLOv8s (fire-yolov8s.pt)",
  "drowsiness_model": "MediaPipe Face + Pose Landmarker"
}
```

---

## 7. WebSocket 实时告警

接收瞌睡检测、火灾检测、**陌生人检测**的实时推送。

```
ws://<服务器IP>:8000/ws/alerts
```

**推送数据格式:**
```json
{
  "timestamp": 1718400000.123,
  "is_drowsy": false,
  "level": "normal",
  "message": "正常",
  "face_detected": true,
  "ear_avg": 0.35,
  "mar": 0.12,
  "eyes_closed_sec": 0,
  "head_droop_sec": 0,
  "fire": {
    "has_fire": false,
    "has_smoke": false,
    "level": "normal",
    "message": "",
    "fire_count": 0,
    "smoke_count": 0
  },
  "stranger": {
    "stranger_alert": false,
    "is_stranger": false,
    "face_reliable": true,
    "matched_user_id": "",
    "matched_user_name": "",
    "similarity": 0.0,
    "face_yaw": 5.2,
    "face_pitch": -3.1,
    "face_size": 180,
    "unmatched_count": 0,
    "matched_count": 15,
    "level": "normal",
    "message": "已识别: 张三"
  }
}
```

| 字段 | 说明 |
|------|------|
| level | 综合告警级别: `normal` / `warning` / `critical` |
| is_drowsy | 是否检测到瞌睡 |
| ear_avg | 眼睛纵横比 (< 0.25 为闭眼) |
| mar | 嘴巴纵横比 (> 0.7 为打哈欠) |
| fire.level | 火灾告警级别 |
| fire.has_fire | 是否检测到火焰 |
| fire.has_smoke | 是否检测到烟雾 |
| **stranger.stranger_alert** | **是否触发陌生人告警（多帧确认后）** |
| **stranger.is_stranger** | **当前帧是否未匹配到已注册用户** |
| **stranger.face_reliable** | **人脸角度是否适合匹配（|yaw|<30° 为可靠）** |
| **stranger.matched_user_id** | **匹配到的用户ID（空=未匹配）** |
| **stranger.matched_user_name** | **匹配到的用户姓名** |
| **stranger.similarity** | **人脸相似度（0~1）** |
| **stranger.face_yaw** | **人脸偏航角（度），绝对值>30°视为侧脸** |
| **stranger.face_pitch** | **人脸俯仰角（度）** |
| **stranger.face_size** | **检测到的人脸宽度（像素）** |
| **stranger.unmatched_count** | **连续未匹配帧数（达到阈值触发告警）** |
| **stranger.matched_count** | **连续匹配帧数（确认身份后稳定输出）** |
| **stranger.level** | 陌生人告警级别: `normal` / `warning` |
| **stranger.message** | 陌生人检测描述信息 |

### 陌生人检测防误报机制

| 机制 | 说明 |
|------|------|
| **侧脸过滤** | 当 |yaw| > 30° 时，`face_reliable=false`，跳过人脸匹配，不触发陌生人告警 |
| **多帧确认** | 连续 20 帧未匹配（~2秒@10fps）才触发 `stranger_alert=true` |
| **匹配稳定** | 连续 5 帧匹配成功才确认身份，输出 `matched_user_name` |
| **计数器衰减** | 人脸短暂丢失/遮挡时缓慢衰减计数，不立即重置 |

**JS 连接示例:**
```js
const ws = new WebSocket("ws://localhost:8000/ws/alerts");
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.level === "critical") {
    console.error("严重告警:", data.message);
  }
};
```

---

## 完整前端对接流程

### 注册门禁
```
1. 管理员在后台录入员工信息
2. 调用 POST /api/face/register 上传员工照片
3. 返回 success → 注册完成
```

### 刷脸开门
```
1. 摄像头采集人脸照片
2. 调用 POST /api/face/verify 上传照片
3. matched=true → 调用 POST /api/door/open 开门
4. matched=false → 提示"未注册"
```

### 员工离职
```
1. 调用 DELETE /api/face/{user_id} 删除记录
2. 飞书组织事件自动触发删除 (需配合 feishu_bot.py)
```

### 实时监控大屏
```
1. 连接 ws://host:8000/ws/alerts
2. 监听推送，在 UI 上展示瞌睡/火灾告警
```

---

## 启动服务

```bash
cd D:\yt\labcv
pip install fastapi uvicorn opencv-python mediapipe numpy
python api_server.py
# 访问 http://localhost:8000/docs 查看 Swagger 交互文档
```
