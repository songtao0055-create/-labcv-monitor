// ========== 告警状态 Pinia Store ==========
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const API_BASE = 'http://localhost:8000'

export const useAlertStore = defineStore('alert', () => {
  const latest = ref(null)
  const history = ref([])
  const connected = ref(false)

  const level = computed(() => latest.value?.level || 'normal')
  const isCritical = computed(() => level.value === 'critical')
  const isWarning = computed(() => level.value === 'warning')
  const alertCount = computed(() => history.value.length)

  let pollTimer = null
  const STORAGE_KEY = 'labcv_alert_history'

  // 启动时恢复本地存储的历史告警
  try {
    const saved = uni.getStorageSync(STORAGE_KEY)
    if (saved && Array.isArray(saved)) {
      history.value = saved
    }
  } catch (e) {}

  function push(data) {
    latest.value = data
    connected.value = true
    if (data.message === 'heartbeat' || (data.level === 'normal' && !data.stranger?.stranger_alert && !data.is_drowsy)) {
      return
    }
    const last = history.value[0]
    const now = Date.now()
    // 同一类型告警 15 秒内去重，避免后端检测抖动重复弹
    if (last && (now - last._id) < 15000) {
      if (last.level === data.level &&
          last.stranger?.stranger_alert === data.stranger?.stranger_alert &&
          last.is_drowsy === data.is_drowsy) {
        return
      }
    }
    history.value.unshift({ ...data, _id: now })
    if (history.value.length > 500) history.value.length = 500
    // 持久化到本地存储
    try { uni.setStorageSync(STORAGE_KEY, history.value) } catch (e) {}
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(async () => {
      try {
        const res = await new Promise((resolve, reject) => {
          uni.request({
            url: API_BASE + '/api/alerts/latest',
            timeout: 3000,
            success(r) { resolve(r.data) },
            fail(e) { reject(e) },
          })
        })
        if (res && res.timestamp) {
          push(res)
        }
      } catch (e) {
        connected.value = false
      }
    }, 2000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function clear() {
    latest.value = null
    history.value = []
    try { uni.removeStorageSync(STORAGE_KEY) } catch (e) {}
  }

  return { latest, history, connected, level, isCritical, isWarning, alertCount, push, clear, startPolling, stopPolling }
})
