// ========== 飞书机器人已录入的人脸数量查询（可选）==========

const API_BASE = 'http://localhost:8000'

export function getStatus() {
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + '/api/status',
      timeout: 5000,
      success(res) {
        if (res.statusCode === 200) resolve(res.data)
        else reject(new Error('请求失败'))
      },
      fail(err) { reject(err) },
    })
  })
}

export function getFaceList() {
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + '/api/face/list',
      timeout: 5000,
      success(res) {
        if (res.statusCode === 200) resolve(res.data)
        else reject(new Error('请求失败'))
      },
      fail(err) { reject(err) },
    })
  })
}
