<template>
  <div class="vl-page">
    <!-- ── Header ── -->
    <div class="vl-header">
      <h1 class="vl-title">视频库</h1>

      <!-- Tag management entry -->
      <div class="vl-tag-mgr-wrap">
        <button class="vl-tag-mgr-btn" @click="openTagManager">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;flex-shrink:0"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
          标签管理
          <span v-if="tags.length" class="vl-tag-count">{{ tags.length }}</span>
        </button>
      </div>

      <div class="vl-header-actions">
        <el-button class="vl-create-tpl-btn" :loading="batchCreatingTemplate" @click="handleBatchCreateTemplates">
          <svg v-if="!batchCreatingTemplate" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
          一键生成模板
        </el-button>
        <el-button class="vl-dl-all-btn" :loading="downloadingAll" @click="handleDownloadAll">
          <svg v-if="!downloadingAll" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          下载全部视频
        </el-button>
        <el-button type="primary" class="vl-add-btn" @click="$router.push('/dashboard/video-library/new')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加视频
        </el-button>
      </div>
    </div>

    <!-- ── Stats row ── -->
    <div class="vl-stats">
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">总视频数</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="1.75"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M10 9l5 3-5 3V9z" fill="#6366f1" stroke="none"/></svg>
        </div>
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-sub">
          <span class="stat-green">+{{ stats.recent_count }}</span> 本周新增
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">YOUTUBE</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="#ef4444"><path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.97C18.88 4 12 4 12 4s-6.88 0-8.59.45A2.78 2.78 0 0 0 1.46 6.42 29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58 2.78 2.78 0 0 0 1.95 1.97C5.12 20 12 20 12 20s6.88 0 8.59-.45a2.78 2.78 0 0 0 1.95-1.97A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58z"/><polygon points="9.75 15.02 15.5 12 9.75 8.98 9.75 15.02" fill="white"/></svg>
        </div>
        <div class="stat-value">{{ stats.youtube_count }}</div>
        <div class="stat-sub">YouTube 视频</div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">TIKTOK</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="#000"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.76a4.86 4.86 0 0 1-1.01-.07z"/></svg>
        </div>
        <div class="stat-value">{{ stats.tiktok_count }}</div>
        <div class="stat-sub">TikTok 视频</div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">本周新增</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="1.75"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        </div>
        <div class="stat-value">{{ stats.recent_count }}</div>
        <div class="stat-sub">最近 7 天</div>
      </div>
    </div>

    <!-- ── Filter bar ── -->
    <div class="vl-filterbar">
      <!-- Platform tabs -->
      <div class="vl-platform-tabs">
        <button
          v-for="tab in PLATFORM_TABS"
          :key="tab.value"
          class="vl-tab"
          :class="{ active: platform === tab.value }"
          @click="switchPlatform(tab.value)"
        >
          <span v-if="tab.value === 'youtube'" class="tab-icon-yt">▶</span>
          <span v-else-if="tab.value === 'tiktok'" class="tab-icon-tt">♪</span>
          <span v-else-if="tab.value === 'instagram'" class="tab-icon-ins">◈</span>
          {{ tab.label }}
        </button>
      </div>

      <!-- Blogger search -->
      <div class="vl-search-wrap">
        <svg class="vl-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input
          v-model="bloggerSearch"
          class="vl-search-input"
          placeholder="搜索博主..."
          @input="onSearchInput"
        />
        <button v-if="bloggerSearch" class="vl-search-clear" @click="clearSearch">✕</button>
      </div>
    </div>

    <!-- ── Card grid ── -->
    <div v-loading="loading" class="vl-grid">
      <div v-for="item in items" :key="item.id" class="vc" @click="goToDetail(item)">
        <!-- Thumbnail -->
        <div class="vc-thumb" @click.stop="openPlayer(item)">
          <img
            v-if="item.thumbnail_url"
            :src="item.thumbnail_url"
            class="vc-thumb-img"
            :alt="item.video_title"
          />
          <div v-else class="vc-thumb-placeholder" :style="thumbGradient(item.platform)">
            <span class="vc-platform-icon">{{ platformEmoji(item.platform) }}</span>
          </div>
          <div class="vc-thumb-overlay">
            <div class="vc-play-btn">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="white"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </div>
          </div>
          <div class="vc-badge">{{ platformShort(item.platform) }}</div>
          <span v-if="isAdmin() && item.owner_username" class="vc-owner-badge">{{ item.owner_username }}</span>
        </div>

        <!-- Body -->
        <div class="vc-body">
          <div class="vc-title" :title="item.video_title">{{ item.video_title || '(无标题)' }}</div>
          <div class="vc-blogger">
            <span class="vc-at">@{{ item.blogger_name || '未知博主' }}</span>
            <span v-if="item.view_count != null" class="vc-views">· {{ formatCount(item.view_count) }} 次播放</span>
          </div>

          <!-- Tags + repeatable row -->
          <div v-if="item.tags?.length || item.repeatable" class="vc-tag-row">
            <span
              v-for="tag in item.tags"
              :key="tag.id"
              class="vc-tag"
              :style="tag.color ? { background: tag.color + '22', borderColor: tag.color, color: tag.color } : {}"
            >{{ tag.name }}</span>
            <span v-if="item.repeatable" class="vc-repeat-badge">可重复</span>
          </div>

          <!-- Download status bar -->
          <div v-if="item.download_status === 'downloading'" class="vc-dl-status vc-dl-ing">
            <span class="vc-dl-spin"></span> 下载上传中...
          </div>
          <div v-else-if="item.download_status === 'done'" class="vc-dl-status vc-dl-done">
            ✓ 已上传可播放
          </div>
          <div v-else-if="item.download_status === 'failed'" class="vc-dl-status vc-dl-fail">
            ✗ 下载失败
          </div>

          <div class="vc-footer">
            <span class="vc-date">{{ formatDate(item.publish_date || item.created_at) }}</span>
            <div class="vc-actions">
              <button
                v-if="!item.local_video_url && item.download_status !== 'downloading'"
                class="vc-btn vc-btn-dl"
                :class="{ loading: downloading === item.id }"
                @click.stop="handleDownload(item)"
              >{{ item.download_status === 'failed' ? '重试上传' : '下载上传' }}</button>
              <button
                v-if="templateMap[item.id]"
                class="vc-btn vc-btn-tpl vc-btn-tpl-exists"
                @click.stop="router.push(`/dashboard/video-ai-templates/${templateMap[item.id]}/edit`)"
              >跳转模板</button>
              <button
                v-else-if="item.download_status === 'done'"
                class="vc-btn vc-btn-tpl"
                :class="{ loading: creatingTemplate === item.id }"
                @click.stop="handleCreateTemplate(item)"
              >生成模板</button>
              <button
                class="vc-btn vc-btn-del"
                :class="{ loading: deleting === item.id }"
                @click.stop="handleDelete(item)"
              >删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Empty ── -->
    <el-empty v-if="!loading && items.length === 0" description="暂无视频，尝试更换筛选条件或点击「添加视频」" :image-size="80" />

    <!-- ── Footer ── -->
    <div v-if="total > 0" class="vl-footer">
      <div class="vl-pagination-left">
        <span class="vl-count-text">显示 {{ startIdx }}-{{ endIdx }} 共 {{ total }} 条</span>
        <select v-model="pageSize" @change="handleSizeChange(pageSize)" class="vl-simple-select">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
          <option :value="500">500</option>
        </select>
      </div>
      <div class="vl-pagination">
        <button class="pg-btn" :disabled="page <= 1" @click="goPage(page - 1)">← 上一页</button>
        <!-- Page number buttons -->
        <template v-for="p in visiblePages" :key="p">
          <span v-if="p === '...'" class="pg-ellipsis">…</span>
          <button v-else class="pg-btn pg-num" :class="{ active: p === page }" @click="goPage(p)">{{ p }}</button>
        </template>
        <button class="pg-btn" :disabled="endIdx >= total" @click="goPage(page + 1)">下一页 →</button>
        <!-- Jump to page -->
        <span class="pg-jump-wrap">
          跳至
          <input
            v-model.number="jumpPage"
            class="pg-jump-input"
            type="number"
            :min="1"
            :max="totalPages"
            @keyup.enter="doJump"
          />
          页
          <button class="pg-btn pg-jump-go" @click="doJump">GO</button>
        </span>
      </div>
    </div>
  </div>

  <!-- ── Video player dialog ── -->
  <el-dialog
    v-model="playerVisible"
    :title="playerItem?.video_title || '视频播放'"
    width="800px"
    align-center
    destroy-on-close
  >
    <div class="player-wrap">
      <video
        v-if="playerItem?.local_video_url || playerItem?.video_url"
        :src="playerItem.local_video_url || playerItem.video_url"
        controls
        autoplay
        class="player-video"
      />
      <div v-else class="player-nourl">
        <el-empty description="暂无可播放地址，请先点击「下载上传」" :image-size="80" />
        <el-link :href="playerItem?.source_url" target="_blank" type="primary">前往原始链接观看</el-link>
      </div>
    </div>
    <div v-if="playerItem" class="player-meta">
      <span>@{{ playerItem.blogger_name || '-' }}</span>
      <el-divider direction="vertical" />
      <span>{{ platformShort(playerItem.platform) }}</span>
      <el-divider direction="vertical" />
      <span v-if="playerItem.view_count != null">{{ formatCount(playerItem.view_count) }} 次播放</span>
    </div>
  </el-dialog>

  <!-- ── Tag Manager Dialog ── -->
  <el-dialog
    v-model="tagMgrVisible"
    title="标签管理"
    width="480px"
    align-center
    destroy-on-close
    class="tag-mgr-dialog"
  >
    <div class="tm-body">
      <!-- Tag list -->
      <div class="tm-list" v-if="tags.length">
        <div v-for="tag in tags" :key="tag.id" class="tm-item">
          <span
            class="tm-color-dot"
            :style="tag.color ? { background: tag.color } : { background: '#94a3b8' }"
          ></span>
          <span
            class="tm-chip"
            :style="tag.color ? { background: tag.color + '22', color: tag.color, borderColor: tag.color + '55' } : {}"
          >{{ tag.name }}</span>
          <span class="tm-spacer"></span>
          <button
            class="tm-del-btn"
            :disabled="deletingTagId === tag.id"
            @click="handleDeleteTag(tag)"
            title="删除标签"
          >
            <svg v-if="deletingTagId !== tag.id" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
            <span v-else class="tm-del-spin"></span>
          </button>
        </div>
      </div>
      <el-empty v-else description="暂无标签，快来创建第一个吧" :image-size="60" style="padding: 16px 0" />

      <!-- Divider -->
      <div class="tm-divider"></div>

      <!-- Create new tag -->
      <div class="tm-create">
        <div class="tm-create-title">创建新标签</div>
        <div class="tm-create-row">
          <input
            v-model.trim="newTagName"
            class="tm-input"
            placeholder="标签名称"
            maxlength="50"
            @keyup.enter="handleCreateTag"
          />
          <div class="tm-color-pick-wrap">
            <input
              type="color"
              v-model="newTagColor"
              class="tm-color-input"
              title="选择颜色"
            />
            <span class="tm-color-preview" :style="{ background: newTagColor }"></span>
          </div>
          <button
            class="tm-create-btn"
            :disabled="!newTagName || creatingTag"
            @click="handleCreateTag"
          >
            <span v-if="creatingTag">创建中…</span>
            <span v-else>+ 创建</span>
          </button>
        </div>
        <!-- Preset colors -->
        <div class="tm-preset-colors">
          <span
            v-for="c in PRESET_COLORS"
            :key="c"
            class="tm-preset-dot"
            :class="{ selected: newTagColor === c }"
            :style="{ background: c }"
            @click="newTagColor = c"
          ></span>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, onActivated, onMounted, onUnmounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchVideoSources, fetchVideoSourceStats, deleteVideoSource, downloadVideoSource, downloadAllVideosZip } from '../api/video_sources'
import { batchCreateAndStartTemplates, createVideoAITemplate, startVideoAITemplate, fetchTemplatesByVideoSourceIds } from '../api/video_ai_templates'
import { fetchTags, createTag, deleteTag } from '../api/tags'
import { isDuplicateRequestError } from '../api/http'
import { useAuth, getToken } from '../composables/useAuth'

const { isAdmin } = useAuth()
const router = useRouter()
const route = useRoute()

const PLATFORM_TABS = [
  { label: '全部', value: '' },
  { label: 'TikTok', value: 'tiktok' },
  { label: 'YouTube', value: 'youtube' },
  { label: 'Instagram', value: 'instagram' },
]

const loading = ref(false)
const deleting = ref(null)
const downloading = ref(null)
const creatingTemplate = ref(null)
const items = ref([])
const total = ref(0)
const stats = ref({ total: 0, youtube_count: 0, tiktok_count: 0, recent_count: 0 })
const templateMap = ref({})
const playerVisible = ref(false)
const playerItem = ref(null)
const downloadingAll = ref(false)

// Tag manager state
const tagMgrVisible = ref(false)
const tags = ref([])
const newTagName = ref('')
const newTagColor = ref('#6366f1')
const creatingTag = ref(false)
const deletingTagId = ref(null)
const PRESET_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f59e0b', '#10b981', '#06b6d4', '#3b82f6', '#64748b']
const batchCreatingTemplate = ref(false)
let pollTimer = null
let searchTimer = null

// State synced with URL query
const page = ref(Number(route.query.page) || 1)
const pageSize = ref(Number(route.query.page_size) || 20)
const platform = ref(route.query.platform || '')
const bloggerSearch = ref(route.query.blogger || '')
const jumpPage = ref(page.value)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const startIdx = computed(() => total.value === 0 ? 0 : (page.value - 1) * pageSize.value + 1)
const endIdx = computed(() => Math.min(page.value * pageSize.value, total.value))

// Generate visible page numbers with ellipsis
const visiblePages = computed(() => {
  const n = totalPages.value
  const cur = page.value
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1)
  const pages = []
  pages.push(1)
  if (cur > 3) pages.push('...')
  for (let p = Math.max(2, cur - 1); p <= Math.min(n - 1, cur + 1); p++) pages.push(p)
  if (cur < n - 2) pages.push('...')
  pages.push(n)
  return pages
})

const PLATFORM_COLORS = {
  youtube: 'linear-gradient(135deg, #ff0000 0%, #cc0000 100%)',
  tiktok: 'linear-gradient(135deg, #010101 0%, #69c9d0 100%)',
  instagram: 'linear-gradient(135deg, #833ab4 0%, #fd1d1d 50%, #fcb045 100%)',
}
const PLATFORM_EMOJIS = { youtube: '▶', tiktok: '♪', instagram: '◈' }
const PLATFORM_SHORTS = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram' }
const DEFAULT_GRAD = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'

function thumbGradient(p) { return { background: PLATFORM_COLORS[p] || DEFAULT_GRAD } }
function platformEmoji(p) { return PLATFORM_EMOJIS[p] || '🎬' }
function platformShort(p) { return PLATFORM_SHORTS[p] || (p || '其他') }

function formatCount(n) {
  if (n == null) return '-'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
}

function syncUrl() {
  const query = {}
  if (page.value > 1) query.page = String(page.value)
  if (pageSize.value !== 20) query.page_size = String(pageSize.value)
  if (platform.value) query.platform = platform.value
  if (bloggerSearch.value) query.blogger = bloggerSearch.value
  router.replace({ query })
}

async function loadStats() {
  try {
    stats.value = await fetchVideoSourceStats()
  } catch { /* ignore */ }
}

async function loadData(silent = false) {
  if (!silent) loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (platform.value) params.platform = platform.value
    if (bloggerSearch.value) params.blogger_name = bloggerSearch.value

    const data = await fetchVideoSources(params)
    items.value = data.items || []
    total.value = data.total || 0
    schedulePollIfNeeded()
    const ids = items.value.map(i => i.id)
    if (ids.length) {
      templateMap.value = await fetchTemplatesByVideoSourceIds(ids)
    }
  } catch (err) {
    if (isDuplicateRequestError(err)) return
    if (!silent) ElMessage.error(err?.response?.data?.detail || '加载失败')
  } finally {
    if (!silent) loading.value = false
  }
}

function switchPlatform(val) {
  platform.value = val
  page.value = 1
  jumpPage.value = 1
  syncUrl()
  loadData()
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    jumpPage.value = 1
    syncUrl()
    loadData()
  }, 400)
}

function clearSearch() {
  bloggerSearch.value = ''
  page.value = 1
  jumpPage.value = 1
  syncUrl()
  loadData()
}

async function handleCreateTemplate(item) {
  creatingTemplate.value = item.id
  try {
    const tpl = await createVideoAITemplate({
      title: item.video_title || item.blogger_name || '新模板',
      description: '',
      video_source_id: item.id,
    })
    await startVideoAITemplate(tpl.id)
    templateMap.value = { ...templateMap.value, [item.id]: tpl.id }
    router.push(`/dashboard/video-ai-templates/${tpl.id}/edit`)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '创建模板失败')
  } finally {
    creatingTemplate.value = null
  }
}

function schedulePollIfNeeded() {
  clearTimeout(pollTimer)
  const hasDownloading = items.value.some(i => i.download_status === 'downloading')
  if (hasDownloading) {
    pollTimer = setTimeout(() => loadData(true), 3000)
  }
}

function goPage(p) {
  const target = Math.max(1, Math.min(p, totalPages.value))
  if (target === page.value) return
  page.value = target
  jumpPage.value = target
  syncUrl()
  loadData()
}

function handleSizeChange(val) {
  pageSize.value = val
  page.value = 1
  jumpPage.value = 1
  syncUrl()
  loadData()
}

function doJump() {
  const p = parseInt(jumpPage.value)
  if (!isNaN(p)) goPage(p)
}

function openPlayer(item) {
  playerItem.value = item
  playerVisible.value = true
}

function goToDetail(item) {
  syncUrl()
  router.push(`/dashboard/video-library/${item.id}`)
}

async function handleDownload(item) {
  downloading.value = item.id
  item.download_status = 'downloading'
  try {
    await downloadVideoSource(item.id)
    ElMessage.success('已开始下载，稍后自动更新状态')
    schedulePollIfNeeded()
  } catch (err) {
    item.download_status = null
    ElMessage.error(err?.response?.data?.detail || '启动下载失败')
  } finally {
    downloading.value = null
  }
}

async function handleDelete(item) {
  try {
    await ElMessageBox.confirm(
      `确定删除视频「${item.video_title || '无标题'}」？此操作不可恢复。`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'premium-delete-dialog',
      }
    )
  } catch { return }

  deleting.value = item.id
  try {
    await deleteVideoSource(item.id)
    ElMessage.success('已删除')
    await Promise.all([loadData(), loadStats()])
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  } finally {
    deleting.value = null
  }
}

async function handleBatchCreateTemplates() {
  batchCreatingTemplate.value = true
  try {
    await batchCreateAndStartTemplates()
    ElMessage.success('已触发批量生成模板，后台处理中…')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '批量创建模板失败')
  } finally {
    batchCreatingTemplate.value = false
  }
}

async function handleDownloadAll() {
  downloadingAll.value = true
  ElMessage.info('正在打包视频，请稍候…')
  try {
    const blob = await downloadAllVideosZip(getToken())
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = 'videos.zip'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(blobUrl), 10000)
    ElMessage.success('打包完成，已开始下载')
  } catch (err) {
    ElMessage.error(err?.message || '下载失败')
  } finally {
    downloadingAll.value = false
  }
}

async function loadTags() {
  try {
    tags.value = await fetchTags()
  } catch { /* ignore */ }
}

async function openTagManager() {
  tagMgrVisible.value = true
  await loadTags()
}

async function handleCreateTag() {
  if (!newTagName.value || creatingTag.value) return
  creatingTag.value = true
  try {
    await createTag({ name: newTagName.value, color: newTagColor.value })
    newTagName.value = ''
    newTagColor.value = '#6366f1'
    await loadTags()
    ElMessage.success('标签创建成功')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '创建失败')
  } finally {
    creatingTag.value = false
  }
}

async function handleDeleteTag(tag) {
  try {
    await ElMessageBox.confirm(
      `确定删除标签「${tag.name}」？已使用该标签的视频将自动解除关联。`,
      '删除标签',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  deletingTagId.value = tag.id
  try {
    await deleteTag(tag.id)
    await loadTags()
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  } finally {
    deletingTagId.value = null
  }
}

onMounted(() => {
  loadStats()
  loadData()
  loadTags()
})

// When navigating back from detail page (keep-alive scenario),
// re-sync state from URL and reload data
onActivated(() => {
  const q = route.query
  page.value = Number(q.page) || 1
  pageSize.value = Number(q.page_size) || 20
  platform.value = q.platform || ''
  bloggerSearch.value = q.blogger || ''
  jumpPage.value = page.value
  loadStats()
  loadData()
  loadTags()
})

onUnmounted(() => {
  clearTimeout(pollTimer)
  clearTimeout(searchTimer)
})
</script>

<style scoped>
/* ── Page layout ── */
.vl-page {
  padding: 28px 32px;
  min-height: 100%;
  animation: rise 0.3s ease;
}

.vl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28px;
}

.vl-title {
  font-size: 26px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.03em;
  margin: 0;
}

.vl-tag-mgr-wrap {
  display: flex;
  align-items: center;
  margin: 0 24px;
}

.vl-tag-mgr-btn {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}

.vl-tag-mgr-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}

.vl-tag-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  margin-left: 6px;
  background: #6366f1;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  border-radius: 9px;
}

/* ── Tag Manager Dialog ── */
.tm-body {
  padding: 4px 0;
}

.tm-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow-y: auto;
  padding-right: 4px;
  margin-bottom: 4px;
}

.tm-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
  transition: background 0.15s;
}

.tm-item:hover {
  background: #f1f5f9;
}

.tm-color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tm-chip {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #64748b;
}

.tm-spacer {
  flex: 1;
}

.tm-del-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.tm-del-btn:hover:not(:disabled) {
  background: #fee2e2;
  color: #ef4444;
}

.tm-del-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tm-del-spin {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid #e2e8f0;
  border-top-color: #ef4444;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.tm-divider {
  height: 1px;
  background: #f1f5f9;
  margin: 16px 0;
}

.tm-create {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tm-create-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.tm-create-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tm-input {
  flex: 1;
  height: 36px;
  padding: 0 12px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  font-size: 13px;
  color: #334155;
  outline: none;
  transition: border-color 0.15s;
}

.tm-input:focus {
  border-color: #6366f1;
}

.tm-color-pick-wrap {
  position: relative;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}

.tm-color-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.tm-color-preview {
  display: block;
  width: 36px;
  height: 36px;
  border-radius: 9px;
  border: 2px solid #e2e8f0;
  pointer-events: none;
}

.tm-create-btn {
  height: 36px;
  padding: 0 16px;
  border-radius: 9px;
  border: none;
  background: #6366f1;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.tm-create-btn:hover:not(:disabled) {
  background: #4f46e5;
}

.tm-create-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tm-preset-colors {
  display: flex;
  gap: 8px;
}

.tm-preset-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid transparent;
  transition: transform 0.15s, border-color 0.15s;
}

.tm-preset-dot:hover {
  transform: scale(1.2);
}

.tm-preset-dot.selected {
  border-color: #1e293b;
  transform: scale(1.15);
}

.vl-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.vl-dl-all-btn {
  display: flex;
  align-items: center;
  font-weight: 600;
  height: 40px;
  border-radius: 10px;
  padding: 0 18px;
  border: 1px solid #e2e8f0;
  color: #475569;
  background: #fff;
}

.vl-dl-all-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}

.vl-create-tpl-btn {
  display: flex;
  align-items: center;
  font-weight: 600;
  height: 40px;
  border-radius: 10px;
  padding: 0 18px;
  border: 1px solid #a7f3d0;
  color: #059669;
  background: #ecfdf5;
}

.vl-create-tpl-btn:hover {
  background: #d1fae5;
  border-color: #34d399;
}

.vl-add-btn {
  display: flex;
  align-items: center;
  font-weight: 600;
  height: 40px;
  border-radius: 10px;
  padding: 0 18px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
}

/* ── Stats ── */
.vl-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 14px;
  padding: 18px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}

.stat-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.stat-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: #94a3b8;
}

.stat-value {
  font-size: 32px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1;
  margin-bottom: 6px;
  letter-spacing: -0.03em;
}

.stat-sub {
  font-size: 12px;
  color: #94a3b8;
}

.stat-green {
  color: #10b981;
  font-weight: 600;
}

/* ── Filter bar ── */
.vl-filterbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.vl-platform-tabs {
  display: flex;
  gap: 6px;
  background: #f1f5f9;
  border-radius: 12px;
  padding: 4px;
}

.vl-tab {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 9px;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.vl-tab:hover {
  color: #334155;
  background: #e2e8f0;
}

.vl-tab.active {
  background: #fff;
  color: #4f46e5;
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
}

.tab-icon-yt { color: #ef4444; }
.tab-icon-tt { color: #000; }
.tab-icon-ins { color: #c026d3; }

.vl-search-wrap {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  max-width: 260px;
}

.vl-search-icon {
  position: absolute;
  left: 10px;
  color: #94a3b8;
  pointer-events: none;
}

.vl-search-input {
  width: 100%;
  height: 36px;
  padding: 0 32px 0 32px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  font-size: 13px;
  color: #334155;
  background: #fff;
  outline: none;
  transition: border-color 0.15s;
}

.vl-search-input:focus {
  border-color: #6366f1;
}

.vl-search-input::placeholder {
  color: #cbd5e1;
}

.vl-search-clear {
  position: absolute;
  right: 10px;
  font-size: 11px;
  color: #94a3b8;
  background: none;
  border: none;
  cursor: pointer;
  line-height: 1;
  padding: 2px;
}

.vl-search-clear:hover {
  color: #64748b;
}

/* ── Card grid ── */
.vl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 20px;
  margin-bottom: 28px;
}

/* ── Video card ── */
.vc {
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,.05);
  transition: box-shadow 0.2s, transform 0.2s;
  cursor: pointer;
}

.vc:hover {
  box-shadow: 0 8px 24px rgba(0,0,0,.1);
  transform: translateY(-2px);
}

/* Thumbnail */
.vc-thumb {
  position: relative;
  aspect-ratio: 16/9;
  cursor: pointer;
  overflow: hidden;
  background: #0f172a;
}

.vc-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.3s;
}

.vc:hover .vc-thumb-img {
  transform: scale(1.04);
}

.vc-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.vc-platform-icon {
  font-size: 36px;
  opacity: 0.5;
}

.vc-thumb-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.vc:hover .vc-thumb-overlay {
  background: rgba(0,0,0,0.35);
}

.vc-play-btn {
  opacity: 0;
  transform: scale(0.8);
  transition: opacity 0.2s, transform 0.2s;
  background: rgba(255,255,255,0.15);
  border-radius: 50%;
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

.vc:hover .vc-play-btn {
  opacity: 1;
  transform: scale(1);
}

.vc-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  background: rgba(0,0,0,0.55);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  backdrop-filter: blur(4px);
  letter-spacing: .03em;
}

.vc-owner-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  background: #f3e8ff;
  color: #9333ea;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  letter-spacing: .03em;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Card body */
.vc-body {
  padding: 14px 16px 12px;
}

.vc-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
  min-height: 2.8em;
}

.vc-blogger {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vc-at {
  font-weight: 600;
  color: #475569;
}

.vc-views {
  color: #94a3b8;
}

.vc-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid #f1f5f9;
  padding-top: 10px;
  margin-top: 4px;
}

.vc-date {
  font-size: 11px;
  color: #94a3b8;
}

.vc-actions {
  display: flex;
  gap: 6px;
}

.vc-btn {
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 7px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
}

.vc-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}

.vc-btn-del {
  border-color: #fecaca;
  color: #dc2626;
  background: #fef2f2;
}

.vc-btn-del:hover {
  border-color: #fca5a5;
  color: #b91c1c;
  background: #fee2e2;
}

.vc-btn-dl:hover {
  border-color: #0ea5e9;
  color: #0ea5e9;
  background: #f0f9ff;
}

.vc-btn-tpl {
  border-color: #c7d2fe;
  color: #4f46e5;
  background: #eef2ff;
}

.vc-btn-tpl:hover {
  border-color: #6366f1;
  color: #4338ca;
  background: #e0e7ff;
}

.vc-btn-tpl-exists {
  border-color: #fed7aa;
  color: #c2410c;
  background: #fff7ed;
}

.vc-btn-tpl-exists:hover {
  border-color: #fb923c;
  color: #9a3412;
  background: #ffedd5;
}

/* Download status bar */
.vc-dl-status {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 5px;
}

.vc-dl-ing {
  background: #fef9c3;
  color: #a16207;
}

.vc-dl-done {
  background: #dcfce7;
  color: #166534;
}

.vc-dl-fail {
  background: #fee2e2;
  color: #991b1b;
}

.vc-dl-spin {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 2px solid #a16207;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.vc-btn.loading {
  opacity: 0.5;
  pointer-events: none;
}

/* ── Footer ── */
.vl-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0 8px;
  border-top: 1px solid #f1f5f9;
  flex-wrap: wrap;
  gap: 12px;
}

.vl-pagination-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.vl-count-text {
  font-size: 13px;
  color: #94a3b8;
}

.vl-simple-select {
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  outline: none;
  padding: 0 4px;
}

.vl-simple-select:hover {
  color: #64748b;
}

.vl-pagination {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.pg-btn {
  font-size: 13px;
  font-weight: 500;
  padding: 7px 14px;
  border-radius: 9px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
}

.pg-btn:hover:not(:disabled) {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}

.pg-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pg-num {
  min-width: 36px;
  padding: 7px 10px;
  text-align: center;
}

.pg-num.active {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  border-color: transparent;
  font-weight: 700;
}

.pg-ellipsis {
  font-size: 13px;
  color: #94a3b8;
  padding: 0 4px;
  user-select: none;
}

.pg-jump-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #94a3b8;
  margin-left: 4px;
}

.pg-jump-input {
  width: 52px;
  height: 34px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  text-align: center;
  font-size: 13px;
  color: #334155;
  outline: none;
  padding: 0 6px;
}

.pg-jump-input:focus {
  border-color: #6366f1;
}

.pg-jump-input::-webkit-inner-spin-button,
.pg-jump-input::-webkit-outer-spin-button {
  -webkit-appearance: none;
}

.pg-jump-go {
  padding: 7px 12px;
}

/* ── Player dialog ── */
.player-wrap {
  background: #000;
  border-radius: 10px;
  overflow: hidden;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.player-video {
  width: 100%;
  max-height: 460px;
  display: block;
}

.player-nourl {
  padding: 40px;
  text-align: center;
  background: #fff;
  width: 100%;
}

.player-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #64748b;
  margin-top: 14px;
  padding: 0 2px;
}

/* ── Animation ── */
@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Tags + repeatable on card */
.vc-tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 6px 0 4px;
}

.vc-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
  line-height: 1.6;
}

.vc-repeat-badge {
  display: inline-block;
  padding: 2px 8px;
  background: #ecfdf5;
  border: 1px solid #6ee7b7;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 500;
  color: #059669;
  line-height: 1.6;
}

/* Responsive */
@media (max-width: 1200px) {
  .vl-stats { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .vl-page { padding: 16px; }
  .vl-stats { grid-template-columns: repeat(2, 1fr); }
  .vl-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
  .vl-filterbar { gap: 10px; }
}
</style>
