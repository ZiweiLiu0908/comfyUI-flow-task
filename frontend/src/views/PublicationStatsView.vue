<template>
  <div class="ps-page">
    <!-- Header -->
    <div class="ps-header">
      <h1 class="ps-title">数据统计</h1>
      <div class="ps-header-right">
        <button class="ps-btn ps-btn-sync" :disabled="syncing" @click="handleSyncMetrics">
          <svg v-if="!syncing" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:5px;vertical-align:-2px"><path d="M1 4v6h6"/><path d="M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:5px;vertical-align:-2px;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          {{ syncing ? '同步中...' : '同步数据' }}
        </button>
        <button class="ps-btn ps-btn-sync" :disabled="syncingKolClicks" @click="handleSyncKolClicks">
          <svg v-if="!syncingKolClicks" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:5px;vertical-align:-2px"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:5px;vertical-align:-2px;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          {{ syncingKolClicks ? '同步中...' : '同步Link点击' }}
        </button>
        <button class="ps-btn ps-btn-export" :disabled="exporting" @click="handleExport">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:5px;vertical-align:-2px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          {{ exporting ? '导出中...' : '导出Excel' }}
        </button>
        <!-- Date mode -->
        <el-radio-group v-model="filters.date_mode" size="small" @change="handleDateModeChange">
          <el-radio-button label="day">某一天</el-radio-button>
          <el-radio-button label="week">最近一周</el-radio-button>
          <el-radio-button label="month">最近一个月</el-radio-button>
          <el-radio-button label="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-if="filters.date_mode === 'day'"
          v-model="filters.single_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择UTC日期"
          size="small"
          style="width:150px"
          @change="syncDateFiltersFromMode"
        />
        <el-date-picker
          v-else-if="filters.date_mode === 'custom'"
          v-model="filters.date_range"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="UTC开始"
          end-placeholder="UTC结束"
          unlink-panels
          size="small"
          style="width:260px"
          @change="syncDateFiltersFromMode"
        />
      </div>
    </div>

    <!-- Filter bar -->
    <div class="ps-filter-bar">
      <el-select v-model="filters.platform" clearable placeholder="全部平台" size="small" style="width:120px">
        <el-option label="TikTok" value="tiktok" />
        <el-option label="YouTube" value="youtube" />
        <el-option label="Instagram" value="instagram" />
      </el-select>
      <el-select
        v-model="filters.account_id"
        clearable
        placeholder="搜索账号名..."
        filterable
        remote
        reserve-keyword
        :remote-method="searchAccounts"
        :loading="accountSearchLoading"
        size="small"
        style="width:220px"
        popper-class="ps-account-select-popper"
        @visible-change="onAccountDropdownVisibleChange"
      >
        <el-option
          v-for="account in accountOptions"
          :key="account.id"
          :label="account.account_name"
          :value="account.id"
        />
        <template #empty>
          <p style="text-align:center;color:#9ca3af;font-size:12px;padding:8px 0">
            {{ accountSearchLoading ? '加载中…' : '没有匹配的账号' }}
          </p>
        </template>
      </el-select>
      <el-select v-model="filters.promotion_code_filter" clearable placeholder="商品码：全部" size="small" style="width:140px" @change="applyFilters">
        <el-option label="有商品码" value="with" />
        <el-option label="无商品码" value="without" />
      </el-select>
      <el-input
        v-model.trim="filters.keyword"
        placeholder="标题、账号、渠道名、平台链接"
        size="small"
        clearable
        style="width:260px"
        @keyup.enter="applyFilters"
      />
      <button class="ps-btn ps-btn-primary" @click="applyFilters">筛选</button>
      <button class="ps-btn ps-btn-secondary" @click="resetFilters">重置</button>
      <span class="ps-count-badge">共 {{ total }} 条</span>
    </div>

    <!-- 视频分类筛选面板 -->
    <div class="ps-cat-panel">
      <div class="ps-cat-panel-header">
        <span class="ps-cat-panel-title">视频分类</span>
        <span class="ps-cat-panel-hint">视频仅可选择 1 个子类</span>
        <span v-if="categoryFilterLabel" class="ps-cat-panel-selected">
          已选分类：
          <span class="ps-cat-chip">
            {{ categoryFilterLabel }}
            <button class="ps-cat-chip-close" @click="clearCategoryFilter">×</button>
          </span>
          <button class="ps-cat-clear-text" @click="clearCategoryFilter">清除</button>
        </span>
      </div>
      <div class="ps-cat-panel-rows">
        <div class="ps-cat-row">
          <button
            type="button"
            class="ps-cat-pill is-unclassified"
            :class="{ active: filters.unclassified }"
            @click="selectCategoryFilter({ unclassified: true })"
          >未分类</button>
        </div>
        <div v-for="major in MAJOR_GROUPS" :key="major.key" class="ps-cat-row">
          <span class="ps-cat-row-label" :class="`is-${major.key}`">
            <span class="ps-cat-row-major">{{ major.key }}</span>
            <span class="ps-cat-row-cn">{{ major.label }}</span>
          </span>
          <button
            v-for="cat in CATEGORY_OPTIONS.filter(c => c.major === major.key)"
            :key="cat.index"
            type="button"
            class="ps-cat-pill"
            :class="[`is-${cat.major}`, { active: filters.category_indices[0] === cat.index }]"
            @click="selectCategoryFilter({ index: cat.index })"
          >{{ cat.label }}</button>
        </div>
      </div>
    </div>

    <!-- 已勾选视频聚合统计 -->
    <div v-if="selectedMap.size > 0" class="ps-selection-stats">
      <div class="ps-selection-stats-header">
        <input
          type="checkbox"
          class="ps-checkbox"
          checked
          @change="clearSelection"
        />
        <span class="ps-selection-stats-title">已选择 {{ selectedMap.size }} 条视频</span>
        <span class="ps-selection-stats-hint">（未达到数据的视频未计入统计）</span>
        <button class="ps-selection-stats-clear" @click="clearSelection">清空选择</button>
      </div>
      <div class="ps-selection-stats-grid">
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">平均播放量</div>
          <div class="ps-stat-card-value">{{ compactNumber(selectionStats.avgViews) }}</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">平均点赞数</div>
          <div class="ps-stat-card-value">{{ compactNumber(selectionStats.avgLikes) }}</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">平均评论数</div>
          <div class="ps-stat-card-value">{{ compactNumber(selectionStats.avgComments) }}</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">平均分享数</div>
          <div class="ps-stat-card-value">{{ compactNumber(selectionStats.avgShares) }}</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">平均点赞率</div>
          <div class="ps-stat-card-value">{{ formatPercent(selectionStats.avgLikeRate) }}</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">转化数（搜索次数）</div>
          <div class="ps-stat-card-value ps-stat-card-empty">-</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">转化率</div>
          <div class="ps-stat-card-value ps-stat-card-empty">-</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">平均转化数</div>
          <div class="ps-stat-card-value ps-stat-card-empty">-</div>
        </div>
        <div class="ps-stat-card">
          <div class="ps-stat-card-label">平均转化率</div>
          <div class="ps-stat-card-value ps-stat-card-empty">-</div>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div v-loading="loading" class="ps-table-wrap">
      <div v-if="!loading && items.length === 0" class="ps-empty">暂无符合条件的数据</div>
      <table v-else class="ps-table">
        <thead>
          <tr>
            <th class="ps-th ps-th-check">
              <input
                type="checkbox"
                class="ps-checkbox"
                :checked="allSelected"
                :indeterminate.prop="someSelected"
                @change="e => toggleSelectAll(e.target.checked)"
              />
            </th>
            <th class="ps-th ps-th-video">视频</th>
            <th class="ps-th ps-th-title">
              <button class="ps-sort-btn" @click="toggleSort('title')">标题{{ sortMark('title') }}</button>
            </th>
            <th class="ps-th">
              <button class="ps-sort-btn" @click="toggleSort('account_name')">账号{{ sortMark('account_name') }}</button>
            </th>
            <th class="ps-th">平台</th>
            <th class="ps-th">视频分类</th>
            <th class="ps-th">商品码</th>
            <th class="ps-th">
              <button class="ps-sort-btn" @click="toggleSort('published_at')">发布时间{{ sortMark('published_at') }}</button>
            </th>
            <th class="ps-th ps-th-num">
              <button class="ps-sort-btn" @click="toggleSort('total_views')">播放量{{ sortMark('total_views') }}</button>
            </th>
            <th class="ps-th ps-th-num">
              <button class="ps-sort-btn" @click="toggleSort('total_likes')">点赞{{ sortMark('total_likes') }}</button>
            </th>
            <th class="ps-th ps-th-num">
              <button class="ps-sort-btn" @click="toggleSort('total_comments')">评论{{ sortMark('total_comments') }}</button>
            </th>
            <th class="ps-th ps-th-num">
              <button class="ps-sort-btn" @click="toggleSort('total_shares')">分享{{ sortMark('total_shares') }}</button>
            </th>
            <th class="ps-th ps-th-num">
              <button class="ps-sort-btn" @click="toggleSort('avg_view_percentage')">平均观看比{{ sortMark('avg_view_percentage') }}</button>
            </th>
            <th class="ps-th ps-th-num">
              <button class="ps-sort-btn" @click="toggleSort('kol_link_clicks')">Link点击{{ sortMark('kol_link_clicks') }}</button>
            </th>
            <th class="ps-th ps-th-num">视频点击率</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.id"
            class="ps-tr"
            :class="{ 'is-selected': selectedMap.has(item.id) }"
            @click="openDetail(item)"
          >
            <td class="ps-td ps-td-check" @click.stop>
              <input
                type="checkbox"
                class="ps-checkbox"
                :checked="selectedMap.has(item.id)"
                @change="() => toggleSelectItem(item)"
              />
            </td>
            <td class="ps-td ps-td-video">
              <video v-if="item.video_url" :src="item.video_url" class="ps-video" controls preload="metadata" />
              <div v-else class="ps-video ps-video-empty">暂无视频</div>
            </td>
            <td class="ps-td ps-td-title">
              <div class="ps-title-main">{{ item.title || '未命名视频' }}</div>
              <div v-if="item.description" class="ps-title-sub">{{ item.description }}</div>
            </td>
            <td class="ps-td">
              <span class="ps-account-name">{{ item.account_name || '-' }}</span>
            </td>
            <td class="ps-td">
              <div class="ps-platforms">
                <a
                  v-for="channel in displayChannels(item)"
                  :key="`${item.id}-${channel.platform}-${channel.channel_id || 'na'}`"
                  :href="channel.platform_video_url || undefined"
                  :class="['ps-platform-tag', `ps-platform-${channel.platform}`]"
                  target="_blank"
                  rel="noreferrer"
                >{{ PLATFORM_LABELS[channel.platform] || channel.platform }}</a>
                <span v-if="!displayChannels(item).length" class="ps-dash">-</span>
              </div>
            </td>
            <td class="ps-td ps-td-category">
              <span
                v-if="item.category_label"
                class="ps-cat-tag"
                :class="`is-${item.major_category || 'unknown'}`"
              >{{ item.category_label }}</span>
              <span v-else class="ps-dash">-</span>
            </td>
            <td class="ps-td ps-td-promo">
              <span v-if="item.promotion_code" class="ps-promo-code">{{ item.promotion_code }}</span>
              <span v-else class="ps-dash">-</span>
            </td>
            <td class="ps-td ps-td-date">{{ formatDateTime(item.published_at || item.created_at) }}</td>
            <td class="ps-td ps-td-num">{{ compactNumber(item.total_views) }}</td>
            <td class="ps-td ps-td-num">{{ compactNumber(item.total_likes) }}</td>
            <td class="ps-td ps-td-num">{{ compactNumber(item.total_comments) }}</td>
            <td class="ps-td ps-td-num">{{ compactNumber(item.total_shares) }}</td>
            <td class="ps-td ps-td-num">{{ formatPercent(item.avg_view_percentage) }}</td>
            <td class="ps-td ps-td-num">{{ item.kol_link_clicks ?? '—' }}</td>
            <td class="ps-td ps-td-num">{{ videoClickRate(item) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="total > 0" class="ps-footer">
      <div class="ps-pagination-left">
        <span class="ps-count-text">显示 {{ startIdx }}-{{ endIdx }} 共 {{ total }} 条</span>
        <select v-model="filters.page_size" @change="handleSizeChange" class="ps-simple-select">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
          <option :value="500">500</option>
        </select>
      </div>
      <div class="ps-pagination">
        <button class="pg-btn" :disabled="filters.page <= 1" @click="changePage(filters.page - 1)">← 上一页</button>
        <template v-for="p in visiblePages" :key="p">
          <span v-if="p === '...'" class="pg-ellipsis">…</span>
          <button v-else class="pg-btn pg-num" :class="{ active: p === filters.page }" @click="changePage(p)">{{ p }}</button>
        </template>
        <button class="pg-btn" :disabled="filters.page >= totalPages" @click="changePage(filters.page + 1)">下一页 →</button>
      </div>
    </div>
  </div>

  <!-- 平台详情抽屉 -->
  <el-drawer
    v-model="drawerVisible"
    direction="rtl"
    size="420px"
    :with-header="false"
    append-to-body
    class="ps-drawer"
  >
    <div v-if="activeItem" class="psd-wrap">
      <!-- 抽屉头部 -->
      <div class="psd-header">
        <div class="psd-header-info">
          <div class="psd-video-title">{{ activeItem.title || '未命名视频' }}</div>
          <div class="psd-account">{{ activeItem.account_name }}</div>
        </div>
        <button class="psd-close" @click="drawerVisible = false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- 视频预览 -->
      <div class="psd-video-wrap">
        <video v-if="activeItem.video_url" :src="activeItem.video_url" class="psd-video" controls preload="metadata" />
        <div v-else class="psd-video psd-video-empty">暂无视频</div>
      </div>

      <!-- 汇总数据 -->
      <div class="psd-section-title">汇总数据</div>
      <div class="psd-summary-grid">
        <div class="psd-summary-card">
          <div class="psd-card-label">总播放量</div>
          <div class="psd-card-value">{{ compactNumber(activeItem.total_views) }}</div>
        </div>
        <div class="psd-summary-card">
          <div class="psd-card-label">总点赞</div>
          <div class="psd-card-value">{{ compactNumber(activeItem.total_likes) }}</div>
        </div>
        <div class="psd-summary-card">
          <div class="psd-card-label">总评论</div>
          <div class="psd-card-value">{{ compactNumber(activeItem.total_comments) }}</div>
        </div>
        <div class="psd-summary-card">
          <div class="psd-card-label">总分享</div>
          <div class="psd-card-value">{{ compactNumber(activeItem.total_shares) }}</div>
        </div>
        <div class="psd-summary-card">
          <div class="psd-card-label">平均观看比</div>
          <div class="psd-card-value">{{ formatPercent(activeItem.avg_view_percentage) }}</div>
        </div>
        <div class="psd-summary-card">
          <div class="psd-card-label">Link点击（美东当日）</div>
          <div class="psd-card-value">{{ activeItem.kol_link_clicks ?? '—' }}</div>
        </div>
        <div class="psd-summary-card">
          <div class="psd-card-label">视频点击率</div>
          <div class="psd-card-value">{{ videoClickRate(activeItem) }}</div>
        </div>
      </div>

      <!-- 各平台数据 -->
      <div class="psd-section-title">各平台数据</div>
      <div v-if="!displayChannels(activeItem).length" class="psd-no-channels">暂无平台数据</div>
      <div
        v-for="ch in displayChannels(activeItem)"
        :key="`${ch.platform}-${ch.channel_id}`"
        class="psd-channel-card"
      >
        <div class="psd-ch-header">
          <span :class="['psd-platform-tag', `ps-platform-${ch.platform}`]">
            {{ PLATFORM_LABELS[ch.platform] || ch.platform }}
          </span>
          <span class="psd-ch-name">{{ ch.channel_name || ch.channel_id || '-' }}</span>
          <a v-if="ch.platform_video_url" :href="ch.platform_video_url" target="_blank" rel="noreferrer" class="psd-link" @click.stop>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          </a>
        </div>
        <div class="psd-ch-stats">
          <template v-if="ch.stats">
            <div class="psd-stat-row" v-if="statVal(ch, 'views') != null">
              <span class="psd-stat-label">播放量</span>
              <span class="psd-stat-val">{{ compactNumber(statVal(ch, 'views')) }}</span>
            </div>
            <div class="psd-stat-row" v-if="ch.stats.engaged_views != null">
              <span class="psd-stat-label">有效播放</span>
              <span class="psd-stat-val">{{ compactNumber(ch.stats.engaged_views) }}</span>
            </div>
            <div class="psd-stat-row" v-if="statVal(ch, 'likes') != null">
              <span class="psd-stat-label">点赞</span>
              <span class="psd-stat-val">{{ compactNumber(statVal(ch, 'likes')) }}</span>
            </div>
            <div class="psd-stat-row" v-if="statVal(ch, 'comments') != null">
              <span class="psd-stat-label">评论</span>
              <span class="psd-stat-val">{{ compactNumber(statVal(ch, 'comments')) }}</span>
            </div>
            <div class="psd-stat-row" v-if="statVal(ch, 'shares') != null">
              <span class="psd-stat-label">分享</span>
              <span class="psd-stat-val">{{ compactNumber(statVal(ch, 'shares')) }}</span>
            </div>
            <div class="psd-stat-row" v-if="ch.stats.average_view_percentage != null">
              <span class="psd-stat-label">平均观看比</span>
              <span class="psd-stat-val">{{ formatPercent(ch.stats.average_view_percentage) }}</span>
            </div>
            <div class="psd-stat-row" v-if="ch.stats.average_view_duration != null">
              <span class="psd-stat-label">平均观看时长</span>
              <span class="psd-stat-val">{{ formatSeconds(ch.stats.average_view_duration) }}</span>
            </div>
            <div class="psd-stat-row" v-if="ch.stats.reach_count != null">
              <span class="psd-stat-label">触达人数</span>
              <span class="psd-stat-val">{{ compactNumber(ch.stats.reach_count) }}</span>
            </div>
            <div class="psd-stat-row" v-if="ch.stats.save_count != null">
              <span class="psd-stat-label">收藏</span>
              <span class="psd-stat-val">{{ compactNumber(ch.stats.save_count) }}</span>
            </div>
          </template>
          <div v-else class="psd-no-stats">暂无数据</div>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchAccount, fetchAccounts } from '../api/accounts'
import { exportPublicationStats, fetchPublicationStats, syncKolLinkClicks, syncPublicationMetrics } from '../api/video_publications'

const exporting = ref(false)

async function handleExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    syncDateFiltersFromMode()
    const response = await exportPublicationStats({
      platform: filters.platform || undefined,
      account_id: filters.account_id || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      keyword: filters.keyword || undefined,
      category_indices: filters.category_indices.length ? filters.category_indices.join(',') : undefined,
      unclassified: filters.unclassified ? true : undefined,
      promotion_code_filter: filters.promotion_code_filter || undefined,
    })
    const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    // 优先用后端 Content-Disposition 里的文件名，fallback 用日期
    const cd = response.headers?.['content-disposition'] || ''
    const match = cd.match(/filename\*?=(?:UTF-8'')?([^;]+)/i)
    const filename = match ? decodeURIComponent(match[1].trim()) : `数据统计_${filters.date_from || formatYmd(new Date())}.xlsx`
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    console.error(e)
    ElMessage.error('导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

const route = useRoute()

const PLATFORM_LABELS = {
  tiktok: 'TikTok',
  youtube: 'YouTube',
  instagram: 'Instagram',
}

// 与后端 video_classification_service.CATEGORY_LABELS 对齐
const CATEGORY_OPTIONS = [
  { index: 0, label: '单套衣服展示美', major: 'display' },
  { index: 1, label: '换装展示美', major: 'display' },
  { index: 2, label: '镜头感或表演型展示美', major: 'display' },
  { index: 3, label: '生活场景中的展示美', major: 'display' },
  { index: 4, label: '单品语言讲解', major: 'knowledge' },
  { index: 5, label: '造型选择或对比', major: 'knowledge' },
  { index: 6, label: '搭配教程或方法论', major: 'knowledge' },
  { index: 7, label: '单品展示无人讲解', major: 'knowledge' },
  { index: 8, label: '单品展示字幕讲解', major: 'knowledge' },
  { index: 9, label: '人生故事', major: 'persona' },
  { index: 10, label: '人生阶段', major: 'persona' },
  { index: 11, label: '个人态度表达', major: 'persona' },
  { index: 12, label: '热门梗段子反转梗流行文案', major: 'trending' },
  { index: 13, label: '明星影视综艺节日社会话题相关穿搭', major: 'trending' },
]

const MAJOR_GROUPS = [
  { key: 'display', label: '展示美学' },
  { key: 'knowledge', label: '穿搭知识' },
  { key: 'persona', label: '个人表达' },
  { key: 'trending', label: '热点趋势' },
]

const filters = reactive({
  platform: '',
  account_id: '',
  date_mode: 'week',
  single_date: '',
  date_range: [],
  date_from: '',
  date_to: '',
  keyword: '',
  category_indices: [],
  unclassified: false,
  promotion_code_filter: '',
  sort_by: 'published_at',
  sort_order: 'desc',
  page: 1,
  page_size: 20,
})

const categoryFilterLabel = computed(() => {
  if (filters.unclassified) return '未分类'
  const idx = filters.category_indices[0]
  if (idx == null) return ''
  return CATEGORY_OPTIONS.find(c => c.index === idx)?.label || ''
})

function selectCategoryFilter({ index = null, unclassified = false }) {
  if (unclassified) {
    if (filters.unclassified) {
      filters.unclassified = false
    } else {
      filters.unclassified = true
      filters.category_indices = []
    }
  } else {
    filters.unclassified = false
    if (filters.category_indices[0] === index) {
      filters.category_indices = []
    } else {
      filters.category_indices = [index]
    }
  }
  filters.page = 1
  load()
}

function clearCategoryFilter() {
  filters.unclassified = false
  filters.category_indices = []
  filters.page = 1
  load()
}

const loading = ref(false)
const items = ref([])
const total = ref(0)
const accountOptions = ref([])
const accountSearchLoading = ref(false)
// 远程搜索 + 滚动分页
const accountSearchKeyword = ref('')
const accountSearchPage = ref(1)
const accountSearchHasMore = ref(false)
const _ACCOUNT_PAGE_SIZE = 50

// ── 行勾选 ──────────────────────────────────────────────────────────────────
const selectedMap = ref(new Map())

const allSelected = computed(() =>
  items.value.length > 0 && items.value.every(item => selectedMap.value.has(item.id))
)
const someSelected = computed(() => {
  if (items.value.length === 0) return false
  const hits = items.value.filter(item => selectedMap.value.has(item.id)).length
  return hits > 0 && hits < items.value.length
})

function toggleSelectItem(item) {
  const next = new Map(selectedMap.value)
  if (next.has(item.id)) next.delete(item.id)
  else next.set(item.id, item)
  selectedMap.value = next
}

function toggleSelectAll(checked) {
  const next = new Map(selectedMap.value)
  if (checked) {
    for (const item of items.value) next.set(item.id, item)
  } else {
    for (const item of items.value) next.delete(item.id)
  }
  selectedMap.value = next
}

function clearSelection() {
  selectedMap.value = new Map()
}

// 已勾选聚合：缺失/0 值不参与对应指标的平均
const selectionStats = computed(() => {
  const list = [...selectedMap.value.values()]
  const avg = (key) => {
    let sum = 0
    let count = 0
    for (const it of list) {
      const n = Number(it?.[key])
      if (!Number.isFinite(n) || n <= 0) continue
      sum += n
      count += 1
    }
    return count > 0 ? sum / count : null
  }
  // 点赞率：每条视频 likes/views 的平均（仅在 views > 0 时计入）
  let rateSum = 0
  let rateCount = 0
  for (const it of list) {
    const v = Number(it?.total_views)
    const l = Number(it?.total_likes)
    if (!Number.isFinite(v) || v <= 0) continue
    if (!Number.isFinite(l) || l < 0) continue
    rateSum += (l / v) * 100
    rateCount += 1
  }
  return {
    avgViews: avg('total_views'),
    avgLikes: avg('total_likes'),
    avgComments: avg('total_comments'),
    avgShares: avg('total_shares'),
    avgLikeRate: rateCount > 0 ? rateSum / rateCount : null,
  }
})

// 抽屉
const drawerVisible = ref(false)
const activeItem = ref(null)

function openDetail(item) {
  activeItem.value = item
  drawerVisible.value = true
}

// metrics 未同步时 fallback 到 channels_status，保证平台标签可点击跳转
function displayChannels(item) {
  if (!item) return []
  const metrics = item.metrics_channels || []
  if (metrics.length > 0) return metrics
  const status = item.channels_status || []
  return status.map(s => ({
    platform: s.platform,
    channel_id: s.channel_id,
    channel_name: s.channel_name,
    platform_video_id: s.platform_video_id,
    platform_video_url: s.platform_video_url,
    status: s.status,
    stats: null,
  }))
}

// stats 字段兼容 view_count/views, like_count/likes 等双名
function statVal(ch, key) {
  const s = ch.stats
  if (!s) return null
  if (key === 'views') return s.views ?? s.view_count ?? null
  if (key === 'likes') return s.likes ?? s.like_count ?? null
  if (key === 'comments') return s.comments ?? s.comment_count ?? null
  if (key === 'shares') return s.shares ?? s.share_count ?? null
  return s[key] ?? null
}

function formatSeconds(val) {
  if (val == null) return '-'
  const n = Math.round(Number(val))
  if (n < 60) return `${n}s`
  return `${Math.floor(n / 60)}m${n % 60}s`
}

const totalPages = computed(() => Math.max(1, Math.ceil((total.value || 0) / filters.page_size)))
const startIdx = computed(() => total.value === 0 ? 0 : (filters.page - 1) * filters.page_size + 1)
const endIdx = computed(() => Math.min(filters.page * filters.page_size, total.value))

const visiblePages = computed(() => {
  const n = totalPages.value
  const cur = filters.page
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1)
  const pages = []
  pages.push(1)
  if (cur > 3) pages.push('...')
  for (let p = Math.max(2, cur - 1); p <= Math.min(n - 1, cur + 1); p++) pages.push(p)
  if (cur < n - 2) pages.push('...')
  pages.push(n)
  return pages
})

function formatYmd(date) {
  const y = date.getUTCFullYear()
  const m = `${date.getUTCMonth() + 1}`.padStart(2, '0')
  const d = `${date.getUTCDate()}`.padStart(2, '0')
  return `${y}-${m}-${d}`
}

function shiftDays(base, days) {
  const next = new Date(base)
  next.setUTCDate(next.getUTCDate() + days)
  return next
}

function syncDateFiltersFromMode() {
  const today = new Date()
  const todayYmd = formatYmd(today)
  if (filters.date_mode === 'day') {
    const value = filters.single_date || todayYmd
    filters.single_date = value
    filters.date_from = value
    filters.date_to = value
    return
  }
  if (filters.date_mode === 'week') {
    filters.date_from = formatYmd(shiftDays(today, -6))
    filters.date_to = todayYmd
    return
  }
  if (filters.date_mode === 'month') {
    filters.date_from = formatYmd(shiftDays(today, -29))
    filters.date_to = todayYmd
    return
  }
  const range = Array.isArray(filters.date_range) ? filters.date_range : []
  filters.date_from = range[0] || ''
  filters.date_to = range[1] || ''
}

function handleDateModeChange() {
  if (filters.date_mode === 'day' && !filters.single_date) {
    filters.single_date = formatYmd(new Date())
  }
  if (filters.date_mode === 'custom' && (!Array.isArray(filters.date_range) || !filters.date_range.length)) {
    filters.date_range = ['', '']
  }
  syncDateFiltersFromMode()
}

function sortMark(field) {
  if (filters.sort_by !== field) return ''
  return filters.sort_order === 'asc' ? ' ↑' : ' ↓'
}

function toggleSort(field) {
  if (filters.sort_by === field) {
    filters.sort_order = filters.sort_order === 'asc' ? 'desc' : 'asc'
  } else {
    filters.sort_by = field
    filters.sort_order = 'desc'
  }
  filters.page = 1
  load()
}

function formatDateTime(value) {
  if (!value) return '-'
  const text = new Date(value).toLocaleString('zh-CN', {
    timeZone: 'UTC',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
  return `${text} UTC`
}

function compactNumber(value) {
  if (value == null || value === '') return '-'
  const n = Number(value)
  if (Number.isNaN(n)) return String(value)
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatPercent(value) {
  if (value == null || value === '') return '-'
  return `${Number(value).toFixed(1)}%`
}

function videoClickRate(item) {
  const clicks = item?.kol_link_clicks
  const views = item?.total_views
  if (clicks == null || !views) return '—'
  return `${(clicks / views * 100).toFixed(2)}%`
}

async function searchAccounts(query) {
  // 关键词变化 → 重置到第 1 页
  accountSearchKeyword.value = (query || '').trim()
  accountSearchPage.value = 1
  accountSearchHasMore.value = false
  await _fetchAccountPage({ append: false })
}

async function loadMoreAccounts() {
  if (accountSearchLoading.value || !accountSearchHasMore.value) return
  accountSearchPage.value += 1
  await _fetchAccountPage({ append: true })
}

async function _fetchAccountPage({ append }) {
  accountSearchLoading.value = true
  try {
    const response = await fetchAccounts({
      page: accountSearchPage.value,
      page_size: _ACCOUNT_PAGE_SIZE,
      search: accountSearchKeyword.value || undefined,
    })
    const items = response?.items || []
    const total = response?.total ?? 0
    accountSearchHasMore.value = accountSearchPage.value * _ACCOUNT_PAGE_SIZE < total

    if (append) {
      // 滚动加载更多：去重追加
      const existing = new Set(accountOptions.value.map(a => a.id))
      accountOptions.value = [
        ...accountOptions.value,
        ...items.filter(a => !existing.has(a.id)),
      ]
    } else {
      // 替换：保留当前选中的账号防止从下拉里消失
      const next = items.slice()
      if (filters.account_id) {
        const hit = next.find(a => a.id === filters.account_id)
        if (!hit) {
          const prev = accountOptions.value.find(a => a.id === filters.account_id)
          if (prev) next.unshift(prev)
        }
      }
      accountOptions.value = next
    }
  } catch (e) {
    console.error(e)
  } finally {
    accountSearchLoading.value = false
  }
}

let _accountScrollListenerTarget = null
function _onAccountDropdownScroll(e) {
  const el = e.target
  if (!el) return
  // 距底部不到 60px 时触发下一页
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 60) {
    loadMoreAccounts()
  }
}

function onAccountDropdownVisibleChange(visible) {
  if (visible) {
    // popper 打开后异步绑定 scroll 监听（DOM 此时才挂载）
    setTimeout(() => {
      const popper = document.querySelector('.ps-account-select-popper')
      if (!popper) return
      // el-select 的滚动容器是 popper 内部的 .el-select-dropdown__wrap 或 .el-scrollbar__wrap
      const wrap = popper.querySelector('.el-select-dropdown__wrap, .el-scrollbar__wrap')
      if (!wrap || _accountScrollListenerTarget === wrap) return
      // 解绑老的（如果换了实例）
      if (_accountScrollListenerTarget) {
        _accountScrollListenerTarget.removeEventListener('scroll', _onAccountDropdownScroll)
      }
      wrap.addEventListener('scroll', _onAccountDropdownScroll, { passive: true })
      _accountScrollListenerTarget = wrap
    }, 0)
  } else if (_accountScrollListenerTarget) {
    _accountScrollListenerTarget.removeEventListener('scroll', _onAccountDropdownScroll)
    _accountScrollListenerTarget = null
  }
}

async function ensureSelectedAccountInOptions(accountId) {
  // 从 URL query 跳过来时，保证下拉里能看到选中账号的名称
  if (!accountId) return
  if (accountOptions.value.find(a => a.id === accountId)) return
  try {
    const acc = await fetchAccount(accountId)
    if (acc && acc.id) {
      accountOptions.value = [acc, ...accountOptions.value]
    }
  } catch (e) {
    console.error(e)
  }
}

async function load() {
  loading.value = true
  try {
    syncDateFiltersFromMode()
    const response = await fetchPublicationStats({
      platform: filters.platform || undefined,
      account_id: filters.account_id || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      keyword: filters.keyword || undefined,
      category_indices: filters.category_indices.length ? filters.category_indices.join(',') : undefined,
      unclassified: filters.unclassified ? true : undefined,
      promotion_code_filter: filters.promotion_code_filter || undefined,
      sort_by: filters.sort_by,
      sort_order: filters.sort_order,
      page: filters.page,
      page_size: filters.page_size,
    })
    items.value = response?.items || []
    total.value = Number(response?.total || 0)
  } catch (e) {
    console.error(e)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  filters.page = 1
  load()
}

function resetFilters() {
  filters.platform = ''
  filters.account_id = ''
  filters.date_mode = 'week'
  filters.single_date = ''
  filters.date_range = []
  filters.keyword = ''
  filters.category_indices = []
  filters.unclassified = false
  filters.promotion_code_filter = ''
  filters.sort_by = 'published_at'
  filters.sort_order = 'desc'
  filters.page = 1
  syncDateFiltersFromMode()
  load()
}

function changePage(page) {
  filters.page = page
  load()
}

const syncing = ref(false)
const syncingKolClicks = ref(false)

async function handleSyncMetrics() {
  if (syncing.value) return
  syncing.value = true
  try {
    syncDateFiltersFromMode()
    const result = await syncPublicationMetrics({
      platform: filters.platform || undefined,
      account_id: filters.account_id || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
    })
    ElMessage.success(result.message || '同步任务已提交')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '同步失败，请稍后重试')
  } finally {
    syncing.value = false
  }
}

async function handleSyncKolClicks() {
  if (syncingKolClicks.value) return
  syncingKolClicks.value = true
  try {
    syncDateFiltersFromMode()
    const result = await syncKolLinkClicks({
      platform: filters.platform || undefined,
      account_id: filters.account_id || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
    })
    ElMessage.success(result.message || 'Link 点击同步任务已提交')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || 'Link 点击同步失败，请稍后重试')
  } finally {
    syncingKolClicks.value = false
  }
}

function handleSizeChange() {
  filters.page = 1
  load()
}

onBeforeUnmount(() => {
  if (_accountScrollListenerTarget) {
    _accountScrollListenerTarget.removeEventListener('scroll', _onAccountDropdownScroll)
    _accountScrollListenerTarget = null
  }
})

onMounted(async () => {
  // 读取 query 参数（从 AI博主页跳转过来时携带）
  if (route.query.account_id) {
    filters.account_id = route.query.account_id
  }
  syncDateFiltersFromMode()
  // 初始拉一批账号供下拉默认展示，并补上 URL query 中预选的账号
  await Promise.all([
    searchAccounts(''),
    ensureSelectedAccountInOptions(filters.account_id),
    load(),
  ])
})
</script>

<style scoped>
.ps-page {
  padding: 28px 32px;
  min-height: 100%;
  animation: rise 0.3s ease;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

/* Header */
.ps-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.ps-title {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.ps-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* Filter bar */
.ps-filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}

.ps-btn {
  height: 32px;
  padding: 0 14px;
  border-radius: 8px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.ps-btn-primary {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
}

.ps-btn-primary:hover {
  opacity: 0.9;
}

.ps-btn-secondary {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.ps-btn-secondary:hover {
  background: #e2e8f0;
  color: #0f172a;
}

.ps-btn-sync {
  background: #f0fdf4;
  color: #15803d;
  border: 1px solid #bbf7d0;
  display: inline-flex;
  align-items: center;
}

.ps-btn-export {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
  display: inline-flex;
  align-items: center;
}

.ps-btn-export:hover {
  background: #dbeafe;
}

.ps-btn-export:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ps-btn-sync:hover:not(:disabled) {
  background: #dcfce7;
  border-color: #86efac;
}

.ps-btn-sync:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ps-count-badge {
  margin-left: auto;
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
}

/* Table */
.ps-table-wrap {
  width: 100%;
  overflow-x: auto;
  border: 1px solid #e8edf5;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,.04);
  margin-bottom: 16px;
}

.ps-empty {
  padding: 60px 0;
  text-align: center;
  color: #94a3b8;
  font-size: 14px;
}

.ps-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1200px;
}

.ps-th {
  padding: 11px 14px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-align: left;
  background: #f8fafc;
  border-bottom: 1px solid #e8edf5;
  white-space: nowrap;
  position: sticky;
  top: 0;
  z-index: 1;
}

.ps-th:first-child { border-top-left-radius: 14px; }
.ps-th:last-child  { border-top-right-radius: 14px; }

.ps-th-check  { width: 36px; padding-left: 12px; padding-right: 4px; }
.ps-th-video  { width: 110px; }
.ps-th-title  { min-width: 220px; }
.ps-th-num    { text-align: right; }

.ps-td-check { width: 36px; padding-left: 12px; padding-right: 4px; }
.ps-tr.is-selected { background: #eef2ff; }
.ps-tr.is-selected:hover { background: #e0e7ff; }

.ps-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #6366f1;
}

.ps-sort-btn {
  border: none;
  background: transparent;
  padding: 0;
  font: inherit;
  font-weight: 700;
  color: #64748b;
  cursor: pointer;
}

.ps-sort-btn:hover { color: #0f172a; }

.ps-tr {
  border-bottom: 1px solid #f1f5f9;
  transition: background 0.15s;
}

.ps-tr:last-child { border-bottom: none; }
.ps-tr:hover { background: #f8faff; }

.ps-td {
  padding: 10px 14px;
  vertical-align: middle;
  font-size: 13px;
  color: #334155;
}

.ps-td-video { width: 110px; }

.ps-td-num {
  text-align: right;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: #0f172a;
}

.ps-td-date {
  white-space: nowrap;
  font-size: 12px;
  color: #64748b;
}

.ps-td-title { max-width: 260px; }

.ps-video {
  width: 72px;
  height: 102px;
  border-radius: 8px;
  object-fit: contain;
  background: #0f172a;
  display: block;
}
video:fullscreen,
video:-webkit-full-screen,
video:-moz-full-screen {
  width: auto !important;
  height: 100% !important;
  object-fit: contain !important;
}

.ps-video-empty {
  display: grid;
  place-items: center;
  color: #cbd5e1;
  font-size: 11px;
}

.ps-title-main {
  font-weight: 700;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}

.ps-title-sub {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ps-account-name {
  font-weight: 500;
  white-space: nowrap;
}

.ps-platforms {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ps-platform-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}

.ps-platform-tiktok    { background: #f1f5f9; color: #0f172a; }
.ps-platform-youtube   { background: #fef2f2; color: #b91c1c; }
.ps-platform-instagram { background: #fff7ed; color: #c2410c; }

.ps-dash { color: #94a3b8; }

.ps-cat-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  background: #f1f5f9;
  color: #475569;
}
.ps-cat-tag.is-display { background: #fce7f3; color: #be185d; }
.ps-cat-tag.is-knowledge { background: #dbeafe; color: #1d4ed8; }
.ps-cat-tag.is-persona { background: #fef3c7; color: #b45309; }
.ps-cat-tag.is-trending { background: #d1fae5; color: #047857; }

.ps-promo-code {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 6px;
  background: #ecfdf5;
  color: #047857;
  font-size: 12px;
  font-weight: 600;
  font-family: 'SFMono-Regular', Menlo, Consolas, monospace;
  letter-spacing: 0.5px;
}

/* 视频分类筛选面板 */
.ps-cat-panel {
  margin: 12px 0;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}
.ps-cat-panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.ps-cat-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}
.ps-cat-panel-hint {
  font-size: 12px;
  color: #94a3b8;
}
.ps-cat-panel-selected {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #475569;
  margin-left: auto;
}
.ps-cat-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  background: #eef2ff;
  color: #4338ca;
  font-weight: 500;
}
.ps-cat-chip-close {
  border: none;
  background: transparent;
  color: #6366f1;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
.ps-cat-chip-close:hover { color: #4338ca; }
.ps-cat-clear-text {
  border: none;
  background: transparent;
  color: #6366f1;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
.ps-cat-clear-text:hover { text-decoration: underline; }
.ps-cat-panel-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ps-cat-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.ps-cat-row-label {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 130px;
  font-size: 12px;
}
.ps-cat-row-major {
  font-weight: 700;
  font-family: 'SFMono-Regular', Menlo, monospace;
}
.ps-cat-row-cn {
  color: #64748b;
}
.ps-cat-row-label.is-display .ps-cat-row-major { color: #be185d; }
.ps-cat-row-label.is-knowledge .ps-cat-row-major { color: #1d4ed8; }
.ps-cat-row-label.is-persona .ps-cat-row-major { color: #b45309; }
.ps-cat-row-label.is-trending .ps-cat-row-major { color: #047857; }
.ps-cat-pill {
  height: 28px;
  padding: 0 12px;
  border-radius: 14px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.ps-cat-pill:hover {
  border-color: #a5b4fc;
  color: #4338ca;
}
.ps-cat-pill.active {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
  font-weight: 500;
}
.ps-cat-pill.is-display.active { background: #ec4899; border-color: #ec4899; }
.ps-cat-pill.is-knowledge.active { background: #3b82f6; border-color: #3b82f6; }
.ps-cat-pill.is-persona.active { background: #f59e0b; border-color: #f59e0b; }
.ps-cat-pill.is-trending.active { background: #10b981; border-color: #10b981; }
.ps-cat-pill.is-unclassified.active { background: #64748b; border-color: #64748b; }

/* 已勾选视频聚合统计 */
.ps-selection-stats {
  margin: 12px 0;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}
.ps-selection-stats-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.ps-selection-stats-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}
.ps-selection-stats-hint {
  font-size: 12px;
  color: #94a3b8;
}
.ps-selection-stats-clear {
  margin-left: auto;
  border: none;
  background: transparent;
  color: #6366f1;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
.ps-selection-stats-clear:hover { text-decoration: underline; }
.ps-selection-stats-grid {
  display: grid;
  grid-template-columns: repeat(9, minmax(0, 1fr));
  gap: 14px;
}
.ps-stat-card {
  min-width: 0;
}
.ps-stat-card-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ps-stat-card-value {
  font-size: 20px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.2;
}
.ps-stat-card-empty { color: #cbd5e1; font-weight: 500; }
@media (max-width: 1400px) {
  .ps-selection-stats-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .ps-selection-stats-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

/* Footer pagination */
.ps-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0 4px;
  border-top: 1px solid #f1f5f9;
}

.ps-pagination-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ps-count-text {
  font-size: 13px;
  color: #64748b;
}

.ps-simple-select {
  height: 30px;
  padding: 0 8px;
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  font-size: 13px;
  color: #334155;
  background: #fff;
  cursor: pointer;
}

.ps-pagination {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pg-btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 7px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.pg-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pg-btn:not(:disabled):hover {
  border-color: #6366f1;
  color: #6366f1;
}

.pg-num.active {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
}

.pg-ellipsis {
  padding: 0 4px;
  color: #94a3b8;
}

/* Clickable rows */
.ps-tr { cursor: pointer; }

/* Drawer */
:deep(.ps-drawer .el-drawer__body) {
  padding: 0 !important;
  overflow-y: auto !important;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.psd-wrap {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: #f8fafc;
  overflow-y: auto;
  padding-bottom: 24px;
}

.psd-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 14px;
  background: #fff;
  border-bottom: 1px solid #e8edf5;
  flex-shrink: 0;
}

.psd-header-info { flex: 1; min-width: 0; }

.psd-video-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.psd-account {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.psd-close {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  background: #f1f5f9;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  transition: background 0.15s;
}
.psd-close:hover { background: #e2e8f0; color: #0f172a; }

.psd-video-wrap {
  padding: 16px 20px;
  background: #fff;
  border-bottom: 1px solid #e8edf5;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

.psd-video {
  width: 100%;
  max-width: 180px;
  height: 320px;
  border-radius: 10px;
  object-fit: contain;
  background: #0f172a;
  display: block;
}

.psd-video-empty {
  display: grid;
  place-items: center;
  color: #94a3b8;
  font-size: 13px;
}

.psd-section-title {
  padding: 14px 20px 8px;
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.psd-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 0 16px 12px;
}

.psd-summary-card {
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.psd-card-label {
  font-size: 11px;
  color: #64748b;
  line-height: 1.3;
}

.psd-card-value {
  font-size: 16px;
  font-weight: 800;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.psd-no-channels {
  padding: 16px 20px;
  color: #94a3b8;
  font-size: 13px;
}

.psd-channel-card {
  margin: 0 16px 10px;
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  overflow: hidden;
}

.psd-ch-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #f1f5f9;
  background: #fafbfc;
}

.psd-platform-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  flex-shrink: 0;
}

.psd-ch-name {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.psd-link {
  flex-shrink: 0;
  color: #6366f1;
  display: flex;
  align-items: center;
}
.psd-link:hover { color: #4f46e5; }

.psd-ch-stats {
  padding: 8px 14px;
}

.psd-stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid #f8fafc;
}
.psd-stat-row:last-child { border-bottom: none; }

.psd-stat-label {
  font-size: 12px;
  color: #64748b;
}

.psd-stat-val {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.psd-no-stats {
  padding: 8px 0;
  font-size: 12px;
  color: #94a3b8;
}

/* Element Plus overrides */
:deep(.el-radio-button__inner) {
  border-radius: 8px !important;
  border-left: 1px solid var(--el-border-color) !important;
  font-size: 12px;
  padding: 7px 12px;
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
  border-radius: 8px;
}
</style>
