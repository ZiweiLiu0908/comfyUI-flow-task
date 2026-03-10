<template>
  <div class="vsf-page">
    <div class="vsf-back" @click="$router.push('/dashboard/video-library')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="15 18 9 12 15 6"/></svg>
      返回视频库
    </div>

    <div class="vsf-card">
      <!-- Header -->
      <div class="vsf-header">
        <div class="vsf-icon-wrap">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.75" stroke-linecap="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M10 9l5 3-5 3V9z" fill="white" stroke="none"/></svg>
        </div>
        <div>
          <div class="vsf-title">添加视频</div>
          <div class="vsf-subtitle">粘贴 TikTok、YouTube 或 Instagram 链接，解析后确认保存入库</div>
        </div>
      </div>

      <!-- Step 1: URL input -->
      <div class="vsf-url-row">
        <el-input
          v-model="url"
          placeholder="https://www.tiktok.com/@user/video/... 或 YouTube / Instagram 链接"
          size="large"
          clearable
          :disabled="parsing"
          @keydown.enter="handleParse"
          class="vsf-url-input"
        >
          <template #prefix>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          </template>
        </el-input>
        <el-button
          type="primary"
          size="large"
          :loading="parsing"
          :disabled="!url.trim() || !!parsed"
          class="vsf-parse-btn"
          @click="handleParse"
        >
          {{ parsing ? '解析中...' : '解析' }}
        </el-button>
      </div>

      <!-- Parse error -->
      <el-alert
        v-if="parseError"
        :title="parseError"
        type="error"
        :closable="true"
        show-icon
        class="vsf-error"
        @close="parseError = ''"
      />

      <!-- Step 2: Preview -->
      <transition name="slide-up">
        <div v-if="parsed" class="vsf-preview">
          <el-divider>
            <span class="divider-text">解析结果 — 请确认后保存</span>
          </el-divider>

          <div class="vsf-preview-body">
            <!-- Left: video player -->
            <div class="vsf-player-col">
              <div class="vsf-player-wrap">
                <video
                  v-if="parsed.video_url"
                  :src="parsed.video_url"
                  :poster="parsed.thumbnail_url || undefined"
                  controls
                  class="vsf-video"
                />
                <div v-else-if="parsed.thumbnail_url" class="vsf-thumb-only">
                  <img :src="parsed.thumbnail_url" class="vsf-thumb-img" alt="thumbnail" />
                  <div class="vsf-noplay-hint">仅预览图，无直链</div>
                </div>
                <div v-else class="vsf-no-media">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M10 9l5 3-5 3V9z"/></svg>
                  <div style="color:#94a3b8;font-size:13px;margin-top:8px">无预览</div>
                </div>
              </div>
              <el-link
                v-if="parsed.source_url"
                :href="parsed.source_url"
                target="_blank"
                type="primary"
                class="vsf-orig-link"
                :underline="false"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="margin-right:4px"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                前往原始链接
              </el-link>
            </div>

            <!-- Right: metadata -->
            <div class="vsf-meta-col">
              <div class="vsf-meta-platform">
                <el-tag :type="parsed.platform === 'youtube' ? 'danger' : 'primary'" size="large">
                  {{ platformLabel(parsed.platform) }}
                </el-tag>
              </div>

              <div class="vsf-meta-title">{{ parsed.video_title || '(无标题)' }}</div>

              <div v-if="parsed.video_desc" class="vsf-meta-desc">
                {{ parsed.video_desc }}
              </div>

              <div class="vsf-meta-grid">
                <div class="vsf-meta-row">
                  <span class="vsf-meta-label">博主</span>
                  <span class="vsf-meta-val">{{ parsed.blogger_name || '-' }}</span>
                </div>
                <div class="vsf-meta-row" v-if="parsed.duration != null">
                  <span class="vsf-meta-label">时长</span>
                  <span class="vsf-meta-val">{{ formatDuration(parsed.duration) }}</span>
                </div>
                <div class="vsf-meta-row" v-if="parsed.width && parsed.height">
                  <span class="vsf-meta-label">分辨率</span>
                  <span class="vsf-meta-val">{{ parsed.width }}x{{ parsed.height }}</span>
                </div>
                <div class="vsf-meta-row" v-if="parsed.aspect_ratio != null">
                  <span class="vsf-meta-label">比例</span>
                  <span class="vsf-meta-val">{{ parsed.aspect_ratio.toFixed(2) }}</span>
                </div>
                <div class="vsf-meta-row" v-if="parsed.view_count != null">
                  <span class="vsf-meta-label">播放量</span>
                  <span class="vsf-meta-val">{{ formatCount(parsed.view_count) }}</span>
                </div>
                <div class="vsf-meta-row" v-if="parsed.like_count != null">
                  <span class="vsf-meta-label">点赞数</span>
                  <span class="vsf-meta-val">{{ formatCount(parsed.like_count) }}</span>
                </div>
                <div class="vsf-meta-row" v-if="parsed.publish_date">
                  <span class="vsf-meta-label">发布日期</span>
                  <span class="vsf-meta-val">{{ formatDate(parsed.publish_date) }}</span>
                </div>
                <div class="vsf-meta-row">
                  <span class="vsf-meta-label">原始链接</span>
                  <span class="vsf-meta-val vsf-url-val" :title="parsed.source_url">{{ parsed.source_url }}</span>
                </div>
              </div>

              <!-- ── Extra fields ── -->
              <el-divider style="margin:16px 0 12px" />

              <!-- Tags -->
              <div class="vsf-extra-row">
                <span class="vsf-extra-label">标签</span>
                <div class="vsf-tag-area">
                  <!-- Selected tags -->
                  <span
                    v-for="tag in selectedTags"
                    :key="tag.id"
                    class="vsf-tag-chip"
                    :style="tag.color ? { background: tag.color + '22', borderColor: tag.color, color: tag.color } : {}"
                  >
                    {{ tag.name }}
                    <button class="vsf-tag-remove" @click="removeTag(tag.id)">×</button>
                  </span>

                  <!-- Input to add/create tags -->
                  <div class="vsf-tag-input-wrap">
                    <input
                      v-model="newTagName"
                      class="vsf-tag-input"
                      placeholder="+ 添加标签"
                      @keydown.enter.prevent="addOrCreateTag"
                      @focus="showTagDropdown = true"
                      @blur="onTagInputBlur"
                    />
                    <div v-if="showTagDropdown && filteredTags.length > 0" class="vsf-tag-dropdown">
                      <div
                        v-for="tag in filteredTags"
                        :key="tag.id"
                        class="vsf-tag-option"
                        @mousedown.prevent="selectTag(tag)"
                      >
                        <span class="vsf-tag-dot" :style="tag.color ? { background: tag.color } : {}" />
                        {{ tag.name }}
                      </div>
                    </div>
                  </div>

                  <!-- Create hint -->
                  <span v-if="newTagName && !filteredTagExists" class="vsf-tag-hint">
                    按 Enter 新建「{{ newTagName }}」
                  </span>
                </div>
              </div>

              <!-- Repeatable -->
              <div class="vsf-extra-row" style="margin-top:10px">
                <span class="vsf-extra-label">可重复</span>
                <div class="vsf-repeat-toggle">
                  <button
                    class="vsf-toggle-btn"
                    :class="{ active: repeatable }"
                    @click="repeatable = !repeatable"
                  >
                    <span class="vsf-toggle-knob" />
                  </button>
                  <span class="vsf-toggle-text">{{ repeatable ? '是，可重复发送' : '否，仅发送一次' }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="vsf-actions">
            <el-button type="primary" size="large" :loading="saving" @click="handleSave">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
              保存入库
            </el-button>
            <el-button size="large" @click="reset">重新解析</el-button>
          </div>
        </div>
      </transition>

      <!-- Success -->
      <transition name="slide-up">
        <div v-if="saved" class="vsf-success">
          <div class="vsf-success-inner">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>
            <div class="vsf-success-title">保存成功！</div>
            <div class="vsf-success-sub">视频已添加到视频库</div>
            <div class="vsf-dl-hint">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0ea5e9" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              CDN 链接可能无法直接播放，可在视频库中点击「下载上传」将视频上传到永久存储后播放
            </div>
            <div class="vsf-success-btns">
              <el-button type="primary" @click="$router.push('/dashboard/video-library')">返回视频库</el-button>
              <el-button @click="addAnother">继续添加</el-button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { parseVideoUrl, createVideoSource, downloadVideoSource } from '../api/video_sources'
import { fetchTags, createTag } from '../api/tags'
import { isDuplicateRequestError } from '../api/http'

const router = useRouter()

const url = ref('')
const parsing = ref(false)
const saving = ref(false)
const parsed = ref(null)
const saved = ref(false)
const parseError = ref('')

// Tag state
const allTags = ref([])
const selectedTagIds = ref([])
const newTagName = ref('')
const showTagDropdown = ref(false)

// Repeatable state
const repeatable = ref(false)

const selectedTags = computed(() => allTags.value.filter(t => selectedTagIds.value.includes(t.id)))
const filteredTags = computed(() =>
  allTags.value.filter(t =>
    !selectedTagIds.value.includes(t.id) &&
    (!newTagName.value || t.name.toLowerCase().includes(newTagName.value.toLowerCase()))
  )
)
const filteredTagExists = computed(() =>
  allTags.value.some(t => t.name.toLowerCase() === newTagName.value.toLowerCase())
)

onMounted(async () => {
  try { allTags.value = await fetchTags() } catch { /* ignore */ }
})

function selectTag(tag) {
  if (!selectedTagIds.value.includes(tag.id)) {
    selectedTagIds.value = [...selectedTagIds.value, tag.id]
  }
  newTagName.value = ''
  showTagDropdown.value = false
}

function removeTag(id) {
  selectedTagIds.value = selectedTagIds.value.filter(tid => tid !== id)
}

async function addOrCreateTag() {
  const name = newTagName.value.trim()
  if (!name) return
  const existing = allTags.value.find(t => t.name.toLowerCase() === name.toLowerCase())
  if (existing) { selectTag(existing); return }
  try {
    const tag = await createTag({ name })
    allTags.value = [...allTags.value, tag]
    selectTag(tag)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '创建标签失败')
  }
}

function onTagInputBlur() {
  setTimeout(() => { showTagDropdown.value = false }, 150)
}

const PLATFORM_LABELS = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram' }
function platformLabel(p) { return PLATFORM_LABELS[p] || (p || '未知平台') }

function formatCount(n) {
  if (n == null) return '-'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function formatDate(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

function formatDuration(seconds) {
  if (!seconds) return '-'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

async function handleParse() {
  const trimmed = url.value.trim()
  if (!trimmed || parsing.value) return
  parseError.value = ''
  parsing.value = true
  parsed.value = null
  try {
    const result = await parseVideoUrl(trimmed)
    if (result.existing_id) {
      ElMessage.warning('该视频已存在于库中，跳转到详情页')
      setTimeout(() => router.push(`/dashboard/video-library/${result.existing_id}`), 1000)
      return
    }
    parsed.value = result
  } catch (err) {
    if (isDuplicateRequestError(err)) return
    parseError.value = err?.response?.data?.detail || '解析失败，请检查链接是否有效'
  } finally {
    parsing.value = false
  }
}

async function handleSave() {
  if (!parsed.value || saving.value) return
  saving.value = true
  try {
    const result = await createVideoSource({
      source_url: parsed.value.source_url,
      platform: parsed.value.platform,
      blogger_name: parsed.value.blogger_name,
      video_title: parsed.value.video_title,
      video_desc: parsed.value.video_desc,
      video_url: parsed.value.video_url,
      thumbnail_url: parsed.value.thumbnail_url,
      view_count: parsed.value.view_count,
      like_count: parsed.value.like_count,
      favorite_count: parsed.value.favorite_count,
      comment_count: parsed.value.comment_count,
      share_count: parsed.value.share_count,
      publish_date: parsed.value.publish_date,
      duration: parsed.value.duration,
      width: parsed.value.width,
      height: parsed.value.height,
      aspect_ratio: parsed.value.aspect_ratio,
      extra: parsed.value.extra,
      tag_ids: selectedTagIds.value,
      repeatable: repeatable.value,
    })

    const isExisting = result.created_at && (new Date() - new Date(result.created_at)) > 2000
    if (isExisting) {
      ElMessage.warning('该视频已存在于库中，跳转到详情页')
    } else {
      ElMessage.success('保存成功，正在跳转...')
      try { await downloadVideoSource(result.id) } catch { /* ignore */ }
    }
    setTimeout(() => router.push(`/dashboard/video-library/${result.id}`), 500)
  } catch (err) {
    if (isDuplicateRequestError(err)) return
    ElMessage.error(err?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function reset() {
  parsed.value = null
  parseError.value = ''
  url.value = ''
  selectedTagIds.value = []
  repeatable.value = false
  newTagName.value = ''
}

function addAnother() {
  saved.value = false
  reset()
}
</script>

<style scoped>
.vsf-page {
  padding: 28px 32px;
  animation: rise 0.3s ease;
}

.vsf-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  margin-bottom: 20px;
  transition: color 0.15s;
}
.vsf-back:hover { color: #6366f1; }

.vsf-card {
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 20px;
  padding: 32px;
  max-width: 900px;
  box-shadow: 0 4px 16px rgba(0,0,0,.06);
}

.vsf-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
}

.vsf-icon-wrap {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.vsf-title {
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
}
.vsf-subtitle { font-size: 13px; color: #64748b; margin-top: 3px; }

.vsf-url-row { display: flex; gap: 12px; margin-bottom: 16px; }
.vsf-url-input { flex: 1; }

.vsf-parse-btn {
  flex-shrink: 0;
  min-width: 100px;
  font-weight: 600;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
}

.vsf-error { margin-bottom: 16px; border-radius: 10px; }

.vsf-preview { margin-top: 8px; }

.divider-text { font-size: 13px; font-weight: 600; color: #475569; }

.vsf-preview-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
  margin-top: 8px;
}
@media (max-width: 640px) { .vsf-preview-body { grid-template-columns: 1fr; } }

.vsf-player-col { display: flex; flex-direction: column; gap: 10px; }

.vsf-player-wrap {
  border-radius: 12px;
  overflow: hidden;
  background: #0f172a;
  aspect-ratio: 16/9;
  display: flex;
  align-items: center;
  justify-content: center;
}

.vsf-video { width: 100%; height: 100%; object-fit: contain; display: block; }

.vsf-thumb-only { position: relative; width: 100%; height: 100%; }
.vsf-thumb-img { width: 100%; height: 100%; object-fit: cover; }

.vsf-noplay-hint {
  position: absolute;
  bottom: 8px;
  left: 0; right: 0;
  text-align: center;
  font-size: 12px;
  color: rgba(255,255,255,.7);
  background: rgba(0,0,0,.4);
  padding: 4px;
}

.vsf-no-media {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 160px;
}

.vsf-orig-link { font-size: 12px; display: inline-flex; align-items: center; }

.vsf-meta-col { display: flex; flex-direction: column; gap: 12px; }
.vsf-meta-platform { margin-bottom: 4px; }

.vsf-meta-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.4;
}

.vsf-meta-desc {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.vsf-meta-grid { display: flex; flex-direction: column; gap: 10px; margin-top: 4px; }

.vsf-meta-row { display: flex; gap: 12px; align-items: flex-start; }

.vsf-meta-label {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  min-width: 56px;
  text-transform: uppercase;
  letter-spacing: .04em;
  padding-top: 1px;
}

.vsf-meta-val { font-size: 14px; color: #334155; word-break: break-all; }
.vsf-url-val { font-size: 12px; color: #94a3b8; word-break: break-all; }

/* Extra fields */
.vsf-extra-row { display: flex; gap: 12px; align-items: flex-start; }

.vsf-extra-label {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  min-width: 56px;
  text-transform: uppercase;
  letter-spacing: .04em;
  padding-top: 6px;
  flex-shrink: 0;
}

/* Tag area */
.vsf-tag-area {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  flex: 1;
}

.vsf-tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px 3px 10px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  color: #475569;
}

.vsf-tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: inherit;
  opacity: 0.6;
  padding: 0;
  line-height: 1;
  margin-left: 2px;
}
.vsf-tag-remove:hover { opacity: 1; }

.vsf-tag-input-wrap { position: relative; }

.vsf-tag-input {
  border: 1px dashed #cbd5e1;
  border-radius: 20px;
  padding: 3px 12px;
  font-size: 12px;
  outline: none;
  width: 110px;
  color: #334155;
  background: #fff;
  transition: border-color 0.15s;
}
.vsf-tag-input::placeholder { color: #94a3b8; }
.vsf-tag-input:focus { border-color: #6366f1; border-style: solid; }

.vsf-tag-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0,0,0,.1);
  z-index: 100;
  min-width: 140px;
  overflow: hidden;
}

.vsf-tag-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  font-size: 13px;
  cursor: pointer;
  color: #334155;
}
.vsf-tag-option:hover { background: #f8fafc; }

.vsf-tag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6366f1;
  flex-shrink: 0;
}

.vsf-tag-hint {
  font-size: 11px;
  color: #6366f1;
  padding: 3px 8px;
  background: #eef2ff;
  border-radius: 6px;
}

/* Repeatable toggle */
.vsf-repeat-toggle { display: flex; align-items: center; gap: 10px; padding-top: 2px; }

.vsf-toggle-btn {
  position: relative;
  width: 42px;
  height: 24px;
  background: #e2e8f0;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
  padding: 0;
}
.vsf-toggle-btn.active { background: #6366f1; }

.vsf-toggle-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
  box-shadow: 0 1px 4px rgba(0,0,0,.2);
  display: block;
}
.vsf-toggle-btn.active .vsf-toggle-knob { transform: translateX(18px); }

.vsf-toggle-text { font-size: 13px; color: #475569; }

/* Actions */
.vsf-actions {
  display: flex;
  gap: 12px;
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid #f1f5f9;
}

/* Success */
.vsf-success { margin-top: 24px; }

.vsf-success-inner {
  text-align: center;
  padding: 40px 20px;
  border: 1px dashed #6ee7b7;
  border-radius: 16px;
  background: #f0fdf4;
}

.vsf-success-title { font-size: 20px; font-weight: 700; color: #065f46; margin: 12px 0 4px; }
.vsf-success-sub { font-size: 14px; color: #059669; margin-bottom: 20px; }
.vsf-success-btns { display: flex; gap: 12px; justify-content: center; }

.vsf-dl-hint {
  display: inline-flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  color: #0369a1;
  background: #e0f2fe;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  padding: 8px 12px;
  margin: 0 auto 16px;
  max-width: 420px;
  text-align: left;
  line-height: 1.5;
}

.slide-up-enter-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.slide-up-enter-from { opacity: 0; transform: translateY(16px); }

@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
