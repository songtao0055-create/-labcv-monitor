<template>
  <view class="page">
    <!-- 门禁控制 -->
    <view class="card">
      <text class="card-title">🚪 门禁控制</text>
      <text class="card-desc">远程开启中控室/测试区门禁</text>
      <button class="ctrl-btn door-btn" :disabled="doorOpening" @click="doDoorOpen">
        {{ doorOpening ? '发送中...' : '一键开门' }}
      </button>
    </view>

    <!-- 报警器控制 -->
    <view class="card">
      <text class="card-title">🔕 报警器控制</text>
      <text class="card-desc">远程静音中控台声光报警器</text>
      <button class="ctrl-btn mute-btn" @click="doMute">
        远程静音
      </button>
    </view>

    <!-- 云台控制 -->
    <view class="card">
      <text class="card-title">🎥 云台控制</text>
      <text class="card-desc">控制摄像头方向（需支持 ONVIF）</text>
      <view class="ptz-grid">
        <view class="ptz-row">
          <view class="ptz-btn" @click="ptz('up')">▲</view>
        </view>
        <view class="ptz-row">
          <view class="ptz-btn" @click="ptz('left')">◀</view>
          <view class="ptz-btn ptz-home" @click="ptz('home')">🏠</view>
          <view class="ptz-btn" @click="ptz('right')">▶</view>
        </view>
        <view class="ptz-row">
          <view class="ptz-btn" @click="ptz('down')">▼</view>
        </view>
      </view>
    </view>

    <!-- 操作日志 -->
    <view class="card">
      <text class="card-title">📋 操作记录</text>
      <view v-if="logs.length === 0" class="log-empty">暂无操作记录</view>
      <view v-for="(log, i) in logs" :key="i" class="log-item">
        <text class="log-time">{{ log.time }}</text>
        <text class="log-action">{{ log.action }}</text>
        <text class="log-result" :class="log.ok ? 'ok' : 'fail'">{{ log.ok ? '✓' : '✗' }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { doorOpen } from '@/utils/api'

const doorOpening = ref(false)
const logs = ref([])

function addLog(action, ok) {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  logs.value.unshift({
    time: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
    action,
    ok,
  })
  if (logs.value.length > 20) logs.value.length = 20
}

async function doDoorOpen() {
  doorOpening.value = true
  try {
    await doorOpen('admin')
    addLog('远程开门', true)
    uni.showToast({ title: '开门指令已发送', icon: 'success' })
  } catch {
    addLog('远程开门', false)
    uni.showToast({ title: '开门失败', icon: 'error' })
  } finally {
    doorOpening.value = false
  }
}

function doMute() {
  // 模拟静音（实际需对接 MQTT 报警器控制）
  addLog('报警器远程静音', true)
  uni.showToast({ title: '静音指令已发送（模拟）', icon: 'success' })
}

function ptz(dir) {
  addLog(`云台: ${dir}`, true)
  uni.showToast({ title: `云台${dir}指令已发送（模拟）`, icon: 'success' })
}
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; }

.card {
  background: $bg-card; border-radius: $radius-lg; padding: $spacing-lg;
  margin-bottom: $spacing-md;
}
.card-title { font-size: 30rpx; font-weight: 600; display: block; }
.card-desc { font-size: 24rpx; color: $text-secondary; display: block; margin-top: 4rpx; margin-bottom: $spacing-md; }

.ctrl-btn {
  width: 100%; height: 80rpx; border-radius: $radius-md; border: none;
  font-size: 30rpx; font-weight: 600;
  &:disabled { opacity: 0.4; }
}
.door-btn { background: linear-gradient(135deg, $accent-blue, #7c5ce7); color: #fff; }
.mute-btn { background: linear-gradient(135deg, $warning, $orange); color: #1a1a2e; }

.ptz-grid { display: flex; flex-direction: column; align-items: center; gap: $spacing-sm; }
.ptz-row { display: flex; gap: $spacing-md; }
.ptz-btn {
  width: 100rpx; height: 100rpx; border-radius: 50%; background: rgba(255,255,255,0.08);
  display: flex; align-items: center; justify-content: center; font-size: 36rpx;
  &:active { background: rgba($accent, 0.2); }
}
.ptz-home { font-size: 48rpx; }

.log-empty { text-align: center; color: $text-muted; padding: $spacing-md; font-size: 24rpx; }
.log-item { display: flex; gap: $spacing-sm; padding: 8rpx 0; font-size: 24rpx; }
.log-time { color: $text-muted; width: 100rpx; flex-shrink: 0; }
.log-action { flex: 1; color: $text-secondary; }
.log-result.ok { color: $success; }
.log-result.fail { color: $danger; }
</style>
