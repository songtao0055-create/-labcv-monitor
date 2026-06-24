<template>
  <view class="page">
    <!-- 预览区 -->
    <view class="preview-box">
      <image v-if="photoPath" :src="photoPath" mode="aspectFill" class="preview-img" />
      <view v-else class="preview-placeholder">
        <text class="placeholder-icon">🔍</text>
        <text class="placeholder-text">请拍摄正面照片进行身份验证</text>
      </view>
    </view>

    <!-- 操作按钮 -->
    <view class="btn-row">
      <button class="btn btn-camera" @click="takePhoto">
        <text class="btn-icon">📷</text> 拍照验证
      </button>
      <button class="btn btn-album" @click="chooseAlbum">
        <text class="btn-icon">🖼️</text> 相册选择
      </button>
    </view>

    <!-- 提交 -->
    <button class="verify-btn" :disabled="!photoPath || verifying" @click="doVerify">
      {{ verifying ? '验证中...' : '开始验证' }}
    </button>

    <!-- 验证结果 -->
    <view v-if="verifyResult" class="result-card" :class="verifyResult.matched ? 'matched' : 'unmatched'">
      <text class="result-icon">{{ verifyResult.matched ? '✅' : '❌' }}</text>
      <text class="result-title">{{ verifyResult.matched ? '验证通过' : '验证失败' }}</text>
      <text class="result-msg">{{ verifyResult.message }}</text>
      <template v-if="verifyResult.matched">
        <view class="match-info">
          <text class="match-name">{{ verifyResult.user_name || verifyResult.user_id }}</text>
          <text class="match-sim">相似度: {{ (verifyResult.similarity * 100).toFixed(1) }}%</text>
        </view>
        <button class="door-btn" :disabled="opening" @click="openDoor">
          {{ opening ? '开门中...' : '🚪 开门' }}
        </button>
      </template>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { faceVerify, doorOpen } from '@/utils/api'

const photoPath = ref('')
const verifying = ref(false)
const opening = ref(false)
const verifyResult = ref(null)

function takePhoto() {
  uni.chooseImage({
    count: 1,
    sourceType: ['camera'],
    success: (res) => { photoPath.value = res.tempFilePaths[0]; verifyResult.value = null },
    fail: (err) => { if (err.errMsg.includes('cancel')) return; uni.showToast({ title: '获取照片失败', icon: 'error' }) },
  })
}

function chooseAlbum() {
  uni.chooseImage({
    count: 1,
    sourceType: ['album'],
    success: (res) => { photoPath.value = res.tempFilePaths[0]; verifyResult.value = null },
    fail: (err) => { if (err.errMsg.includes('cancel')) return; uni.showToast({ title: '选取照片失败', icon: 'error' }) },
  })
}

async function doVerify() {
  if (!photoPath.value) return
  verifying.value = true
  verifyResult.value = null
  try {
    verifyResult.value = await faceVerify(photoPath.value)
  } catch (e) {
    verifyResult.value = { matched: false, message: e.message }
  } finally {
    verifying.value = false
  }
}

async function openDoor() {
  opening.value = true
  try {
    await doorOpen(verifyResult.value?.user_id || '')
    uni.showToast({ title: '开门指令已发送', icon: 'success' })
  } catch {
    uni.showToast({ title: '开门失败', icon: 'error' })
  } finally {
    opening.value = false
  }
}
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; }

.preview-box {
  width: 100%; height: 480rpx; border-radius: $radius-lg; overflow: hidden;
  background: $bg-card; margin-bottom: $spacing-lg;
}
.preview-img { width: 100%; height: 100%; }
.preview-placeholder {
  width: 100%; height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: $spacing-sm;
}
.placeholder-icon { font-size: 80rpx; }
.placeholder-text { font-size: 26rpx; color: $text-muted; }

.btn-row { display: flex; gap: $spacing-md; margin-bottom: $spacing-lg; }
.btn { flex: 1; display: flex; align-items: center; justify-content: center; gap: $spacing-xs; height: 80rpx; border-radius: $radius-md; font-size: 28rpx; background: $bg-card; color: $text-primary; border: none; }
.btn-icon { font-size: 32rpx; }
.btn:active { background: $bg-card-hover; }

.verify-btn {
  width: 100%; height: 88rpx; border-radius: $radius-md; border: none;
  background: linear-gradient(135deg, $accent, #3ab0a0);
  color: #1a1a2e; font-size: 32rpx; font-weight: 600; margin-bottom: $spacing-lg;
  &:disabled { opacity: 0.4; }
}

.result-card {
  text-align: center; padding: $spacing-lg; border-radius: $radius-lg;
  &.matched { background: rgba($success, 0.08); border: 2rpx solid rgba($success, 0.2); }
  &.unmatched { background: rgba($danger, 0.08); border: 2rpx solid rgba($danger, 0.2); }
}
.result-icon { font-size: 64rpx; display: block; }
.result-title { font-size: 32rpx; font-weight: 600; display: block; margin-top: $spacing-xs; }
.result-msg { font-size: 26rpx; color: $text-secondary; display: block; margin-top: 4rpx; }

.match-info { margin-top: $spacing-md; padding: $spacing-md; background: rgba($accent, 0.08); border-radius: $radius-md; }
.match-name { font-size: 36rpx; font-weight: 700; color: $accent; display: block; }
.match-sim { font-size: 26rpx; color: $text-secondary; margin-top: 4rpx; display: block; }

.door-btn {
  margin-top: $spacing-md; width: 100%; height: 88rpx; border-radius: $radius-md; border: none;
  background: linear-gradient(135deg, $accent-blue, #7c5ce7);
  color: #fff; font-size: 32rpx; font-weight: 600;
  &:disabled { opacity: 0.4; }
}
</style>
