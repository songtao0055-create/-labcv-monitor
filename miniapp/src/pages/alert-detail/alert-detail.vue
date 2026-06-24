<template>
  <view class="page">
    <!-- 懒加载提示 -->
    <view v-if="!loaded" class="loading-card">
      <text class="loading-text">加载告警数据...</text>
    </view>

    <!-- 告警详情 -->
    <view v-if="loaded" class="detail">
      <!-- 级别标签 -->
      <view class="level-badge" :class="data.level">
        {{ levelText(data.level) }}
      </view>

      <!-- 瞌睡数据（仅在触发瞌睡告警时显示） -->
      <view class="card" v-if="showDrowsiness">
        <text class="card-title">😴 瞌睡检测数据</text>
        <view class="kv">
          <text class="k">眼部纵横比 EAR</text>
          <text class="v" :class="data.ear_avg < 0.25 ? 'danger' : ''">{{ data.ear_avg?.toFixed(3) }}</text>
        </view>
        <view class="kv">
          <text class="k">嘴部纵横比 MAR</text>
          <text class="v" :class="data.mar > 0.7 ? 'danger' : ''">{{ data.mar?.toFixed(3) }}</text>
        </view>
        <view class="kv">
          <text class="k">闭眼累计 (秒)</text>
          <text class="v">{{ data.eyes_closed_sec }}</text>
        </view>
        <view class="kv">
          <text class="k">低头累计 (秒)</text>
          <text class="v">{{ data.head_droop_sec }}</text>
        </view>
        <view class="kv">
          <text class="k">是否检测到人脸</text>
          <text class="v">{{ data.face_detected ? '是' : '否' }}</text>
        </view>
        <view class="kv">
          <text class="k">是否瞌睡</text>
          <text class="v" :class="data.is_drowsy ? 'danger' : ''">{{ data.is_drowsy ? '⚠️ 是' : '否' }}</text>
        </view>
      </view>

      <!-- 火灾数据（仅在触发火灾告警时显示） -->
      <view class="card" v-if="showFire">
        <text class="card-title">火灾检测数据</text>
        <view class="kv">
          <text class="k">火焰检测</text>
          <text class="v" :class="data.fire.has_fire ? 'danger' : ''">{{ data.fire.has_fire ? '⚠️ 检测到' : '未检测到' }}</text>
        </view>
        <view class="kv">
          <text class="k">烟雾检测</text>
          <text class="v" :class="data.fire.has_smoke ? 'danger' : ''">{{ data.fire.has_smoke ? '💨 检测到' : '未检测到' }}</text>
        </view>
        <view class="kv">
          <text class="k">火焰目标数</text>
          <text class="v">{{ data.fire.fire_count }}</text>
        </view>
        <view class="kv">
          <text class="k">烟雾目标数</text>
          <text class="v">{{ data.fire.smoke_count }}</text>
        </view>
        <view class="kv">
          <text class="k">火灾级别</text>
          <text class="v">{{ data.fire.level }}</text>
        </view>
      </view>

      <!-- 陌生人数据（仅在触发陌生人告警时显示） -->
      <view class="card" v-if="showStranger">
        <text class="card-title">👤 陌生人检测数据</text>
        <view class="kv">
          <text class="k">陌生人告警</text>
          <text class="v" :class="data.stranger.stranger_alert ? 'danger' : ''">
            {{ data.stranger.stranger_alert ? '⚠️ 触发告警' : '正常' }}
          </text>
        </view>
        <view class="kv">
          <text class="k">当前帧未匹配</text>
          <text class="v" :class="data.stranger.is_stranger ? 'danger' : ''">
            {{ data.stranger.is_stranger ? '是' : '否' }}
          </text>
        </view>
        <view class="kv">
          <text class="k">人脸可靠</text>
          <text class="v" :class="!data.stranger.face_reliable ? 'warning' : ''">
            {{ data.stranger.face_reliable ? '是（|yaw|<30°）' : '否（侧脸跳过）' }}
          </text>
        </view>
        <view class="kv">
          <text class="k">偏航角 Yaw</text>
          <text class="v">{{ data.stranger.face_yaw?.toFixed(1) || '--' }}°</text>
        </view>
        <view class="kv">
          <text class="k">俯仰角 Pitch</text>
          <text class="v">{{ data.stranger.face_pitch?.toFixed(1) || '--' }}°</text>
        </view>
        <view class="kv">
          <text class="k">人脸尺寸</text>
          <text class="v">{{ data.stranger.face_size || '--' }}px</text>
        </view>
        <view class="kv">
          <text class="k">匹配用户</text>
          <text class="v">{{ data.stranger.matched_user_name || data.stranger.matched_user_id || '未匹配' }}</text>
        </view>
        <view class="kv">
          <text class="k">相似度</text>
          <text class="v">{{ data.stranger.similarity ? (data.stranger.similarity * 100).toFixed(1) + '%' : '--' }}</text>
        </view>
        <view class="kv">
          <text class="k">连续未匹配帧</text>
          <text class="v">{{ data.stranger.unmatched_count || 0 }}</text>
        </view>
        <view class="kv">
          <text class="k">连续匹配帧</text>
          <text class="v">{{ data.stranger.matched_count || 0 }}</text>
        </view>
      </view>

      <!-- 告警截图 -->
      <view class="card" v-if="data.image">
        <text class="card-title">📸 告警截图</text>
        <image :src="API_BASE + '/alerts_img/' + data.image" mode="widthFix" class="alert-img" />
      </view>

      <!-- 时间戳 -->
      <view class="time-card">
        <text class="time-label">告警时间</text>
        <text class="time-value">{{ formatFull(data.timestamp) }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API_BASE = 'http://localhost:8000'
const loaded = ref(false)
const data = ref({})
const imgUrl = ref('')

const showDrowsiness = computed(() => data.value.is_drowsy)
const showFire = computed(() => {
  const f = data.value.fire
  return f && (f.has_fire || f.has_smoke || f.level !== 'normal')
})
const showStranger = computed(() => {
  const s = data.value.stranger
  return s && s.stranger_alert
})

function levelText(lv) {
  const map = { normal: '正常', warning: '⚠️ 警告', critical: '🚨 紧急' }
  return map[lv] || '未知'
}

function formatFull(ts) {
  if (!ts) return '--'
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN')
}

onMounted(() => {
  const pages = getCurrentPages()
  const opts = pages[pages.length - 1]?.options || {}
  if (opts.data) {
    try {
      data.value = JSON.parse(decodeURIComponent(opts.data))
      if (data.value.image) {
        imgUrl.value = API_BASE + '/alerts_img/' + data.value.image
      }
    } catch {
      data.value = {}
    }
    loaded.value = true
  }
})
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; }

.loading-card { text-align: center; padding: $spacing-xl; color: $text-muted; }

.level-badge {
  display: inline-block; padding: 8rpx 24rpx; border-radius: $radius-full;
  font-size: 26rpx; font-weight: 600; margin-bottom: $spacing-lg;
  &.critical { background: rgba($danger, 0.15); color: $danger; }
  &.warning { background: rgba($warning, 0.15); color: $warning; }
  &.normal { background: rgba($success, 0.15); color: $success; }
}

.card {
  background: $bg-card; border-radius: $radius-lg; padding: $spacing-lg; margin-bottom: $spacing-md;
}
.card-title { font-size: 28rpx; font-weight: 600; margin-bottom: $spacing-md; display: block; }

.kv {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10rpx 0; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.k { font-size: 26rpx; color: $text-secondary; }
.v { font-size: 26rpx; font-weight: 500; }
.v.danger { color: $danger; }

.time-card { text-align: center; padding: $spacing-lg; }
.time-label { font-size: 24rpx; color: $text-muted; display: block; }
.time-value { font-size: 28rpx; margin-top: $spacing-xs; display: block; }

.alert-img { width: 100%; border-radius: $radius-md; margin-top: $spacing-sm; }
</style>
