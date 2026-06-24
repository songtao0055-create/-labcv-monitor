<template>
  <view class="page">
    <!-- 预览区 -->
    <view class="preview-box">
      <image v-if="photoPath" :src="photoPath" mode="aspectFill" class="preview-img" />
      <view v-else class="preview-placeholder">
        <text class="placeholder-icon">📷</text>
        <text class="placeholder-text">请拍摄或选择正面免冠照片</text>
      </view>
    </view>

    <!-- 操作按钮 -->
    <view class="btn-row">
      <button class="btn btn-camera" @click="takePhoto">
        <text class="btn-icon">📷</text> 拍照
      </button>
      <button class="btn btn-album" @click="chooseAlbum">
        <text class="btn-icon">🖼️</text> 相册
      </button>
    </view>

    <!-- 用户信息 -->
    <view class="form">
      <view class="form-item">
        <text class="label">用户 ID</text>
        <input class="input" v-model="userId" placeholder="员工工号或唯一标识" placeholder-style="color:#5a6480" />
      </view>
      <view class="form-item">
        <text class="label">姓名</text>
        <input class="input" v-model="userName" placeholder="用户姓名（选填）" placeholder-style="color:#5a6480" />
      </view>
    </view>

    <!-- 提交 -->
    <button class="submit-btn" :disabled="!photoPath || submitting" @click="doRegister">
      {{ submitting ? '注册中...' : '确认录入' }}
    </button>

    <!-- 结果提示 -->
    <view v-if="result" class="result" :class="result.success ? 'success' : 'fail'">
      <text class="result-icon">{{ result.success ? '✅' : '❌' }}</text>
      <text class="result-text">{{ result.message }}</text>
      <text v-if="result.total_faces" class="result-sub">当前人脸库共 {{ result.total_faces }} 人</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { faceRegister } from '@/utils/api'

const photoPath = ref('')
const userId = ref('')
const userName = ref('')
const submitting = ref(false)
const result = ref(null)

function takePhoto() {
  uni.chooseImage({
    count: 1,
    sourceType: ['camera'],
    success: (res) => { photoPath.value = res.tempFilePaths[0]; result.value = null },
    fail: (err) => { if (err.errMsg.includes('cancel')) return; uni.showToast({ title: '获取照片失败', icon: 'error' }) },
  })
}

function chooseAlbum() {
  uni.chooseImage({
    count: 1,
    sourceType: ['album'],
    success: (res) => { photoPath.value = res.tempFilePaths[0]; result.value = null },
    fail: (err) => { if (err.errMsg.includes('cancel')) return; uni.showToast({ title: '选取照片失败', icon: 'error' }) },
  })
}

async function doRegister() {
  if (!photoPath.value) return
  submitting.value = true
  result.value = null
  try {
    const res = await faceRegister(photoPath.value, userId.value, userName.value)
    result.value = res
    if (res.success) {
      photoPath.value = ''; userId.value = ''; userName.value = ''
    }
  } catch (e) {
    result.value = { success: false, message: e.message }
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; }

.preview-box {
  width: 100%; height: 520rpx; border-radius: $radius-lg; overflow: hidden;
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

.form { background: $bg-card; border-radius: $radius-lg; padding: $spacing-md $spacing-lg; margin-bottom: $spacing-lg; }
.form-item { padding: $spacing-sm 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.form-item:last-child { border-bottom: none; }
.label { font-size: 26rpx; color: $text-secondary; display: block; margin-bottom: 4rpx; }
.input { width: 100%; height: 72rpx; font-size: 28rpx; color: $text-primary; }

.submit-btn {
  width: 100%; height: 88rpx; border-radius: $radius-md; border: none;
  background: linear-gradient(135deg, $accent-blue, $accent);
  color: #1a1a2e; font-size: 32rpx; font-weight: 600; margin-bottom: $spacing-lg;
  &:disabled { opacity: 0.4; }
}

.result { text-align: center; padding: $spacing-lg; border-radius: $radius-md; }
.result.success { background: rgba($success, 0.08); }
.result.fail { background: rgba($danger, 0.08); }
.result-icon { font-size: 48rpx; display: block; }
.result-text { font-size: 28rpx; font-weight: 500; display: block; margin-top: $spacing-xs; }
.result-sub { font-size: 24rpx; color: $text-secondary; display: block; margin-top: 4rpx; }
</style>
