<template>
  <view class="page">
    <view class="status-bar">
      <view class="sys-status" :class="store.connected ? 'online' : 'offline'">
        <view class="dot"></view>
        {{ store.connected ? '服务器在线' : '未连接' }}
      </view>
      <text class="face-count">v2.1 已注册 {{ faceCount }} 人</text>
    </view>

    <view class="alert-indicator" :class="alertLevel" @click="goTab('/pages/alert/alert')">
      <text class="alert-icon">{{ alertIcon }}</text>
      <text class="alert-text">{{ alertText }}</text>
      <text class="arrow">›</text>
    </view>

    <view class="quick-grid">
      <view class="quick-item" @click="goTab('/pages/alert/alert')">
        <text class="quick-icon">🔔</text>
        <text class="quick-label">实时告警</text>
      </view>
      <view class="quick-item" @click="go('/pages/monitor/monitor')">
        <text class="quick-icon">📹</text>
        <text class="quick-label">实时监控</text>
      </view>
      <view class="quick-item" @click="goTab('/pages/user/user')">
        <text class="quick-icon">⚙️</text>
        <text class="quick-label">个人中心</text>
      </view>
    </view>

    <view class="section" v-if="store.latest">
      <text class="section-title">当前状态</text>
      <view class="status-grid">
        <view class="status-item" :class="store.latest.is_drowsy ? 'danger' : 'normal'">
          <text class="s-icon">{{ store.latest.is_drowsy ? '😴' : '✅' }}</text>
          <text class="s-label">瞌睡</text>
        </view>
        <view class="status-item" :class="store.latest.fire?.level !== 'normal' ? 'danger' : 'normal'">
          <text class="s-icon">{{ store.latest.fire?.level !== 'normal' ? '🔥' : '✅' }}</text>
          <text class="s-label">火灾</text>
        </view>
        <view class="status-item" :class="store.latest.stranger?.stranger_alert ? 'danger' : (store.latest.stranger?.matched_user_id ? 'normal' : 'warn')">
          <text class="s-icon">{{ store.latest.stranger?.stranger_alert ? '👤' : (store.latest.stranger?.matched_user_id ? '✅' : '👀') }}</text>
          <text class="s-label">陌生人</text>
        </view>
      </view>
    </view>

    <view class="section">
      <text class="section-title">最新告警 ({{ store.alertCount }})</text>
      <view v-if="store.history.length === 0" class="empty">暂无告警</view>
      <view v-for="a in store.history.slice(0, 10)" :key="a._id" class="alert-card" :class="cardClass(a)" @click="goDetail(a)">
        <view class="card-left"><text class="card-icon">{{ cardIcon(a) }}</text></view>
        <view class="card-body">
          <text class="card-title">{{ cardTitle(a) }}</text>
          <text class="card-time">{{ formatTime(a.timestamp) }}</text>
        </view>
        <text class="card-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad, onShow, onHide } from '@dcloudio/uni-app'
import { useAlertStore } from '@/stores/alert'
import { getStatus } from '@/utils/api'

const store = useAlertStore()
const faceCount = ref(0)

const alertLevel = computed(() => {
  if (!store.latest) return 'normal'
  if (store.latest.stranger?.stranger_alert) return 'warning'
  return store.latest.level || 'normal'
})
const alertIcon = computed(() => ({ normal: '✅', warning: '⚠️', critical: '🚨' }[alertLevel.value] || '✅'))
const alertText = computed(() => {
  if (!store.latest) return '一切正常'
  if (store.latest.stranger?.stranger_alert) return '陌生人警告！'
  return { normal: '一切正常', warning: '有告警待处理', critical: '紧急告警！' }[store.latest.level] || '一切正常'
})

function cardClass(a) {
  if (a.stranger?.stranger_alert) return 'warning stranger'
  return a.level || 'normal'
}
function cardIcon(a) {
  if (a.stranger?.stranger_alert) return '👤'
  return { normal: 'i', warning: '⚠️', critical: '🚨' }[a.level] || 'i'
}
function cardTitle(a) {
  if (a.stranger?.stranger_alert) return a.stranger.message || '陌生人警告'
  return a.message || '系统消息'
}
function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function go(url) { uni.navigateTo({ url }) }
function goTab(url) { uni.switchTab({ url }) }
function goDetail(a) {
  uni.navigateTo({ url: `/pages/alert-detail/alert-detail?data=${encodeURIComponent(JSON.stringify(a))}` })
}

// onLoad: 首次进入时立即启动，比 onMounted 更早，减少白屏
onLoad(() => {
  getStatus().then(s => { faceCount.value = s.face_registered || 0 }).catch(() => {})
  store.startPolling()
})

// onShow: 切回页面时刷新状态（不重启轮询，避免闪）
onShow(() => {
  getStatus().then(s => { faceCount.value = s.face_registered || 0 }).catch(() => {})
})

// onHide: 页面隐藏时暂停轮询，释放资源
onHide(() => {
  store.stopPolling()
})
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; background: #0f0f23; }
.status-bar { display: flex; justify-content: space-between; align-items: center; padding: $spacing-md; background: $bg-card; border-radius: $radius-md; margin-bottom: $spacing-md; }
.sys-status { display: flex; align-items: center; gap: $spacing-xs; font-size: 26rpx; }
.sys-status.online { color: $success; }
.sys-status.offline { color: $text-muted; }
.sys-status .dot { width: 12rpx; height: 12rpx; border-radius: 50%; }
.sys-status.online .dot { background: $success; }
.face-count { font-size: 26rpx; color: $text-secondary; }
.alert-indicator { display: flex; align-items: center; gap: $spacing-sm; padding: $spacing-md; background: $bg-card; border-radius: $radius-md; margin-bottom: $spacing-md; font-size: 28rpx; }
.alert-indicator.normal { border-left: 6rpx solid $success; }
.alert-indicator.warning { border-left: 6rpx solid $warning; }
.alert-indicator.critical { border-left: 6rpx solid $danger; animation: pulse 1s infinite alternate; }
.alert-text { flex: 1; }
.arrow { font-size: 40rpx; color: $text-muted; }
.quick-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: $spacing-sm; margin-bottom: $spacing-lg; }
.quick-item { display: flex; flex-direction: column; align-items: center; gap: $spacing-xs; padding: $spacing-lg $spacing-sm; background: $bg-card; border-radius: $radius-md; }
.quick-item:active { background: $bg-card-hover; }
.quick-icon { font-size: 48rpx; }
.quick-label { font-size: 24rpx; color: $text-secondary; }
.section { margin-bottom: $spacing-lg; }
.section-title { font-size: 30rpx; font-weight: 600; margin-bottom: $spacing-sm; display: block; }
.status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: $spacing-sm; }
.status-item { text-align: center; padding: $spacing-md; border-radius: $radius-md; }
.status-item.normal { background: rgba($success, 0.08); }
.status-item.warn { background: rgba($warning, 0.08); }
.status-item.danger { background: rgba($danger, 0.08); }
.s-icon { font-size: 40rpx; display: block; }
.s-label { font-size: 22rpx; color: $text-secondary; margin-top: 4rpx; display: block; }
.empty { text-align: center; color: $text-muted; padding: $spacing-xl; font-size: 26rpx; }
.alert-card { display: flex; align-items: center; gap: $spacing-sm; padding: $spacing-md; background: $bg-card; border-radius: $radius-md; margin-bottom: $spacing-xs; }
.alert-card.critical { border-left: 4rpx solid $danger; }
.alert-card.warning { border-left: 4rpx solid $warning; }
.alert-card.stranger { border-left: 4rpx solid $orange; background: rgba($orange, 0.05); }
.alert-card:active { background: $bg-card-hover; }
.card-left { font-size: 30rpx; }
.card-body { flex: 1; }
.card-title { font-size: 28rpx; display: block; }
.card-time { font-size: 22rpx; color: $text-muted; margin-top: 4rpx; }
.card-arrow { font-size: 36rpx; color: $text-muted; }
@keyframes pulse { from { opacity: 1; } to { opacity: 0.6; } }
</style>
