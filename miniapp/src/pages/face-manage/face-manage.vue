<template>
  <view class="page">
    <!-- 搜索栏 -->
    <view class="search-bar">
      <input class="search-input" v-model="keyword" placeholder="搜索用户ID或姓名..." placeholder-style="color:#5a6480" />
    </view>

    <!-- 统计 -->
    <view class="total-bar">
      共 {{ store.total }} 人已注册
      <text class="add-btn" @click="go('/pages/face-register/face-register')">+ 录入</text>
    </view>

    <!-- 用户列表 -->
    <view v-if="store.loading" class="loading">加载中...</view>
    <view v-else-if="filteredUsers.length === 0" class="empty">
      {{ keyword ? '无匹配结果' : '暂无人脸注册记录' }}
    </view>
    <view v-for="u in filteredUsers" :key="u.id" class="user-card">
      <view class="avatar-placeholder">{{ (u.user_name || u.user_id).charAt(0).toUpperCase() }}</view>
      <view class="user-body">
        <text class="user-name">{{ u.user_name || '未命名' }}</text>
        <text class="user-id">ID: {{ u.user_id }}</text>
        <text class="user-time">注册时间: {{ fmtTime(u.created_at) }}</text>
      </view>
      <view class="delete-btn" @click="handleDelete(u)">删除</view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useFaceStore } from '@/stores/face'

const store = useFaceStore()
const keyword = ref('')

const filteredUsers = computed(() => {
  if (!keyword.value) return store.users
  const kw = keyword.value.toLowerCase()
  return store.users.filter(u =>
    u.user_id.toLowerCase().includes(kw) ||
    (u.user_name && u.user_name.toLowerCase().includes(kw))
  )
})

function fmtTime(ts) {
  if (!ts) return '--'
  return new Date(ts * 1000).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function go(url) {
  uni.navigateTo({ url })
}

function handleDelete(u) {
  uni.showModal({
    title: '确认删除',
    content: `确定删除「${u.user_name || u.user_id}」的人脸数据吗？`,
    success: async (res) => {
      if (res.confirm) {
        try {
          await store.remove(u.user_id)
          uni.showToast({ title: '已删除', icon: 'success' })
        } catch {
          uni.showToast({ title: '删除失败', icon: 'error' })
        }
      }
    },
  })
}

onMounted(() => {
  store.fetchList()
})
</script>

<style lang="scss" scoped>
.page { padding: $spacing-md; min-height: 100vh; }

.search-bar { margin-bottom: $spacing-md; }
.search-input {
  width: 100%; height: 72rpx; background: $bg-card; border-radius: $radius-full;
  padding: 0 $spacing-lg; font-size: 28rpx; color: $text-primary; box-sizing: border-box;
}

.total-bar {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 26rpx; color: $text-secondary; margin-bottom: $spacing-md;
}
.add-btn {
  color: $accent; font-weight: 600; padding: 8rpx 24rpx;
  background: rgba($accent, 0.1); border-radius: $radius-full;
}

.user-card {
  display: flex; align-items: center; gap: $spacing-md; padding: $spacing-md;
  background: $bg-card; border-radius: $radius-md; margin-bottom: $spacing-xs;
}
.avatar-placeholder {
  width: 80rpx; height: 80rpx; border-radius: 50%;
  background: linear-gradient(135deg, $accent-blue, $accent);
  display: flex; align-items: center; justify-content: center;
  font-size: 36rpx; font-weight: 700; color: #fff; flex-shrink: 0;
}
.user-body { flex: 1; }
.user-name { font-size: 30rpx; font-weight: 500; display: block; }
.user-id { font-size: 24rpx; color: $text-secondary; display: block; margin-top: 2rpx; }
.user-time { font-size: 22rpx; color: $text-muted; display: block; margin-top: 2rpx; }

.delete-btn {
  padding: 10rpx 24rpx; border-radius: $radius-full; font-size: 24rpx;
  background: rgba($danger, 0.1); color: $danger;
  &:active { background: rgba($danger, 0.25); }
}

.loading, .empty { text-align: center; padding: $spacing-xl; color: $text-muted; font-size: 26rpx; }
</style>
