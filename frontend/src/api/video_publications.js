import http from './http'

/**
 * 获取 Open API 渠道列表（通过后端代理）
 * @param {string} platform - 平台类型: tiktok/youtube/instagram
 * @param {Object} options - 额外参数 { isActive, page, pageSize }
 */
export async function fetchChannels(platform, options = {}) {
  const params = {
    platform,
    page: options.page ?? 1,
    page_size: options.pageSize ?? 50,
  }
  if (options.isActive !== undefined) {
    params.is_active = options.isActive
  }
  if (options.accountId) {
    params.account_id = options.accountId
  }
  const { data } = await http.get('/open-api/channels', { params })
  return data
}

export async function fetchAllChannels(platform, options = {}) {
  const pageSize = options.pageSize ?? 100
  let page = 1
  let total = 0
  const items = []

  do {
    const response = await fetchChannels(platform, {
      ...options,
      page,
      pageSize,
    })
    const data = response?.data || {}
    const pageItems = data.items || []
    total = Number(data.total || 0)
    items.push(...pageItems)
    if (pageItems.length < pageSize) break
    page += 1
  } while (items.length < total || total === 0)

  return items
}

/**
 * 创建视频发布任务
 * @param {Object} payload - 发布任务参数
 */
export async function createPublication(payload) {
  const { data } = await http.post('/video-publications', payload)
  return data
}

/**
 * 获取发布任务详情
 * @param {string} publicationId - 发布任务 ID
 */
export async function fetchPublication(publicationId) {
  const { data } = await http.get(`/video-publications/${publicationId}`)
  return data
}

/**
 * 获取子任务的所有发布记录
 * @param {string} subTaskId - 子任务 ID
 */
export async function fetchSubTaskPublications(subTaskId) {
  const { data } = await http.get(`/video-sub-tasks/${subTaskId}/publications`)
  return data
}

export async function fetchPublicationStats(params = {}) {
  const { data } = await http.get('/video-publications/stats', { params })
  return data
}

export async function exportPublicationStats(params = {}) {
  const response = await http.get('/video-publications/stats/export', {
    params,
    responseType: 'blob',
  })
  return response
}

export async function syncPublicationMetrics(params = {}) {
  const { data } = await http.post('/video-publications/sync-metrics', null, { params })
  return data
}

export async function syncKolLinkClicks(params = {}) {
  const { data } = await http.post('/video-publications/sync-kol-clicks', null, { params })
  return data
}

export async function syncAccountSnapshots(accountId) {
  const params = accountId ? { account_id: accountId } : {}
  const { data } = await http.post('/video-publications/sync-account-snapshots', null, { params })
  return data
}

/**
 * 同步发布任务状态（从 Open API）
 * @param {string} publicationId - 发布任务 ID
 */
export async function syncPublicationStatus(publicationId) {
  const { data } = await http.post(`/video-publications/${publicationId}/sync`)
  return data
}

export async function retryPublication(publicationId) {
  const { data } = await http.post(`/video-publications/${publicationId}/retry`)
  return data
}

/**
 * 重发当前 publication 中某个失败渠道（platform + channel_id 指定）。
 * 用于「查看数据」弹窗内单平台重发。
 */
export async function retryPublicationChannel(publicationId, { platform, channel_id }) {
  const { data } = await http.post(
    `/video-publications/${publicationId}/retry-channel`,
    { platform, channel_id },
  )
  return data
}

/**
 * 查询上传任务各渠道视频指标
 * @param {Object} params - { task_id?, external_id? }
 */
export async function fetchUploadMetrics(params = {}) {
  const { data } = await http.get('/open-api/upload/metrics', { params })
  return data
}

/**
 * 检查 Open API 服务健康状态
 */
export async function healthCheck() {
  const { data } = await http.post('/open-api/health-check')
  return data
}

/**
 * 统一频道查询接口（内部 openapi / 外部 ext_pub 均走此接口）
 * @param {string} platform - 平台: tiktok/youtube/instagram
 * @param {string} channelSource - 来源: 'openapi' | 'ext_pub'
 * @param {Object} options - { page, pageSize, isActive, accountId }
 */
export async function fetchChannelsUnified(platform, channelSource, options = {}) {
  const params = {
    platform,
    channel_source: channelSource,
    page: options.page ?? 1,
    page_size: options.pageSize ?? 50,
  }
  if (options.isActive !== undefined) params.is_active = options.isActive
  if (options.accountId) params.account_id = options.accountId
  const { data } = await http.get('/channels', { params })
  return data
}

/**
 * 获取外部发布 API 的平台账号列表（通过后端代理，兼容旧版）
 */
export async function fetchExtPubPlatformAccounts(platform) {
  const { data } = await http.get('/ext-pub/platform-accounts', {
    params: platform ? { platform } : undefined,
  })
  return data
}
