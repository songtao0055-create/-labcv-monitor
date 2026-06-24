<template>
  <view class="page">
    <view class="video-box">
      <video
        id="monitor-video"
        :src="streamUrl"
        autoplay
        muted
        :show-fullscreen-btn="true"
        :show-center-play-btn="false"
        object-fit="contain"
        class="video-player"
        @error="onError"
      />
    </view>

    <view class="toolbar">
      <text class="live-tag">● LIVE</text>
      <text class="ctrl-btn" @click="doRefresh">🔄 刷新</text>
      <text class="err-msg" v-if="errMsg">{{ errMsg }}</text>
    </view>

    <view class="camera-list">
      <text class="section-title">摄像头列表</text>
      <view v-for="cam in cameras" :key="cam.id" class="camera-item" :class="{ active: activeCam === cam.id }" @click="switchCamera(cam)">
        <text class="cam-icon">{{ activeCam === cam.id ? '🔴' : '⭕' }}</text>
        <view class="cam-body">
          <text class="cam-name">{{ cam.name }}</text>
          <text class="cam-location">{{ cam.location }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'

const SVR = 'http://localhost:8000'
const cameras = ref([
  { id: 1, name: '中控室', location: '测试台C区', url: SVR + '/hls/camera1/main_stream.m3u8' },
])

const activeCam = ref(1)
const streamUrl = ref(cameras.value[0].url + '?t=' + Date.now())
const errMsg = ref('')

function onError(e) {
  console.error('video error:', e)
  errMsg.value = '加载失败，点刷新重试'
}

function doRefresh() {
  errMsg.value = ''
  streamUrl.value = cameras.value.find(c => c.id === activeCam.value).url + '?t=' + Date.now()
}

function switchCamera(cam) {
  activeCam.value = cam.id
  errMsg.value = ''
  streamUrl.value = cam.url + '?t=' + Date.now()
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: #000; padding-bottom: 40rpx; }
.video-box {
  width: 100%; height: 560rpx; background: #111;
  display: flex; align-items: center; justify-content: center;
}
.video-player { width: 100%; height: 100%; }
.toolbar {
  display: flex; align-items: center; gap: 16rpx; padding: 16rpx 24rpx;
}
.live-tag { color: $danger; font-weight: 700; font-size: 24rpx; }
.ctrl-btn {
  color: $accent; font-size: 24rpx; padding: 8rpx 16rpx;
  background: rgba($accent, 0.1); border-radius: $radius-md;
}
.err-msg { color: #ff6b6b; font-size: 22rpx; }
.section-title { font-size: 30rpx; font-weight: 600; margin-bottom: $spacing-sm; display: block; padding: 0 $spacing-md; color: #fff; }
.camera-list { padding: $spacing-md; }
.camera-item {
  display: flex; align-items: center; gap: $spacing-md; padding: $spacing-md;
  background: $bg-card; border-radius: $radius-md; margin-bottom: $spacing-xs;
}
.camera-item.active { border: 2rpx solid rgba($accent, 0.4); }
.cam-icon { font-size: 36rpx; }
.cam-body { flex: 1; }
.cam-name { font-size: 28rpx; display: block; color: #fff; }
.cam-location { font-size: 22rpx; color: $text-muted; }
</style>
