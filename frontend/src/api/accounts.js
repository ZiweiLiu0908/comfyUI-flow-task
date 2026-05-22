import http from './http'

export async function createAccount(payload) {
  const { data } = await http.post('/accounts', payload)
  return data
}

export async function fetchAccounts(params = {}) {
  const { data } = await http.get('/accounts', { params })
  return data
}

export async function fetchAccount(id) {
  const { data } = await http.get(`/accounts/${id}`)
  return data
}

export async function patchAccount(id, payload) {
  const { data } = await http.patch(`/accounts/${id}`, payload)
  return data
}

export async function bulkUpdateAccountAttributes(payload) {
  const { data } = await http.post('/accounts/bulk-update-attributes', payload)
  return data
}

export async function deleteAccount(id) {
  await http.delete(`/accounts/${id}`)
}

// 账号-博主绑定
export async function fetchAccountBloggers(accountId) {
  const { data } = await http.get(`/accounts/${accountId}/bloggers`)
  return data
}

export async function bindBlogger(accountId, tiktokBloggerId) {
  const { data } = await http.post(`/accounts/${accountId}/bloggers`, { tiktok_blogger_id: tiktokBloggerId })
  return data
}

export async function unbindBlogger(accountId, bloggerId) {
  await http.delete(`/accounts/${accountId}/bloggers/${bloggerId}`)
}

export async function updateScheduledPublish(accountId, payload) {
  // payload: { publish_enabled, publish_cron, publish_window_minutes, publish_count }
  const { data } = await http.put(`/accounts/${accountId}/scheduled-publish`, payload)
  return data
}

// AI 生成
export async function triggerAIAccountGeneration(accountId, tagIds) {
  const { data } = await http.post(`/accounts/${accountId}/ai-generate`, { tag_ids: tagIds })
  return data
}

export async function fetchAIGenerationStatus(accountId) {
  const { data } = await http.get(`/accounts/${accountId}/ai-generate/status`)
  return data
}

export async function resumeAIAccountGeneration(accountId) {
  const res = await http.post(`/accounts/${accountId}/ai-generate/resume`)
  return res.data
}

export async function bulkResumeAIAccountGeneration(fromStage = 'current', accountIds = null) {
  const payload = { from_stage: fromStage }
  if (accountIds) payload.account_ids = accountIds
  const { data } = await http.post('/accounts/bulk-resume-ai-generation', payload)
  return data
}

export async function restartAIAccountGeneration(accountId) {
  const res = await http.post(`/accounts/${accountId}/ai-generate/restart`)
  return res.data
}

export async function bulkGenerateAIAccounts() {
  const { data } = await http.post('/accounts/bulk-generate-ai-bloggers')
  return data
}

export async function selectAIPhotoCandidate(accountId, candidateId) {
  const { data } = await http.post(`/accounts/${accountId}/ai-generate/select-photo`, { candidate_id: candidateId })
  return data
}

export async function bulkRestartAIAccountGeneration(accountIds) {
  const res = await http.post('/accounts/bulk-restart-ai-generation', { account_ids: accountIds })
  return res.data
}

// 账号-标签绑定
export async function fetchAccountTags(accountId) {
  const { data } = await http.get(`/accounts/${accountId}/tags`)
  return data
}

export async function bindTagToAccount(accountId, tagId) {
  const { data } = await http.post(`/accounts/${accountId}/tags`, { tag_id: tagId })
  return data
}

export async function unbindTagFromAccount(accountId, tagId) {
  await http.delete(`/accounts/${accountId}/tags/${tagId}`)
}

export async function exportVideoUrls(accountIds) {
  const body = accountIds && accountIds.length > 0 ? { account_ids: accountIds } : {}
  const response = await http.post('/accounts/export-video-urls', body, { responseType: 'blob' })
  return response.data
}

function _normalizeFilters(filters = {}) {
  filters = filters || {}
  // 把空值 / 0 视为不限，转 null
  const minV = filters.min_view_count
  const pub = filters.published_after
  const dur = filters.max_duration_seconds
  const cats = Array.isArray(filters.category_indices)
    ? filters.category_indices.filter(v => Number.isInteger(v) && v >= 0 && v <= 13)
    : []
  return {
    min_view_count: typeof minV === 'number' && minV > 0 ? minV : null,
    published_after: pub || null,
    max_duration_seconds: typeof dur === 'number' && dur > 0 ? dur : null,
    category_indices: cats.length ? cats : null,
  }
}

export async function autoSupplementTemplates(accountIds, targetVideoCount = 10, filters = {}) {
  const { data } = await http.post('/accounts/auto-supplement-templates', {
    account_ids: accountIds,
    target_video_count: targetVideoCount,
    filters: _normalizeFilters(filters),
  })
  return data
}

export async function supplementTemplates(accountIds, templateType = 'shared', targetVideoCount = 10, filters = {}) {
  const { data } = await http.post('/accounts/supplement-templates', {
    account_ids: accountIds,
    template_type: templateType,
    target_video_count: targetVideoCount,
    filters: _normalizeFilters(filters),
  })
  return data
}

export async function bulkGenerateVideoTasks(
  accountIds,
  mode = 'unused',
  limit = 0,
  subtaskCount = 3,
  fillMode = 'count',
) {
  const { data } = await http.post('/accounts/bulk-generate-video-tasks', {
    account_ids: accountIds,
    mode,
    limit,
    subtask_count: subtaskCount,
    fill_mode: fillMode,
  })
  return data
}

export async function bulkGenerateNameHandle(accountIds = null) {
  const payload = accountIds && accountIds.length > 0 ? { account_ids: accountIds } : {}
  const { data } = await http.post('/accounts/bulk-generate-name-handle', payload)
  return data
}

export async function bulkSearchHashtags(accountIds = null, mode = 'replace') {
  const payload = {
    mode,
    ...(accountIds && accountIds.length > 0 ? { account_ids: accountIds } : {}),
  }
  const { data } = await http.post('/accounts/bulk-search-hashtags', payload)
  return data
}

export async function bulkBindHashtags(accountIds = null, hashtags = [], mode = 'replace') {
  const payload = {
    hashtags,
    mode,
    ...(accountIds && accountIds.length > 0 ? { account_ids: accountIds } : {}),
  }
  const { data } = await http.post('/accounts/bulk-bind-hashtags', payload)
  return data
}

export async function reserveAIAccountsForChannel(payload) {
  const { data } = await http.post('/accounts/channel-reservations', payload)
  return data
}

export async function confirmChannelReservations(payload) {
  const { data } = await http.post('/accounts/channel-reservations/confirm', payload)
  return data
}

export async function bindOpenAPIChannel(accountId, payload) {
  const { data } = await http.post(`/accounts/${accountId}/channel-bindings`, payload)
  return data
}

export async function deleteChannelReservation(accountId, reservationId) {
  await http.delete(`/accounts/${accountId}/channel-reservations/${reservationId}`)
}

export async function fetchPlatformStats() {
  const { data } = await http.get('/accounts/platform-stats')
  return data
}

// 视频分类
export async function startAccountClassification(accountId, force = false) {
  const { data } = await http.post(`/accounts/${accountId}/classify-videos`, { force })
  return data
}

export async function fetchAccountClassification(accountId) {
  const { data } = await http.get(`/accounts/${accountId}/classification`)
  return data
}

export async function retryAccountClassificationFailed(accountId) {
  const { data } = await http.post(`/accounts/${accountId}/classify-videos/retry-failed`)
  return data
}

export async function batchClassifyVideos(ids, force = false) {
  const { data } = await http.post('/accounts/batch-classify-videos', { ids, force })
  return data
}

// 账号分级评估（test ↔ dev）
export async function previewTierEvaluation() {
  const { data } = await http.post('/accounts/tier-evaluation/preview')
  return data
}

export async function applyTierEvaluation(changes) {
  const { data } = await http.post('/accounts/tier-evaluation/apply', { changes })
  return data
}
