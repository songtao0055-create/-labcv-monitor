<template>
  <view class="layout">
    <!-- ========== Tab 0: 监控 ========== -->
    <view v-show="tab === 0" class="tab-content">
      <view class="status-bar">
        <view class="sys-status" :class="store.connected ? 'online' : 'offline'">
          <view class="dot"></view>
          {{ store.connected ? '服务器在线' : '未连接' }}
        </view>
        <text class="face-count">v2.1 已注册 {{ faceCount }} 人</text>
      </view>

      <view class="alert-indicator" :class="alertLevel" @click="tab = 1">
        <text class="alert-icon">{{ alertIcon }}</text>
        <text class="alert-text">{{ alertText }}</text>
        <text class="arrow">›</text>
      </view>

      <view class="quick-grid">
        <view class="quick-item" @click="tab = 1">
          <text class="quick-icon">🔔</text>
          <text class="quick-label">实时告警</text>
        </view>
        <view class="quick-item" @click="go('/pages/monitor/monitor')">
          <text class="quick-icon">📹</text>
          <text class="quick-label">实时监控</text>
        </view>
        <view class="quick-item" @click="tab = 2">
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
          <view class="status-item" :class="!store.latest?.face_detected ? 'normal' : (store.latest.stranger?.stranger_alert ? 'danger' : (store.latest.stranger?.matched_user_id ? 'normal' : 'warn'))">
            <text class="s-icon">{{ !store.latest?.face_detected ? '--' : (store.latest.stranger?.stranger_alert ? '👤' : (store.latest.stranger?.matched_user_id ? '✅' : '👀')) }}</text>
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

    <!-- ========== Tab 1: 告警 ========== -->
    <view v-show="tab === 1" class="tab-content">
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

    <!-- ========== Tab 2: 我的 ========== -->
    <view v-show="tab === 2" class="tab-content">
      <view class="user-header">
        <view class="avatar">L</view>
        <text class="username">云韬氢能韶关监控员</text>
        <text class="role">内部工具</text>
      </view>

      <view class="menu">
        <view class="menu-item" @click="go('/pages/monitor/monitor')">
          <text class="menu-icon">📹</text>
          <text class="menu-label">实时监控</text>
          <text class="menu-arrow">›</text>
        </view>
        <view class="menu-item" @click="refreshStatus">
          <text class="menu-icon">🔄</text>
          <text class="menu-label">刷新系统状态</text>
          <text class="menu-arrow">›</text>
        </view>
      </view>

      <view class="section">
        <text class="section-title">飞书人脸注册</text>
        <view class="about">
          <text class="about-text">在飞书中搜索机器人，发送照片即可完成人脸注册。</text>
          <text class="about-text mt">支持指令：</text>
          <text class="about-text">• 直接发送照片 → 注册人脸</text>
          <text class="about-text">• 发送「开门」→ 发送照片验证开门</text>
          <text class="about-text">• 发送「离职」→ 发送照片确认后删除</text>
        </view>
      </view>

      <view class="section">
        <text class="section-title">关于</text>
        <view class="about">
          <text class="about-name">云韬氢能韶关实验室智能监控中心</text>
          <text class="about-ver">版本 1.0.0</text>
        </view>
      </view>
    </view>

    <!-- 自定义 TabBar -->
    <view class="custom-tab-bar">
      <view v-for="(t, i) in tabs" :key="i" class="tab-item" :class="{ active: tab === i }" @click="tab = i">
        <text class="tab-icon">{{ t.icon }}</text>
        <text class="tab-text">{{ t.text }}</text>
        <view v-if="i === 1 && store.alertCount > 0" class="tab-badge">{{ store.alertCount > 99 ? '99+' : store.alertCount }}</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useAlertStore } from '@/stores/alert'
import { getStatus } from '@/utils/api'

const store = useAlertStore()
const tab = ref(0)
const faceCount = ref(0)
const apiOk = ref(false)
const now = ref(Date.now())
let timer = null

const tabs = [
  { text: '监控', icon: '📊' },
  { text: '告警', icon: '🔔' },
  { text: '我的', icon: '⚙️' },
]

// ===== 监控 Tab =====
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
function cardClass(a) { return a.stranger?.stranger_alert ? 'warning stranger' : a.level || 'normal' }
function cardIcon(a) { return a.stranger?.stranger_alert ? '👤' : { normal: 'i', warning: '⚠️', critical: '🚨' }[a.level] || 'i' }
function cardTitle(a) { return a.stranger?.stranger_alert ? a.stranger.message || '陌生人警告' : a.message || '系统消息' }
function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// ===== 告警 Tab =====
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

// ===== 通用 =====
function go(url) { uni.navigateTo({ url }) }
function goDetail(a) {
  uni.navigateTo({ url: `/pages/alert-detail/alert-detail?data=${encodeURIComponent(JSON.stringify(a))}` })
}
async function refreshStatus() {
  try {
    const s = await getStatus()
    faceCount.value = s.face_registered || 0
    apiOk.value = true
    uni.showToast({ title: '已刷新', icon: 'success' })
  } catch {
    apiOk.value = false
    uni.showToast({ title: '无法连接服务器', icon: 'error' })
  }
}

// onLoad 延迟重活，让 UI 先渲染
onLoad(() => {
  setTimeout(() => {
    getStatus().then(s => { faceCount.value = s.face_registered || 0; apiOk.value = true }).catch(() => {})
  }, 100)
  store.startPolling()
  timer = setInterval(() => { now.value = Date.now() }, 1000)
})
</script>

<style lang="scss" scoped>
.layout { display: flex; flex-direction: column; height: 100vh; background: #0f0f23; overflow: hidden; }

.tab-content {
  flex: 1; padding: $spacing-md; overflow-y: auto; min-height: 0;
}

/* custom tab bar */
.custom-tab-bar {
  display: flex; justify-content: space-around; align-items: center;
  height: 100rpx; background: #1a1a2e; border-top: 1px solid rgba(255,255,255,0.06);
  padding-bottom: env(safe-area-inset-bottom);
}
.tab-item {
  display: flex; flex-direction: column; align-items: center; gap: 2rpx;
  position: relative; padding: 8rpx 24rpx;
}
.tab-icon { font-size: 36rpx; }
.tab-text { font-size: 20rpx; color: #8892b0; }
.tab-item.active .tab-text { color: $accent; }
.tab-badge {
  position: absolute; top: 0; right: 4rpx;
  min-width: 28rpx; height: 28rpx; line-height: 28rpx; text-align: center;
  background: $danger; color: #fff; font-size: 18rpx; border-radius: 14rpx; padding: 0 6rpx;
}

/* ========== 监控 Tab 样式 ========== */
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

/* ========== 告警 Tab 样式 ========== */
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
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: $spacing-sm; }
.clear-btn { font-size: 24rpx; color: $text-muted; }
.alert-row { display: flex; align-items: center; gap: $spacing-sm; padding: $spacing-md; background: $bg-card; border-radius: $radius-md; margin-bottom: $spacing-xs; }
.alert-row.critical { border-left: 4rpx solid $danger; }
.alert-row.warning { border-left: 4rpx solid $warning; }
.alert-row:active { background: $bg-card-hover; }
.row-level { font-size: 22rpx; padding: 4rpx 12rpx; border-radius: $radius-full; background: rgba(255,255,255,0.1); }
.row-body { flex: 1; }
.row-msg { font-size: 26rpx; display: block; }
.row-time { font-size: 22rpx; color: $text-muted; margin-top: 2rpx; }
.row-arrow { font-size: 36rpx; color: $text-muted; }

/* ========== 我的 Tab 样式 ========== */
.user-header { display: flex; flex-direction: column; align-items: center; padding: $spacing-xl 0; }
.avatar { width: 120rpx; height: 120rpx; border-radius: 50%; background: linear-gradient(135deg, $accent-blue, $accent); display: flex; align-items: center; justify-content: center; font-size: 48rpx; font-weight: 700; color: #fff; margin-bottom: $spacing-sm; }
.username { font-size: 36rpx; font-weight: 600; }
.role { font-size: 24rpx; color: $text-muted; margin-top: 4rpx; padding: 2rpx 20rpx; background: rgba($accent, 0.1); border-radius: $radius-full; }
.menu { background: $bg-card; border-radius: $radius-lg; overflow: hidden; margin-bottom: $spacing-lg; }
.menu-item { display: flex; align-items: center; gap: $spacing-md; padding: $spacing-md $spacing-lg; border-bottom: 1px solid rgba(255,255,255,0.04); }
.menu-item:last-child { border-bottom: none; }
.menu-item:active { background: $bg-card-hover; }
.menu-icon { font-size: 36rpx; }
.menu-label { flex: 1; font-size: 28rpx; }
.menu-arrow { font-size: 36rpx; color: $text-muted; }
.info-item { display: flex; justify-content: space-between; align-items: center; padding: $spacing-sm $spacing-md; background: $bg-card; margin-bottom: 2rpx; }
.info-item:first-child { border-radius: $radius-md $radius-md 0 0; }
.info-item:last-child { border-radius: 0 0 $radius-md $radius-md; }
.info-label { font-size: 26rpx; color: $text-secondary; }
.info-value { font-size: 26rpx; }
.info-value.ok { color: $success; }
.info-value.fail { color: $text-muted; }
.info-value.small { font-size: 22rpx; }
.about { padding: $spacing-md; background: $bg-card; border-radius: $radius-md; }
.about-text { font-size: 24rpx; color: $text-secondary; display: block; line-height: 1.8; }
.about-text.mt { margin-top: $spacing-sm; color: $text-primary; }
.about-name { font-size: 28rpx; font-weight: 500; display: block; }
.about-ver { font-size: 24rpx; color: $text-secondary; display: block; margin-top: 4rpx; }
</style>
