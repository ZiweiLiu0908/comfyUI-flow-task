import http, { getIframeToken } from './http'
import { TOKEN_KEY } from '../utils/constants'

export async function fetchSystemSettings() {
  const { data } = await http.get('/settings/system')
  return data
}

export async function updateSystemSettings(payload) {
  const { data } = await http.put('/settings/system', payload)
  return data
}

export async function fetchPipelineSettings() {
  const { data } = await http.get('/settings/pipeline')
  return data
}

export async function updatePipelineSettings(payload) {
  const { data } = await http.put('/settings/pipeline', payload)
  return data
}

export async function fetchTemplateSupplementConfig() {
  const { data } = await http.get('/settings/template-supplement-config')
  return data
}

export async function updateTemplateSupplementConfig(payload) {
  const { data } = await http.put('/settings/template-supplement-config', payload)
  return data
}

export async function triggerCheckChannelStatus() {
  const { data } = await http.post('/settings/check-channel-status')
  return data
}

function parseSseEvent(rawEvent) {
  const lines = rawEvent.split('\n')
  let event = 'message'
  const dataLines = []

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      event = line.slice(6).trim() || 'message'
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (!dataLines.length) {
    return null
  }

  const rawData = dataLines.join('\n')
  let data = rawData
  try {
    data = JSON.parse(rawData)
  } catch {
    // Keep plain text payload when backend does not send JSON.
  }

  return { event, data }
}

async function streamSse(path, { onEvent, signal } = {}) {
  const token = getIframeToken() || localStorage.getItem(TOKEN_KEY) || ''
  const headers = { Accept: 'text/event-stream' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(`${http.defaults.baseURL}${path}`, {
    method: 'GET',
    headers,
    signal
  })

  if (!response.ok) {
    let detail = '检查失败，请稍后重试'
    try {
      const body = await response.json()
      detail = body?.detail || detail
    } catch {
      try {
        const text = await response.text()
        if (text) detail = text
      } catch {
        // Ignore body parsing errors and fall back to the default message.
      }
    }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n')

      let boundaryIndex = buffer.indexOf('\n\n')
      while (boundaryIndex !== -1) {
        const rawEvent = buffer.slice(0, boundaryIndex)
        buffer = buffer.slice(boundaryIndex + 2)
        const parsed = parseSseEvent(rawEvent)
        if (parsed) {
          onEvent?.(parsed)
        }
        boundaryIndex = buffer.indexOf('\n\n')
      }

      if (done) {
        break
      }
    }
  } catch (error) {
    try {
      await reader.cancel()
    } catch {
      // Ignore cleanup failures after stream errors.
    }
    throw error
  } finally {
    reader.releaseLock()
  }

  if (buffer.trim()) {
    const parsed = parseSseEvent(buffer)
    if (parsed) {
      onEvent?.(parsed)
    }
  }
}

export async function streamCheckChannelStatus(options = {}) {
  return await streamSse('/settings/check-channel-status/stream', options)
}

export async function streamSyncChannelNames(options = {}) {
  return await streamSse('/settings/sync-channel-names/stream', options)
}

export async function fetchCandidateConfig() {
  const { data } = await http.get('/settings/candidate-config')
  return data
}

export async function updateCandidateConfig(payload) {
  const { data } = await http.put('/settings/candidate-config', payload)
  return data
}
