<template>
  <view class="page">
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
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getStatus } from '@/utils/api'

const faceCount = ref(0)
const apiOk = ref(false)

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

function go(url) {
  uni.navigateTo({ url })
}

// onLoad 比 onMounted 更早触发，减少白屏
onLoad(() => {
  getStatus().then(s => { faceCount.value = s.face_registered || 0; apiOk.value = true }).catch(() => {})
})
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; background: #0f0f23; }

.user-header {
  display: flex; flex-direction: column; align-items: center; padding: $spacing-xl 0;
}
.avatar {
  width: 120rpx; height: 120rpx; border-radius: 50%;
  background: linear-gradient(135deg, $accent-blue, $accent);
  display: flex; align-items: center; justify-content: center;
  font-size: 48rpx; font-weight: 700; color: #fff; margin-bottom: $spacing-sm;
}
.username { font-size: 36rpx; font-weight: 600; }
.role { font-size: 24rpx; color: $text-muted; margin-top: 4rpx;
  padding: 2rpx 20rpx; background: rgba($accent, 0.1); border-radius: $radius-full; }

.menu { background: $bg-card; border-radius: $radius-lg; overflow: hidden; margin-bottom: $spacing-lg; }
.menu-item {
  display: flex; align-items: center; gap: $spacing-md; padding: $spacing-md $spacing-lg;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  &:last-child { border-bottom: none; }
  &:active { background: $bg-card-hover; }
}
.menu-icon { font-size: 36rpx; }
.menu-label { flex: 1; font-size: 28rpx; }
.menu-arrow { font-size: 36rpx; color: $text-muted; }

.section { margin-bottom: $spacing-lg; }
.section-title { font-size: 28rpx; font-weight: 600; margin-bottom: $spacing-sm; display: block; }

.info-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: $spacing-sm $spacing-md; background: $bg-card; margin-bottom: 2rpx;
}
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
