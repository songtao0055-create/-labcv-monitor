// ========== 人脸管理 Pinia Store ==========
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { faceList, faceDelete } from '@/utils/api'

export const useFaceStore = defineStore('face', () => {
  const users = ref([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchList() {
    loading.value = true
    try {
      const res = await faceList()
      users.value = res.users || []
      total.value = res.total || 0
    } catch (e) {
      console.error('获取人脸列表失败:', e.message)
    } finally {
      loading.value = false
    }
  }

  async function remove(user_id) {
    await faceDelete(user_id)
    await fetchList()
  }

  return { users, total, loading, fetchList, remove }
})
