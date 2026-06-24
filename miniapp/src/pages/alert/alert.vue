<template>
  <view class="page">
    <view class="conn-bar" :class="store.connected ? 'connected' : 'disconnected'">
      <view class="dot"></view>
      {{ store.connected ? '服务器在线 · 实时数据' : '等待连接...' }}
      <text class="last-update" v-if="store.latest">{{ updateTime }}</text>
    </view>

    <view class="level-banner" v-if="store.latest" :class="store.level">
      <text class="level-icon">{{ levelEmoji }}</text>
      <view class="level-body">
        <text class="level-text">{{ store.latest.message }}</text>
        <text class="level-sub" v-if="store.latest.fire?.has_fire">🔥 检测到火焰</text>
        <text class="level-sub" v-if="store.latest.fire?.has_smoke">💨 检测到烟雾</text>
        <text class="level-sub" v-if="store.latest.is_drowsy">😴 检测到瞌睡行为</text>
        <text class="level-sub" v-if="store.latest.stranger?.stranger_alert">👤 陌生人警告！</text>
        <text class="level-sub" v-if="store.latest.stranger?.matched_user_id && !store.latest.stranger?.stranger_alert">
          ✅ 已识别: {{ store.latest.stranger.matched_user_name || store.latest.stranger.matched_user_id }}
        </text>
      </view>
    </view>
    <view v-else class="level-banner normal">
      <text class="level-icon">✅</text>
      <view class="level-body"><text class="level-text">一切正常</text><text class="level-sub">等待数据...</text></view>
    </view>

    <view class="data-grid" v-if="store.latest">
      <view class="data-item face-warn" v-if="!store.latest.face_detected && store.latest.is_drowsy">
        <text class="data-label">姿态告警</text><text class="data-value warn-text">无人脸</text>
      </view>
      <view class="data-item">
        <text class="data-label">眼部 EAR</text>
        <text class="data-value" :class="earClass">{{ store.latest.face_detected ? store.latest.ear_avg?.toFixed(3) : '--' }}</text>
      </view>
      <view class="data-item">
        <text class="data-label">嘴部 MAR</text>
        <text class="data-value" :class="marClass">{{ store.latest.face_detected ? store.latest.mar?.toFixed(3) : '--' }}</text>
      </view>
      <view class="data-item">
        <text class="data-label">闭眼/低头</text>
        <text class="data-value normal">{{ store.latest.eyes_closed_sec || 0 }}s / {{ store.latest.head_droop_sec || 0 }}s</text>
      </view>
      <view class="data-item">
        <text class="data-label">火焰 / 烟雾</text>
        <text class="data-value normal">{{ store.latest.fire?.fire_count || 0 }} / {{ store.latest.fire?.smoke_count || 0 }}</text>
      </view>
      <view class="data-item">
        <text class="data-label">陌生人状态</text>
        <text class="data-value" :class="strangerStatus.class">{{ strangerStatus.text }}</text>
      </view>
      <view class="data-item">
        <text class="data-label">人脸角度</text>
        <text class="data-value" :class="store.latest.stranger?.face_reliable === false ? 'warning' : 'normal'">
          {{ store.latest.stranger?.face_yaw?.toFixed(0) || '--' }}°
        </text>
      </view>
    </view>

    <view class="section">
      <view class="section-header">
        <text class="section-title">历史告警 ({{ store.alertCount }})</text>
        <text class="clear-btn" @click="store.clear()">清空</text>
      </view>
      <view v-if="store.history.length === 0" class="empty">暂无告警</view>
      <view v-for="a in store.history" :key="a._id" class="alert-row" :class="a.level" @click="goDetail(a)">
        <view class="row-left"><text class="row-level">{{ levelTag(a.level) }}</text></view>
        <view class="row-body">
          <text class="row-msg">{{ a.message }}</text>
          <text class="row-time">{{ fmt(a.timestamp) }}</text>
        </view>
        <text class="row-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad, onHide } from '@dcloudio/uni-app'
import { useAlertStore } from '@/stores/alert'

const store = useAlertStore()
const now = ref(Date.now())
let timer = null

const updateTime = computed(() => {
  now.value
  const d = new Date()
  return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0')
})

const levelEmoji = computed(() => ({ normal: '✅', warning: '⚠️', critical: '🚨' }[store.level] || '✅'))

const strangerStatus = computed(() => {
  const s = store.latest?.stranger
  if (!s || !store.latest?.face_detected) return { text: '--', class: 'normal' }
  if (s.stranger_alert) return { text: '⚠️ 陌生人', class: 'danger' }
  if (s.matched_user_id) return { text: '已识别', class: 'normal' }
  if (!s.face_reliable) return { text: '侧脸跳过', class: 'warning' }
  if (s.is_stranger) return { text: '未匹配...', class: 'warning' }
  return { text: '--', class: 'normal' }
})

const earClass = computed(() => {
  if (!store.latest?.face_detected) return 'muted'
  return store.latest.ear_avg < 0.25 ? 'danger' : 'normal'
})
const marClass = computed(() => {
  if (!store.latest?.face_detected) return 'muted'
  return store.latest.mar > 0.7 ? 'warning' : 'normal'
})

function levelTag(lv) { return { normal: '正常', warning: '⚠️', critical: '🚨' }[lv] || '正常' }
function fmt(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function goDetail(data) {
  uni.navigateTo({ url: `/pages/alert-detail/alert-detail?data=${encodeURIComponent(JSON.stringify(data))}` })
}

// onLoad: 首次加载立即启动轮询和计时器
onLoad(() => {
  store.startPolling()
  timer = setInterval(() => { now.value = Date.now() }, 1000)
})

// onHide: 页面隐藏时停计时器，保留轮询（让其他页面继续用）
onHide(() => {
  clearInterval(timer)
})
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; background: #0f0f23; }
.conn-bar { display: flex; align-items: center; gap: $spacing-xs; padding: 12rpx $spacing-md; border-radius: $radius-full; font-size: 22rpx; margin-bottom: $spacing-md; }
.conn-bar.connected { background: rgba($success, 0.1); color: $success; }
.conn-bar.disconnected { background: rgba($danger, 0.1); color: $danger; }
.dot { width: 12rpx; height: 12rpx; border-radius: 50%; }
.connected .dot { background: $success; }
.disconnected .dot { background: $danger; }
.last-update { margin-left: auto; font-size: 20rpx; opacity: 0.7; }
.level-banner { display: flex; align-items: center; gap: $spacing-md; padding: $spacing-lg; border-radius: $radius-lg; margin-bottom: $spacing-lg; }
.level-banner.critical { background: linear-gradient(135deg, rgba($danger,0.2), rgba($danger,0.05)); border: 2rpx solid rgba($danger,0.3); }
.level-banner.warning { background: linear-gradient(135deg, rgba($warning,0.2), rgba($warning,0.05)); border: 2rpx solid rgba($warning,0.3); }
.level-banner.normal { background: $bg-card; }
.level-icon { font-size: 56rpx; }
.level-text { font-size: 32rpx; font-weight: 600; display: block; }
.level-sub { font-size: 24rpx; color: $text-secondary; margin-top: 4rpx; display: block; }
.data-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: $spacing-sm; margin-bottom: $spacing-lg; }
.data-item { padding: $spacing-md; background: $bg-card; border-radius: $radius-md; text-align: center; }
.data-label { font-size: 22rpx; color: $text-muted; display: block; margin-bottom: $spacing-xs; }
.data-value { font-size: 40rpx; font-weight: 700; }
.data-value.danger { color: $danger; }
.data-value.warning { color: $warning; }
.data-value.normal { color: $accent; }
.data-value.muted { color: $text-muted; font-size: 26rpx; }
.face-warn { grid-column: span 2; background: rgba($orange, 0.1); border: 2rpx solid rgba($orange, 0.3); }
.warn-text { color: $orange !important; font-size: 28rpx !important; }
.section { margin-bottom: $spacing-lg; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: $spacing-sm; }
.section-title { font-size: 30rpx; font-weight: 600; }
.clear-btn { font-size: 24rpx; color: $text-muted; }
.empty { text-align: center; color: $text-muted; padding: $spacing-xl; font-size: 26rpx; }
.alert-row { display: flex; align-items: center; gap: $spacing-sm; padding: $spacing-md; background: $bg-card; border-radius: $radius-md; margin-bottom: $spacing-xs; }
.alert-row.critical { border-left: 4rpx solid $danger; }
.alert-row.warning { border-left: 4rpx solid $warning; }
.alert-row:active { background: $bg-card-hover; }
.row-level { font-size: 22rpx; padding: 4rpx 12rpx; border-radius: $radius-full; background: rgba(255,255,255,0.1); }
.row-body { flex: 1; }
.row-msg { font-size: 26rpx; display: block; }
.row-time { font-size: 22rpx; color: $text-muted; margin-top: 2rpx; }
.row-arrow { font-size: 36rpx; color: $text-muted; }
</style>
