<template>
  <div class="al-page">
    <div class="al-header">
      <h1 class="al-title">AI博主</h1>
      <div class="al-header-actions">
        <el-button class="al-config-btn" @click="openAISettings">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          AI博主配置
        </el-button>
        <el-button class="al-config-btn" @click="handleBulkGenerateAIAccounts" :loading="bulkGenerating">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M12 5v14"/><path d="M5 12h14"/><path d="M4 4h16v16H4z" opacity=".2"/></svg>
          一键生成AI博主
        </el-button>
        <el-button class="al-tagging-btn" @click="handleBulkPersonaTagging" :loading="personaTagging">
          <svg v-if="!personaTagging" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
          {{ selectedMap.size > 0 ? `人设打标 (${selectedMap.size})` : '人设打标' }}
        </el-button>
        <el-button class="al-restart-btn" @click="openBulkContinueDialog" :loading="bulkRestarting" :disabled="items.length === 0">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
          {{ selectedMap.size > 0 ? `一键继续 (${selectedMap.size})` : '一键继续' }}
        </el-button>
        <el-button class="al-gen-btn" :loading="bulkVideoGenerating" :disabled="total === 0" @click="handleBulkVideoGenerate">
          <svg v-if="!bulkVideoGenerating" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          {{ bulkVideoGenerating ? `${bulkVideoGenProgress.current}/${bulkVideoGenProgress.total}` : selectedMap.size > 0 ? `一键生成 (${selectedMap.size})` : '一键生成' }}
        </el-button>
        <el-button class="al-schedule-btn" :disabled="total === 0" @click="openScheduledGenerationDialog">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" style="margin-right:6px"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/><path d="M8 12h4"/></svg>
          定时生成
        </el-button>
        <el-button class="al-schedule-btn" :disabled="total === 0" @click="openBulkScheduleDialog">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="margin-right:6px"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          {{ selectedMap.size > 0 ? `一键定时 (${selectedMap.size})` : '一键定时' }}
        </el-button>
        <el-button class="al-supplement-btn" :disabled="total === 0" @click="openSupplementDialog">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
          {{ selectedMap.size > 0 ? `补充模板 (${selectedMap.size})` : '补充模板' }}
        </el-button>
        <el-button class="al-supplement-btn" :disabled="total === 0" @click="openSupplementScheduleDialog">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" style="margin-right:6px"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          定时补充
        </el-button>
        <el-button class="al-namehandle-btn" :loading="bulkNameHandleLoading" :disabled="total === 0" @click="confirmBulkNameHandle">
          <svg v-if="!bulkNameHandleLoading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          {{ selectedMap.size > 0 ? `生成Handle (${selectedMap.size})` : '生成Handle' }}
        </el-button>
        <el-button class="al-hashtag-btn" :loading="hashtagSearchLoading" :disabled="total === 0" @click="openHashtagSearchDialog">
          <svg v-if="!hashtagSearchLoading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/></svg>
          {{ selectedMap.size > 0 ? `标签搜索 (${selectedMap.size})` : '标签搜索' }}
        </el-button>
        <el-button class="al-classify-btn" :loading="bulkClassifying" :disabled="total === 0" @click="openClassifyConfirm('batch')">
          <svg v-if="!bulkClassifying" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/></svg>
          {{ selectedMap.size > 0 ? `视频分类 (${selectedMap.size})` : '视频分类' }}
        </el-button>
        <el-button class="al-tasks-btn" :loading="downloading" @click="handleDownload">
          <svg v-if="!downloading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          {{ downloading ? '下载中...' : selectedMap.size > 0 ? `下载 (${selectedMap.size})` : '下载视频' }}
        </el-button>
        <el-button class="al-tasks-btn" :loading="exporting" @click="handleExportVideoUrls">
          <svg v-if="!exporting" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          {{ exporting ? '导出中...' : selectedMap.size > 0 ? `一键导出 (${selectedMap.size})` : '一键导出' }}
        </el-button>
        <el-button type="primary" class="al-add-btn" @click="$router.push('/dashboard/accounts/new')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:6px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建账号
        </el-button>
      </div>
    </div>

    <!-- 平台统计卡片 -->
    <div class="ps-row" v-loading="platformStatsLoading">
      <div
        v-for="stat in platformStats"
        :key="stat.platform"
        class="ps-card"
      >
        <div class="ps-card-header">
          <div class="ps-platform-icon" v-html="PLATFORM_META[stat.platform]?.icon || ''"></div>
          <span class="ps-platform-name">{{ PLATFORM_META[stat.platform]?.label || stat.platform }}</span>
          <span
            class="ps-platform-tag"
            :style="{
              color: PLATFORM_META[stat.platform]?.tagColor,
              background: PLATFORM_META[stat.platform]?.tagBg,
            }"
          >{{ PLATFORM_META[stat.platform]?.tag }}</span>
        </div>
        <div class="ps-stats">
          <div class="ps-stat-item">
            <span class="ps-stat-label">已绑定</span>
            <span class="ps-stat-value">{{ stat.bound }}</span>
          </div>
          <div class="ps-stat-item">
            <span class="ps-stat-label">已确认</span>
            <span class="ps-stat-value">{{ stat.confirmed }}</span>
          </div>
          <div class="ps-stat-item">
            <span class="ps-stat-label">无库存</span>
            <span class="ps-stat-value ps-stat-warn">{{ stat.no_stock }}</span>
          </div>
          <div class="ps-stat-item">
            <span class="ps-stat-label">未绑定</span>
            <span class="ps-stat-value ps-stat-muted">{{ stat.unbound }}</span>
          </div>
        </div>
        <div class="ps-status-hint" v-if="stat.no_stock > 0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ stat.no_stock }} 个{{ PLATFORM_META[stat.platform]?.label }} AI 博主当前无有效库存
        </div>
        <div class="ps-status-hint ps-status-ok" v-else-if="stat.bound > 0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>
          库存状态充足，运作良好
        </div>
        <div class="ps-status-hint ps-status-info" v-else-if="stat.unbound > 0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ stat.unbound }} 个新账号待初始化设置
        </div>
      </div>
    </div>

    <!-- AI博主配置弹窗 -->
    <el-dialog
      v-model="showAISettingsDialog"
      title="AI博主配置"
      width="700px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-loading="aiSettingsLoading" class="ai-cfg-body">

        <!-- 阶段一：视频理解 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">阶段一：视频理解</span>
            <span class="ai-cfg-desc">从标签关联的全部视频里随机抽样，生成理解结果并用于名称生成</span>
          </div>
          <el-form-item label="分析样本数">
            <el-input-number v-model="aiSettingsForm.ai_account_analysis_sample_size" :min="1" :max="50" style="width: 160px" />
          </el-form-item>
          <el-form-item label="视频分析提示词">
            <el-input v-model="aiSettingsForm.ai_account_video_prompt" type="textarea" :rows="4" placeholder="请输入视频分析提示词..." />
          </el-form-item>
          <el-form-item label="视频理解模型">
            <el-input v-model="aiSettingsForm.ai_account_video_model" placeholder="e.g. gemini-3.1-pro-preview" />
          </el-form-item>
        </div>

        <!-- 阶段二：名称生成 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">阶段二：名称生成</span>
            <span class="ai-cfg-desc">基于视频描述，调用 Gemini 生成博主名称</span>
          </div>
          <el-form-item label="名称生成提示词">
            <el-input v-model="aiSettingsForm.ai_account_name_prompt" type="textarea" :rows="4" placeholder="请输入名称生成提示词..." />
          </el-form-item>
          <el-form-item label="名称生成模型">
            <el-input v-model="aiSettingsForm.ai_account_name_model" placeholder="e.g. gemini-3.1-pro-preview" />
          </el-form-item>
        </div>

        <!-- 阶段三：照片候选生成 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">阶段三：照片候选生成</span>
            <span class="ai-cfg-desc">随机选择最多 3 个不同视频，每个视频并发生成 3 张照片候选，用户后续手动选择一张进入头像生成</span>
          </div>
          <el-form-item label="照片生成提示词">
            <el-input v-model="aiSettingsForm.ai_account_photo_image_prompt" type="textarea" :rows="3" placeholder="Nano2 生图提示词前缀，将与视频描述拼接后调用生图..." />
          </el-form-item>
        </div>

        <!-- 阶段四：头像生成 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">阶段四：头像生成</span>
            <span class="ai-cfg-desc">基于人工选中的照片候选和视频描述生成博主头像</span>
          </div>
          <el-form-item label="头像生成提示词">
            <el-input v-model="aiSettingsForm.ai_account_avatar_prompt" type="textarea" :rows="4" placeholder="请输入头像生成提示词..." />
          </el-form-item>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px">
            <el-form-item label="头像生成模型">
              <el-input v-model="aiSettingsForm.ai_account_avatar_model" placeholder="e.g. nano2" />
            </el-form-item>
            <el-form-item label="头像尺寸">
              <el-select v-model="aiSettingsForm.ai_account_avatar_size" style="width:100%">
                <el-option label="1:1 (正方形)" value="1:1" />
                <el-option label="9:16 (竖版)" value="9:16" />
                <el-option label="16:9 (横版)" value="16:9" />
                <el-option label="3:4" value="3:4" />
              </el-select>
            </el-form-item>
            <el-form-item label="头像质量">
              <el-select v-model="aiSettingsForm.ai_account_avatar_quality" style="width:100%">
                <el-option label="1K" value="1K" />
                <el-option label="2K" value="2K" />
                <el-option label="4K" value="4K" />
              </el-select>
            </el-form-item>
          </div>
        </div>

        <!-- 批量生成名称/Handle/签名 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">批量生成：独享号 &amp; 人设号 Prompt</span>
            <span class="ai-cfg-desc">
              基于绑定的 TikTok 博主信息生成，可用占位符：
              <code style="background:#f3f4f6;padding:1px 4px;border-radius:3px">{blogger_name}</code>
              <code style="background:#f3f4f6;padding:1px 4px;border-radius:3px">{blogger_handle}</code>
              <code style="background:#f3f4f6;padding:1px 4px;border-radius:3px">{blogger_signature}</code>
            </span>
          </div>
          <el-form-item label="独享号/人设号 Prompt">
            <el-input v-model="aiSettingsForm.ai_account_exclusive_name_prompt" type="textarea" :rows="4" placeholder="例：参考博主 {blogger_name}（@{blogger_handle}）的简介「{blogger_signature}」，为新账号生成一个创意名称、handle 和个人签名..." />
          </el-form-item>
        </div>

        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">批量生成：共享号 Prompt</span>
            <span class="ai-cfg-desc">
              基于绑定的标签关键词生成，可用占位符：
              <code style="background:#f3f4f6;padding:1px 4px;border-radius:3px">{keyword}</code>
            </span>
          </div>
          <el-form-item label="共享号 Prompt">
            <el-input v-model="aiSettingsForm.ai_account_shared_name_prompt" type="textarea" :rows="4" placeholder="例：根据关键词「{keyword}」，为一个共享账号生成博主名称、handle 和签名..." />
          </el-form-item>
        </div>

        <!-- 标签搜索配置 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">标签搜索（Hashtag Search）</span>
            <span class="ai-cfg-desc">根据账号绑定的 TikTok 博主，抓取热门视频的 HashTag，经 AI 过滤后返回推荐标签列表</span>
          </div>
          <el-form-item label="抓取视频数量">
            <el-input-number v-model="aiSettingsForm.hashtag_search_top_n" :min="10" :max="500" :step="10" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">条（按播放量排序取前 N 个视频）</span>
          </el-form-item>
          <el-form-item label="过滤模型">
            <el-input v-model="aiSettingsForm.hashtag_filter_model" placeholder="e.g. gemini-3.1-pro-preview" />
          </el-form-item>
          <el-form-item label="AI 过滤提示词">
            <el-input
              v-model="aiSettingsForm.hashtag_filter_prompt"
              type="textarea"
              :rows="5"
              placeholder="例：以下是从 TikTok 视频中提取的 HashTag 列表，请过滤掉无意义、过于通用（如 fyp、viral）或与目标内容无关的标签，保留能精准描述内容品类、场景、风格的标签..."
            />
            <div style="margin-top:4px;color:#9ca3af;font-size:12px">留空则跳过 AI 过滤，直接返回全量去重 HashTag。系统会在提示词末尾自动拼接 JSON 格式化指令。</div>
          </el-form-item>
        </div>

        <!-- 视频分类配置 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">视频分类</span>
            <span class="ai-cfg-desc">基于 local_video_url，使用 Gemini 将视频归入 14 个细分类（4 大类）</span>
          </div>
          <el-form-item label="模型">
            <el-input v-model="aiSettingsForm.video_classify_model" placeholder="e.g. gemini-3.1-pro-preview" />
          </el-form-item>
          <el-form-item label="温度">
            <div style="display:flex;align-items:center;gap:12px;width:100%">
              <el-slider v-model="aiSettingsForm.video_classify_temperature" :min="0" :max="2" :step="0.1" style="flex:1" />
              <span style="width:36px;text-align:right;font-size:13px;color:#374151">{{ aiSettingsForm.video_classify_temperature }}</span>
            </div>
          </el-form-item>
          <el-form-item label="提示词">
            <el-input
              v-model="aiSettingsForm.video_classify_prompt"
              type="textarea"
              :rows="6"
              placeholder="留空则使用内置默认提示词"
            />
            <div style="margin-top:6px;display:flex;align-items:center;gap:8px">
              <span style="color:#9ca3af;font-size:12px">无论是否自定义，系统都会通过 response_schema 限制返回 {"category_key": "..."}。</span>
              <button type="button" class="ai-default-prompt-toggle" @click="showDefaultPrompt = !showDefaultPrompt">
                {{ showDefaultPrompt ? '收起' : '查看内置默认提示词' }}
              </button>
            </div>
            <div v-if="showDefaultPrompt" class="ai-default-prompt-box">{{ DEFAULT_CLASSIFY_PROMPT }}</div>
          </el-form-item>
        </div>

        <!-- 分类聚合阈值 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">博主分类阈值</span>
            <span class="ai-cfg-desc">基于大类占比（排除「不能分类」）将 AI 博主判定为单核心 / 双核心 / 混乱</span>
          </div>
          <el-form-item label="样本阈值">
            <el-input-number v-model="aiSettingsForm.classify_min_sample" :min="1" :max="50" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">成功分类数 &lt; 此值时记为「样本不足」</span>
          </el-form-item>
          <div style="margin-bottom:8px;color:#374151;font-size:13px;font-weight:500">单核心阈值（某大类占比 ≥ 阈值即为单核心）</div>
          <div style="display:flex;flex-wrap:wrap;gap:12px 24px;margin-bottom:16px">
            <div v-for="major in RANKABLE_MAJOR_KEYS" :key="major" style="display:flex;align-items:center;gap:8px">
              <span :class="`al-supplement-major-dot is-${major}`" style="flex-shrink:0"></span>
              <span style="color:#374151;font-size:13px;min-width:72px">{{ MAJOR_LABEL_MAP[major] }}</span>
              <el-input-number
                v-model="aiSettingsForm[`classify_${major}_threshold_pct`]"
                :min="1" :max="100" :step="5" :precision="0"
                style="width:120px"
              />
              <span style="color:#6b7280;font-size:12px">%</span>
            </div>
          </div>
          <el-form-item label="双核心合计阈值">
            <el-input-number v-model="aiSettingsForm.classify_dual_combined_threshold_pct" :min="1" :max="100" :step="5" :precision="0" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">% &nbsp;Top1+Top2 大类占比合计 ≥ 此值（且均未达单核心阈值）判为双核心</span>
          </el-form-item>
        </div>

        <!-- 账号分级判定规则 -->
        <div class="ai-cfg-section">
          <div class="ai-cfg-section-header">
            <span class="ai-cfg-tag">账号分级判定规则</span>
            <span class="ai-cfg-desc">
              满足条件 → 常规号；不满足 → 实验号；正式号永远保持。每天北京时间 09:00 自动评估并按区间从常规号随机扩量正式号。
            </span>
          </div>
          <el-form-item label="最近 N 条视频">
            <el-input-number v-model="aiSettingsForm.tier_video_sample_count" :min="1" :max="50" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">取最近 N 条已发布视频用于均播计算</span>
          </el-form-item>
          <el-form-item label="平均播放量阈值">
            <el-input-number v-model="aiSettingsForm.tier_avg_play_threshold" :min="0" :max="1000000" :step="50" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">N 条均播 ≥ 此值才能升常规号</span>
          </el-form-item>
          <el-form-item label="最近 N 天">
            <el-input-number v-model="aiSettingsForm.tier_activity_days" :min="1" :max="60" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">活跃度时间窗（天）</span>
          </el-form-item>
          <el-form-item label="最少发视频数">
            <el-input-number v-model="aiSettingsForm.tier_min_video_count" :min="1" :max="100" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">该窗口内已完成发布数 ≥ 此值才能升常规号</span>
          </el-form-item>
          <el-form-item label="正式号每日新增比例">
            <div style="display:flex;align-items:center;gap:8px">
              <el-input-number v-model="aiSettingsForm.tier_daily_formal_growth_min_rate" :min="0" :max="1" :step="0.01" :precision="4" style="width: 160px" />
              <span style="color:#6b7280">~</span>
              <el-input-number v-model="aiSettingsForm.tier_daily_formal_growth_max_rate" :min="0" :max="1" :step="0.01" :precision="4" style="width: 160px" />
              <span style="color:#6b7280;font-size:13px">× 当前正式号数（每日扩量区间）</span>
            </div>
          </el-form-item>
          <el-form-item label="子任务成功率样本 N">
            <el-input-number v-model="aiSettingsForm.sub_task_success_sample_size" :min="1" :max="200" style="width: 160px" />
            <span style="margin-left:8px;color:#6b7280;font-size:13px">
              账号列表展示「成功率」时取最近 N 条子任务；分子 = 暂存 + 队列中 + 已发布，分母 = 暂存 + 待决策 + 决策未通过 + 队列中 + 已发布
            </span>
          </el-form-item>
          <el-form-item label="">
            <el-button
              type="warning"
              plain
              :loading="tierEvalPreviewLoading"
              @click="openTierEvalPreview"
            >
              重新判定账号状态（实验号 ↔ 常规号）
            </el-button>
            <div style="margin-top:6px;color:#9ca3af;font-size:12px">
              修改上方阈值后保存，再点击此按钮预览会变动的账号；二次确认后才落库。正式号永不被改动。
            </div>
          </el-form-item>
        </div>

      </div>
      <template #footer>
        <el-button @click="showAISettingsDialog = false">取消</el-button>
        <el-button type="primary" :loading="aiSettingsSaving" @click="saveAISettings">保存配置</el-button>
      </template>
    </el-dialog>

    <!-- 账号分级重判预览弹窗 -->
    <el-dialog
      v-model="showTierEvalPreviewDialog"
      title="账号分级 · 重新判定预览"
      width="780px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-loading="tierEvalPreviewLoading" class="tier-eval-body">
        <div class="tier-eval-summary">
          <span><b>{{ tierEvalChanges.length }}</b> 个账号将变动</span>
          <span class="tier-eval-summary-sep"></span>
          <span class="tier-eval-promote">实验号 → 常规号：{{ tierEvalSummary.promote_to_dev || 0 }}</span>
          <span class="tier-eval-summary-sep"></span>
          <span class="tier-eval-demote">常规号 → 实验号：{{ tierEvalSummary.demote_to_test || 0 }}</span>
        </div>
        <div v-if="tierEvalChanges.length === 0" class="tier-eval-empty">
          按当前阈值评估后，没有账号需要变动。
        </div>
        <div v-else class="tier-eval-list">
          <div
            v-for="c in tierEvalChanges"
            :key="c.account_id"
            class="tier-eval-item"
            :class="c.target_tier === 'dev' ? 'is-promote' : 'is-demote'"
          >
            <div class="tier-eval-name">{{ c.account_name }}</div>
            <div class="tier-eval-tier-flow">
              <span class="tier-chip" :class="`tier-chip-${c.current_tier}`">{{ tierLabel(c.current_tier) }}</span>
              <span class="tier-eval-arrow">→</span>
              <span class="tier-chip" :class="`tier-chip-${c.target_tier}`">{{ tierLabel(c.target_tier) }}</span>
            </div>
            <div class="tier-eval-reason">
              样本 {{ c.reason?.video_count_in_sample ?? 0 }}/{{ c.reason?.threshold?.video_sample_count ?? 0 }}
              · 均播 {{ c.reason?.avg_views ?? 0 }}（阈值 {{ c.reason?.threshold?.avg_play_threshold ?? 0 }}）
              · 近 {{ c.reason?.threshold?.activity_days ?? 0 }} 天 {{ c.reason?.recent_count ?? 0 }} 条（最少 {{ c.reason?.threshold?.min_video_count ?? 0 }}）
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showTierEvalPreviewDialog = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="tierEvalChanges.length === 0"
          :loading="tierEvalApplying"
          @click="applyTierEvalChanges"
        >
          确认应用（{{ tierEvalChanges.length }}）
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showBulkContinueDialog"
      title="一键继续 AI 生成"
      width="520px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="al-bulk-resume-body">
        <div class="al-bulk-resume-hint">
          选择从哪个阶段开始继续。
          <template v-if="selectedMap.size > 0">
            <b>操作范围：已选 {{ selectedMap.size }} 个账号</b>。
          </template>
          <template v-else>
            该操作会对当前账号下所有未完成、且不处于"待选照片"的 AI 博主统一生效。
          </template>
        </div>
        <el-form-item label="继续阶段">
          <el-select v-model="bulkResumeStage" style="width: 100%">
            <el-option label="按当前数据库阶段断点续跑" value="current" />
            <el-option label="从照片生成开始" value="photo_generating" />
            <el-option label="从视频理解开始" value="video_analyzing" />
            <el-option label="从头像生成开始" value="avatar_generating" />
            <el-option label="从名称生成开始" value="name_generating" />
          </el-select>
        </el-form-item>
        <div class="al-bulk-resume-desc">
          <template v-if="bulkResumeStage === 'photo_generating'">
            清空照片候选、头像、名称，重跑「照片生成 → 待选照片 → 视频理解 → 头像生成 → 名称生成」。需要再次手动选照片。
          </template>
          <template v-else-if="bulkResumeStage === 'video_analyzing'">
            保留已选照片，重跑「视频理解 → 头像生成 → 名称生成」。
          </template>
          <template v-else-if="bulkResumeStage === 'avatar_generating'">
            保留已选照片和视频理解结果，重跑「头像生成 → 名称生成」。
          </template>
          <template v-else-if="bulkResumeStage === 'name_generating'">
            保留照片、视频理解结果和头像，仅重新生成名称。
          </template>
          <template v-else>
            会按照数据库里当前记录的阶段断点续跑（处于"待选照片"的账号会被跳过，需要先去选照片）。
          </template>
        </div>
      </div>
      <template #footer>
        <el-button @click="showBulkContinueDialog = false">取消</el-button>
        <el-button type="primary" :loading="bulkRestarting" @click="handleBulkContinueAIGeneration">确认继续</el-button>
      </template>
    </el-dialog>

    <!-- 批量定时发布配置 dialog -->
    <el-dialog
      v-model="showBulkScheduleDialog"
      title="批量定时发布配置"
      width="520px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="al-bulk-resume-hint" style="margin-bottom:16px">
        <template v-if="selectedMap.size > 0">
          以下设置将强制启用并覆盖已选 <strong>{{ selectedMap.size }}</strong> 个账号的定时发布配置。
        </template>
        <template v-else>
          以下设置将强制启用并覆盖当前筛选结果 <strong>{{ total }}</strong> 个账号的定时发布配置。
        </template>
      </div>
      <el-form :model="bulkScheduleForm" label-width="120px" label-position="left">
        <el-form-item label="快捷规则">
          <div class="al-schedule-presets">
            <button
              v-for="p in CRON_PRESETS"
              :key="p.cron"
              type="button"
              class="al-preset-btn"
              :class="{ active: bulkScheduleForm.publish_cron === p.cron }"
              @click="bulkScheduleForm.publish_cron = p.cron"
            >{{ p.label }}</button>
          </div>
        </el-form-item>
        <el-form-item label="Cron 表达式">
          <el-input v-model="bulkScheduleForm.publish_cron" placeholder="0 10 * * *" style="font-family:monospace" />
          <div class="al-schedule-hint">格式：分 时 日 月 周（北京时间）。例：每天10点 = 0 10 * * *</div>
        </el-form-item>
        <el-form-item label="随机延迟">
          <el-input-number v-model="bulkScheduleForm.publish_window_minutes" :min="0" :max="720" :step="15" style="width:130px" />
          <span class="al-schedule-unit">分钟（0 = 精确时间）</span>
        </el-form-item>
        <el-form-item label="每次发布数量">
          <el-input-number v-model="bulkScheduleForm.publish_count" :min="1" :max="20" style="width:100px" />
          <span class="al-schedule-unit">个视频</span>
        </el-form-item>
        <el-form-item label="规则预览">
          <div class="al-schedule-preview">{{ bulkSchedulePreview }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showBulkScheduleDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingBulkSchedule" @click="handleBulkSchedule">{{ selectedMap.size > 0 ? `应用到已选 ${selectedMap.size} 个账号` : '应用到全部账号' }}</el-button>
      </template>
    </el-dialog>

    <!-- 一键生成配置 dialog -->
    <el-dialog
      v-model="showBulkGenDialog"
      title="一键生成"
      width="480px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="al-supplement-body">
        <!-- 操作范围提示 -->
        <div class="al-supplement-scope">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span v-if="selectedMap.size > 0">将为已选 <b>{{ selectedMap.size }}</b> 个账号创建生成任务</span>
          <span v-else>将为全部 <b>{{ total }}</b> 个账号创建生成任务</span>
        </div>
        <!-- 模式选择 -->
        <div class="al-supplement-types">
          <button
            class="al-supplement-type-card"
            :class="{ active: bulkGenForm.mode === 'unused' }"
            @click="bulkGenForm.mode = 'unused'"
          >
            <div class="al-supplement-type-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
            </div>
            <div class="al-supplement-type-name">未用过 / 可重复</div>
            <div class="al-supplement-type-desc">选择未使用模板；可重复模板即使已使用也会进入候选</div>
          </button>
          <button
            class="al-supplement-type-card"
            :class="{ active: bulkGenForm.mode === 'used' }"
            @click="bulkGenForm.mode = 'used'"
          >
            <div class="al-supplement-type-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </div>
            <div class="al-supplement-type-name">用过的</div>
            <div class="al-supplement-type-desc">从已使用过的模板中随机抽取 N 个</div>
          </button>
        </div>
        <!-- 补充策略二选一 -->
        <div class="al-supplement-config">
          <div class="al-supplement-config-label">补充策略</div>
          <div class="al-supplement-config-row" style="gap:18px;flex-wrap:wrap;justify-content:flex-start">
            <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer">
              <input type="radio" value="count" v-model="bulkGenForm.fill_mode" />
              <span>补充 X 个</span>
            </label>
            <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer">
              <input type="radio" value="target_total" v-model="bulkGenForm.fill_mode" />
              <span>补充到 X 个（含当前 queued 任务）</span>
            </label>
          </div>
        </div>
        <!-- 数量配置 -->
        <div class="al-supplement-config">
          <div class="al-supplement-config-label">
            {{ bulkGenForm.fill_mode === 'target_total' ? '每账号补到 N 个 queued 任务' : '每账号新增模板数（0 = 不限制）' }}
          </div>
          <div class="al-supplement-config-row">
            <button class="al-supplement-minus" @click="bulkGenForm.limit = Math.max(bulkGenForm.fill_mode === 'target_total' ? 1 : 0, bulkGenForm.limit - 1)">−</button>
            <span class="al-supplement-num">{{ bulkGenForm.limit }}</span>
            <button class="al-supplement-plus" @click="bulkGenForm.limit = Math.min(99, bulkGenForm.limit + 1)">+</button>
            <span class="al-supplement-num-hint">个</span>
          </div>
        </div>
        <!-- 子任务数量配置 -->
        <div class="al-supplement-config">
          <div class="al-supplement-config-label">每个任务生成子任务数</div>
          <div class="al-supplement-config-row">
            <button class="al-supplement-minus" @click="bulkGenForm.subtaskCount = Math.max(1, bulkGenForm.subtaskCount - 1)">−</button>
            <span class="al-supplement-num">{{ bulkGenForm.subtaskCount }}</span>
            <button class="al-supplement-plus" @click="bulkGenForm.subtaskCount = Math.min(20, bulkGenForm.subtaskCount + 1)">+</button>
            <span class="al-supplement-num-hint">个</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showBulkGenDialog = false">取消</el-button>
        <el-button type="primary" :loading="bulkVideoGenerating" @click="startBulkVideoGenerate">开始生成</el-button>
      </template>
    </el-dialog>

    <!-- 定时一键生成配置 dialog -->
    <el-dialog
      v-model="showScheduledGenerationDialog"
      title="定时一键生成"
      width="620px"
      :close-on-click-modal="false"
    >
      <div class="al-supplement-body">
        <div class="al-supplement-scope">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span>仅处理已绑定 TikTok 博主的 AI 博主</span>
        </div>
        <div class="al-supplement-config">
          <div class="al-supplement-config-row" style="justify-content:space-between">
            <div class="al-supplement-config-label">启用定时生成</div>
            <el-switch v-model="scheduledGenerationForm.enabled" />
          </div>
        </div>
        <template v-if="scheduledGenerationForm.enabled">
          <div class="al-supplement-config">
            <div class="al-supplement-config-label">北京时间 Cron</div>
            <div class="al-schedule-presets" style="margin-bottom:8px">
              <button
                v-for="preset in scheduledGenerationPresets"
                :key="preset.cron"
                type="button"
                :class="{ active: scheduledGenerationForm.cron === preset.cron }"
                @click="scheduledGenerationForm.cron = preset.cron"
              >
                {{ preset.label }}
              </button>
            </div>
            <el-input v-model="scheduledGenerationForm.cron" placeholder="0 10 * * *" style="font-family:monospace" />
          </div>
          <div class="al-supplement-config">
            <div class="al-supplement-config-label">库存与筛选</div>
            <div class="al-supplement-filters">
              <div class="al-supplement-filter-row">
                <label>查找 N 天前</label>
                <el-input-number v-model="scheduledGenerationForm.lookbackDays" :min="1" :max="30" controls-position="right" style="width:160px" />
              </div>
              <div class="al-supplement-filter-row">
                <label>目标未发布库存</label>
                <el-input-number v-model="scheduledGenerationForm.targetUnpublishedCount" :min="1" :max="99" controls-position="right" style="width:160px" />
              </div>
              <div class="al-supplement-filter-row">
                <label>每任务视频数</label>
                <el-input-number v-model="scheduledGenerationForm.subtaskCount" :min="1" :max="20" controls-position="right" style="width:160px" />
              </div>
              <div class="al-supplement-filter-row">
                <label>未使用回看（月）</label>
                <el-input-number v-model="scheduledGenerationForm.unusedTemplateMonths" :min="1" :max="24" controls-position="right" style="width:160px" />
              </div>
              <div class="al-supplement-filter-row">
                <label>已使用冷却（天）</label>
                <el-input-number v-model="scheduledGenerationForm.usedTemplateCooldownDays" :min="0" :max="365" controls-position="right" style="width:160px" />
              </div>
            </div>
          </div>
          <div class="al-supplement-config">
            <div class="al-supplement-config-label">大类重提规则</div>
            <div class="al-scheduled-rule-list">
              <div v-for="major in RANKABLE_MAJOR_KEYS" :key="major" class="al-scheduled-rule-row">
                <div class="al-scheduled-rule-name">
                  <span :class="`al-supplement-major-dot is-${major}`"></span>
                  <span>{{ MAJOR_LABEL_MAP[major] }}</span>
                </div>
                <el-switch v-model="scheduledGenerationForm.categoryRules[major].enabled" />
                <div class="al-scheduled-rule-field">
                  <span>播放量 &gt;</span>
                  <el-input-number v-model="scheduledGenerationForm.categoryRules[major].min_views" :min="0" :step="1000" controls-position="right" style="width:140px" />
                </div>
                <div class="al-scheduled-rule-field">
                  <span>重提</span>
                  <el-input-number v-model="scheduledGenerationForm.categoryRules[major].repeat_count" :min="1" :max="20" controls-position="right" style="width:110px" />
                  <span>次</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="showScheduledGenerationDialog = false">取消</el-button>
        <el-button type="primary" :loading="scheduledGenerationSaving" @click="saveScheduledGenerationConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 补充模板弹窗 -->
    <el-dialog
      v-model="showSupplementDialog"
      title="补充模板"
      width="480px"
      :close-on-click-modal="false"
    >
      <div class="al-supplement-body">
        <!-- 操作范围提示 -->
        <div class="al-supplement-scope">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span v-if="selectedMap.size > 0">将为已选 <b>{{ selectedMap.size }}</b> 个账号补充模板</span>
          <span v-else>将为全部 <b>{{ total }}</b> 个账号补充模板</span>
        </div>
        <!-- 类型选择 -->
        <div class="al-supplement-types">
          <button
            class="al-supplement-type-card"
            :class="{ active: supplementForm.templateType === 'shared' }"
            @click="supplementForm.templateType = 'shared'"
          >
            <div class="al-supplement-type-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
            </div>
            <div class="al-supplement-type-name">补充共享</div>
            <div class="al-supplement-type-desc">以标签名搜索视频</div>
          </button>
          <button
            class="al-supplement-type-card"
            :class="{ active: supplementForm.templateType === 'exclusive' }"
            @click="supplementForm.templateType = 'exclusive'"
          >
            <div class="al-supplement-type-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            </div>
            <div class="al-supplement-type-name">补充人设</div>
            <div class="al-supplement-type-desc">搜索绑定博主的视频</div>
          </button>
          <button
            class="al-supplement-type-card"
            :class="{ active: supplementForm.templateType === 'auto' }"
            @click="supplementForm.templateType = 'auto'"
          >
            <div class="al-supplement-type-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2a10 10 0 0 1 10 10"/><polyline points="22 2 22 8 16 8"/><path d="M12 22a10 10 0 0 1-10-10"/><polyline points="2 22 2 16 8 16"/></svg>
            </div>
            <div class="al-supplement-type-name">自动补充</div>
            <div class="al-supplement-type-desc">按分类类型过滤，仅核心类别入库</div>
          </button>
        </div>
        <!-- 自动补充说明 -->
        <div v-if="supplementForm.templateType === 'auto'" class="al-auto-supplement-tip">
          <div class="al-auto-supplement-tip-row">
            <span class="ac-classify-badge is-single" style="font-size:11px">单核心</span>
            <span>搜索绑定博主视频，分类后只有 <b>Top1 类别</b> 入库</span>
          </div>
          <div class="al-auto-supplement-tip-row">
            <span class="ac-classify-badge is-dual" style="font-size:11px">双核心</span>
            <span>搜索绑定博主视频，分类后 <b>Top1 + Top2 类别</b> 均可入库</span>
          </div>
          <div class="al-auto-supplement-tip-row al-auto-supplement-tip-warn">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            未分类、混乱或样本不足的账号将跳过
          </div>
        </div>
        <div v-if="supplementForm.templateType === 'exclusive'" class="al-supplement-config">
          <div class="al-supplement-config-label">
            视频分类
            <span class="al-supplement-filter-hint">不选择 = 不启用分类过滤</span>
          </div>
          <div class="al-supplement-category-groups">
            <div v-for="major in MAJOR_KEYS" :key="major" class="al-supplement-category-group">
              <div class="al-supplement-category-major">
                <span :class="`al-supplement-major-dot is-${major}`"></span>
                <span>{{ MAJOR_LABEL_MAP[major] }}</span>
              </div>
              <div class="al-cat-filter-pills">
                <button
                  v-for="cat in CATEGORY_OPTIONS.filter(c => c.major === major)"
                  :key="cat.key"
                  type="button"
                  class="al-cat-pill"
                  :class="[`is-${cat.major}`, { active: supplementForm.categoryKeys.includes(cat.key) }]"
                  @click="toggleSupplementCategory(cat.key)"
                >
                  {{ cat.label }}
                </button>
              </div>
            </div>
          </div>
        </div>
        <!-- 数量配置 -->
        <div class="al-supplement-config">
          <div class="al-supplement-config-label">目标未使用模板数量（每个博主）</div>
          <div class="al-supplement-config-row">
            <button class="al-supplement-minus" @click="supplementForm.targetUnusedTemplateCount = Math.max(1, supplementForm.targetUnusedTemplateCount - 1)">−</button>
            <span class="al-supplement-num">{{ supplementForm.targetUnusedTemplateCount }}</span>
            <button class="al-supplement-plus" @click="supplementForm.targetUnusedTemplateCount = Math.min(50, supplementForm.targetUnusedTemplateCount + 1)">+</button>
            <span class="al-supplement-num-hint">个</span>
          </div>
        </div>

        <!-- 过滤条件（仅 exclusive / auto；shared 走内部默认配置） -->
        <div v-if="supplementForm.templateType !== 'shared'" class="al-supplement-config">
          <div class="al-supplement-config-label">过滤条件（留空 = 不限）</div>
          <div class="al-supplement-filters">
            <div class="al-supplement-filter-row">
              <label>最少播放量</label>
              <el-input-number
                v-model="supplementForm.minViewCount"
                :min="0"
                :step="1000"
                controls-position="right"
                placeholder="不限"
                style="width:180px"
              />
              <span class="al-supplement-filter-hint">view_count ≥ 该值才采集</span>
            </div>
            <div class="al-supplement-filter-row">
              <label>发布日期之后</label>
              <el-date-picker
                v-model="supplementForm.publishedAfter"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="不限"
                style="width:180px"
              />
              <span class="al-supplement-filter-hint">仅该日期及之后发布的视频</span>
            </div>
            <div class="al-supplement-filter-row">
              <label>时长上限（秒）</label>
              <el-input-number
                v-model="supplementForm.maxDurationSeconds"
                :min="0"
                :step="5"
                controls-position="right"
                placeholder="不限"
                style="width:180px"
              />
              <span class="al-supplement-filter-hint">视频时长 ≤ 该值</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showSupplementDialog = false">取消</el-button>
        <el-button type="primary" :loading="supplementing" @click="handleSupplement">开始补充</el-button>
      </template>
    </el-dialog>

    <!-- 定时补充模板弹窗 -->
    <el-dialog
      v-model="showSupplementScheduleDialog"
      title="定时补充模板"
      width="520px"
      :close-on-click-modal="false"
    >
      <div class="al-supplement-body">
        <div class="al-supplement-scope">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span>仅处理已绑定 TikTok 博主的 AI 博主</span>
        </div>
        <div class="al-supplement-config">
          <div class="al-supplement-config-row" style="justify-content:space-between">
            <div class="al-supplement-config-label">启用定时补充</div>
            <el-switch v-model="supplementScheduleForm.enabled" />
          </div>
        </div>
        <template v-if="supplementScheduleForm.enabled">
          <div class="al-supplement-config">
            <div class="al-supplement-config-label">北京时间 Cron</div>
            <div class="al-schedule-presets" style="margin-bottom:8px">
              <button
                v-for="preset in supplementSchedulePresets"
                :key="preset.cron"
                type="button"
                :class="{ active: supplementScheduleForm.cron === preset.cron }"
                @click="supplementScheduleForm.cron = preset.cron"
              >
                {{ preset.label }}
              </button>
            </div>
            <el-input v-model="supplementScheduleForm.cron" placeholder="0 10 * * *" style="font-family:monospace" />
          </div>
          <div class="al-supplement-config">
            <div class="al-supplement-config-label">
              人设补充视频分类
              <span class="al-supplement-filter-hint">不选择 = 不启用分类过滤</span>
            </div>
            <div class="al-supplement-category-groups">
              <div v-for="major in MAJOR_KEYS" :key="major" class="al-supplement-category-group">
                <div class="al-supplement-category-major">
                  <span :class="`al-supplement-major-dot is-${major}`"></span>
                  <span>{{ MAJOR_LABEL_MAP[major] }}</span>
                </div>
                <div class="al-cat-filter-pills">
                  <button
                    v-for="cat in CATEGORY_OPTIONS.filter(c => c.major === major)"
                    :key="cat.key"
                    type="button"
                    class="al-cat-pill"
                    :class="[`is-${cat.major}`, { active: supplementScheduleForm.categoryKeys.includes(cat.key) }]"
                    @click="toggleSupplementScheduleCategory(cat.key)"
                  >
                    {{ cat.label }}
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div class="al-supplement-config">
            <div class="al-supplement-config-label">目标未使用模板数量（每个博主）</div>
            <div class="al-supplement-config-row">
              <button class="al-supplement-minus" @click="supplementScheduleForm.targetUnusedTemplateCount = Math.max(1, supplementScheduleForm.targetUnusedTemplateCount - 1)">−</button>
              <span class="al-supplement-num">{{ supplementScheduleForm.targetUnusedTemplateCount }}</span>
              <button class="al-supplement-plus" @click="supplementScheduleForm.targetUnusedTemplateCount = Math.min(50, supplementScheduleForm.targetUnusedTemplateCount + 1)">+</button>
              <span class="al-supplement-num-hint">个</span>
            </div>
          </div>
          <div class="al-supplement-config">
            <div class="al-supplement-config-label">过滤条件（留空 = 不限）</div>
            <div class="al-supplement-filters">
              <div class="al-supplement-filter-row">
                <label>最少播放量</label>
                <el-input-number v-model="supplementScheduleForm.minViewCount" :min="0" :step="1000" controls-position="right" placeholder="不限" style="width:180px" />
                <span class="al-supplement-filter-hint">view_count ≥ 该值才采集</span>
              </div>
              <div class="al-supplement-filter-row">
                <label>发布日期之后</label>
                <el-date-picker v-model="supplementScheduleForm.publishedAfter" type="date" value-format="YYYY-MM-DD" placeholder="不限" style="width:180px" />
                <span class="al-supplement-filter-hint">仅该日期及之后发布的视频</span>
              </div>
              <div class="al-supplement-filter-row">
                <label>时长上限（秒）</label>
                <el-input-number v-model="supplementScheduleForm.maxDurationSeconds" :min="0" :step="5" controls-position="right" placeholder="不限" style="width:180px" />
                <span class="al-supplement-filter-hint">视频时长 ≤ 该值</span>
              </div>
            </div>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="showSupplementScheduleDialog = false">取消</el-button>
        <el-button type="primary" :loading="supplementScheduleSaving" @click="saveSupplementSchedule">保存</el-button>
      </template>
    </el-dialog>

    <!-- 视频分类确认弹窗 -->
    <el-dialog
      v-model="showClassifyConfirmDialog"
      title="视频分类"
      width="420px"
      :close-on-click-modal="false"
    >
      <div class="al-supplement-body">
        <div class="al-supplement-scope">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span v-if="classifyConfirmMode === 'single' && classificationAccount">
            将对账号 <b>{{ classificationAccount.account_name }}</b> 下的视频进行分类
          </span>
          <span v-else-if="selectedMap.size > 0">
            将为已选 <b>{{ selectedMap.size }}</b> 个账号进行视频分类
          </span>
          <span v-else>
            将为全部 <b>{{ total }}</b> 个账号进行视频分类
          </span>
        </div>
        <div class="al-classify-confirm-option">
          <label class="al-classify-force-label">
            <input type="checkbox" v-model="classifyForce" />
            <span>重新分类已分类的视频</span>
          </label>
          <div class="al-classify-force-hint">勾选后，已成功分类的视频也会重新调用 Gemini 分类</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showClassifyConfirmDialog = false">取消</el-button>
        <el-button type="primary" :loading="classificationStarting || bulkClassifying" @click="confirmClassify">开始分类</el-button>
      </template>
    </el-dialog>

    <!-- 视频分类弹窗 -->
    <!-- 频道数据分析弹窗 -->
    <el-dialog
      v-model="showAnalyticsDialog"
      :title="analyticsAccount ? `频道数据 · ${analyticsAccount.account_name}` : '频道数据'"
      width="860px"
      :close-on-click-modal="false"
      destroy-on-close
      @close="closeAnalyticsDialog"
    >
      <div class="ana-body">
        <!-- 平台切换 + 日期选择 -->
        <div class="ana-toolbar">
          <div class="ana-platform-tabs">
            <button
              v-for="p in analyticsPlatforms"
              :key="p"
              class="ana-tab"
              :class="{ active: analyticsActivePlatform === p }"
              @click="switchAnalyticsPlatform(p)"
            >{{ p }}</button>
          </div>
          <div class="ana-date-range">
            <el-date-picker
              v-model="analyticsDateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              :clearable="false"
              size="small"
              style="width:240px"
              @change="loadAnalyticsData"
            />
          </div>
        </div>

        <!-- 加载 / 无数据 / 无绑定 -->
        <div v-if="analyticsLoading" class="ana-loading">加载中...</div>
        <div v-else-if="analyticsError" class="ana-error">{{ analyticsError }}</div>
        <div v-else-if="!analyticsData" class="ana-empty">请选择平台和日期范围</div>
        <template v-else>
          <!-- 指标卡 -->
          <div class="ana-metrics">
            <div class="ana-metric-card">
              <div class="ana-metric-label">Link 总点击</div>
              <div class="ana-metric-value">{{ analyticsData.total_link_clicks.toLocaleString() }}</div>
            </div>
            <div class="ana-metric-card">
              <div class="ana-metric-label">视频总 Views</div>
              <div class="ana-metric-value">{{ analyticsData.total_video_views.toLocaleString() }}</div>
            </div>
            <div class="ana-metric-card">
              <div class="ana-metric-label">Link 总转化率</div>
              <div class="ana-metric-value">{{ analyticsLinkTotalConversion }}</div>
            </div>
          </div>

          <!-- 5 条折线图 -->
          <div class="ana-charts">
            <div class="ana-chart-row">
              <div class="ana-chart-title">当日账号总 Views</div>
              <div ref="anaChart1Ref" class="ana-chart-canvas"></div>
            </div>
            <div class="ana-chart-row">
              <div class="ana-chart-title">Link 总点击次数（累计）</div>
              <div ref="anaChart2Ref" class="ana-chart-canvas"></div>
            </div>
            <div class="ana-chart-row">
              <div class="ana-chart-title">Link 当日点击次数</div>
              <div ref="anaChart3Ref" class="ana-chart-canvas"></div>
            </div>
            <div class="ana-chart-row">
              <div class="ana-chart-title">Link 日转化率（当日点击 / 当日 Views）</div>
              <div ref="anaChart4Ref" class="ana-chart-canvas"></div>
            </div>
            <div class="ana-chart-row">
              <div class="ana-chart-title">Link 总转化率（累计点击 / 视频总 Views）</div>
              <div ref="anaChart5Ref" class="ana-chart-canvas"></div>
            </div>
          </div>
        </template>
      </div>
    </el-dialog>

    <el-dialog
      v-model="showClassificationDialog"
      :title="classificationAccount ? `视频分类 · ${classificationAccount.account_name}` : '视频分类'"
      width="780px"
      :close-on-click-modal="false"
      destroy-on-close
      @close="closeClassificationDialog"
    >
      <div v-loading="classificationLoading" class="vc-body">
        <!-- 顶部总览 -->
        <div class="vc-overview">
          <div class="vc-overview-left">
            <div class="vc-overview-status">
              <span class="vc-status-dot" :class="`is-${classificationView?.summary?.classification_status || 'idle'}`"></span>
              <span>{{ classificationView?.summary?.classification_status === 'running' ? '分类中' : '空闲' }}</span>
            </div>
            <div class="vc-overview-title">
              <template v-if="classificationSummary?.type === 'single'">
                <span class="vc-type-tag is-single">单核心</span>
                <span class="vc-type-name">{{ majorLabel(classificationSummary.primary) }}</span>
              </template>
              <template v-else-if="classificationSummary?.type === 'dual'">
                <span class="vc-type-tag is-dual">双核心</span>
                <span class="vc-type-name">{{ majorLabel(classificationSummary.primary) }} + {{ majorLabel(classificationSummary.secondary) }}</span>
              </template>
              <template v-else-if="classificationSummary?.type === 'chaos'">
                <span class="vc-type-tag is-chaos">混乱</span>
              </template>
              <template v-else-if="classificationSummary?.type === 'insufficient'">
                <span class="vc-type-tag is-insufficient">样本不足</span>
                <span style="color:#9ca3af;font-size:12px">至少需要 3 个成功分类</span>
              </template>
              <template v-else>
                <span class="vc-type-tag is-none">未分类</span>
              </template>
            </div>
            <div class="vc-overview-counts" v-if="classificationSummary">
              共 {{ classificationSummary.total }}，
              <span style="color:#16a34a">成功 {{ classificationSummary.success }}</span>，
              <span v-if="classificationSummary.processing">处理中 {{ classificationSummary.processing }}，</span>
              <span v-if="classificationSummary.pending">排队 {{ classificationSummary.pending }}，</span>
              <span v-if="classificationSummary.failed" style="color:#dc2626">失败 {{ classificationSummary.failed }}</span>
            </div>
          </div>
          <div class="vc-overview-right">
            <el-button
              type="primary"
              :loading="classificationStarting"
              :disabled="classificationView?.summary?.classification_status === 'running'"
              @click="openClassifyConfirm('single')"
            >{{ classificationView?.summary?.classification_status === 'running' ? '分类中...' : '开始分类' }}</el-button>
            <el-button
              v-if="classificationSummary?.failed"
              :loading="classificationRetrying"
              @click="handleRetryFailed"
            >重试失败 ({{ classificationSummary.failed }})</el-button>
          </div>
        </div>

        <!-- 图表：大类饼图 + 14 细分类柱状图 -->
        <div v-if="classificationSummary && classificationSummary.success > 0" class="vc-charts">
          <div ref="vcMajorChartRef" class="vc-chart vc-chart-major"></div>
          <div ref="vcCategoryChartRef" class="vc-chart vc-chart-category"></div>
        </div>

        <!-- 视频分组 -->
        <div class="vc-groups">
          <div v-for="group in classificationGroups" :key="group.key" v-show="group.items.length > 0" class="vc-group">
            <div class="vc-group-header">
              <span class="vc-group-name" :class="`is-${group.key}`">{{ group.label }}</span>
              <span class="vc-group-count">{{ group.items.length }}</span>
            </div>
            <div class="vc-group-list">
              <div v-for="v in group.items" :key="v.video_source_id" class="vc-item" :class="`is-${v.status}`">
                <div class="vc-item-thumb" @click="(v.local_video_url || v.local_gcs_video_url) && openVcFullscreen(v)">
                  <video
                    v-if="v.local_video_url || v.local_gcs_video_url"
                    :src="v.local_video_url || v.local_gcs_video_url"
                    preload="metadata"
                    playsinline
                    class="vc-thumb-video"
                  />
                  <div class="vc-item-thumb-expand" v-if="v.local_video_url || v.local_gcs_video_url">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
                  </div>
                  <div v-if="!(v.local_video_url || v.local_gcs_video_url)" class="vc-item-thumb-placeholder">无视频</div>
                </div>
                <div class="vc-item-info">
                  <div class="vc-item-title">{{ v.video_title || '(无标题)' }}</div>
                  <div class="vc-item-meta">
                    <span v-if="v.blogger_name">@{{ v.blogger_name }}</span>
                  </div>
                  <div v-if="v.status === 'success'" class="vc-item-cat">
                    <span class="vc-major-tag" :class="`is-${v.major_category}`">{{ majorLabel(v.major_category) }}</span>
                    <span class="vc-cat-label">{{ v.category_label }}</span>
                  </div>
                  <div v-else-if="v.status === 'failed'" class="vc-item-error" :title="v.error_message || ''">
                    失败：{{ v.error_message || '未知错误' }}
                  </div>
                  <div v-else-if="v.status === 'processing'" class="vc-item-status">分类中...</div>
                  <div v-else-if="v.status === 'pending'" class="vc-item-status">排队中</div>
                  <div v-else-if="v.status === 'no_local_video'" class="vc-item-status is-warn">无 local_video_url / local_gcs_video_url，跳过</div>
                  <div v-else class="vc-item-status is-muted">未开始</div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="classificationView && classificationView.videos.length === 0" class="vc-empty">
            该账号绑定的博主下还没有视频
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 人设打标确认 dialog -->
    <el-dialog
      v-model="showPersonaTagConfirmDialog"
      title="人设打标"
      width="420px"
      :close-on-click-modal="false"
    >
      <div class="al-supplement-body">
        <div class="al-supplement-scope">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span v-if="personaTagConfirmIds.length > 0">
            将为已选 <b>{{ personaTagConfirmIds.length }}</b> 个 AI 博主绑定的 TikTok 博主进行人设打标
          </span>
          <span v-else>
            将为全部 <b>{{ total }}</b> 个 AI 博主绑定的 TikTok 博主进行人设打标
          </span>
        </div>
        <div class="al-classify-confirm-option">
          <label class="al-classify-force-label">
            <input type="checkbox" v-model="personaTagForce" />
            <span>覆盖已有打标结果</span>
          </label>
          <div class="al-classify-force-hint">勾选后，已完成打标的博主也会清除旧结果重新打标</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showPersonaTagConfirmDialog = false">取消</el-button>
        <el-button type="primary" :loading="personaTagging" @click="confirmPersonaTagging">开始打标</el-button>
      </template>
    </el-dialog>

    <!-- 人设打标进度 dialog -->
    <el-dialog
      v-model="showTaggingProgressDialog"
      :title="taggingProgressBlogger ? `人设打标进度 · ${taggingProgressBlogger.blogger_name}` : '人设打标进度'"
      width="640px"
      :close-on-click-modal="true"
      destroy-on-close
      @close="closeTaggingProgressDialog"
    >
      <div v-loading="taggingProgressLoading" class="tp-body">
        <!-- 顶部总览 -->
        <div class="tp-overview">
          <div class="tp-overview-left">
            <div class="tp-overview-status">
              <span class="tp-status-dot" :class="`is-${taggingProgressData?.blogger_status || 'not_started'}`"></span>
              <span class="tp-status-label">{{ taggingStatusLabel(taggingProgressData?.blogger_status) }}</span>
            </div>
            <div class="tp-overview-counts" v-if="taggingProgressData?.summary">
              共 {{ taggingProgressData.summary.total }} 条视频
              <template v-if="taggingProgressData.summary.total">
                （至少需 {{ taggingProgressData.min_video_count }} 条）
              </template>
              <span style="color:#16a34a;margin-left:6px">✓ {{ taggingProgressData.summary.success }}</span>
              <span v-if="taggingProgressData.summary.running" style="color:#6366f1;margin-left:4px">⏳ 处理中 {{ taggingProgressData.summary.running }}</span>
              <span v-if="taggingProgressData.summary.pending" style="color:#ca8a04;margin-left:4px">排队 {{ taggingProgressData.summary.pending }}</span>
              <span v-if="taggingProgressData.summary.failed" style="color:#dc2626;margin-left:4px">✗ {{ taggingProgressData.summary.failed }}</span>
              <span v-if="taggingProgressData.summary.not_started" style="color:#94a3b8;margin-left:4px">未开始 {{ taggingProgressData.summary.not_started }}</span>
            </div>
            <!-- 进度条 -->
            <div v-if="taggingProgressData?.summary?.total" class="tp-progress-bar-wrap">
              <div class="tp-progress-bar">
                <div
                  class="tp-progress-fill tp-progress-fill--success"
                  :style="{ width: (taggingProgressData.summary.success / taggingProgressData.summary.total * 100).toFixed(1) + '%' }"
                ></div>
                <div
                  class="tp-progress-fill tp-progress-fill--running"
                  :style="{ width: ((taggingProgressData.summary.running + taggingProgressData.summary.pending) / taggingProgressData.summary.total * 100).toFixed(1) + '%' }"
                ></div>
                <div
                  class="tp-progress-fill tp-progress-fill--failed"
                  :style="{ width: (taggingProgressData.summary.failed / taggingProgressData.summary.total * 100).toFixed(1) + '%' }"
                ></div>
              </div>
              <span class="tp-progress-pct">{{ taggingProgressData.summary.total ? (((taggingProgressData.summary.success + taggingProgressData.summary.running) / taggingProgressData.summary.total) * 100).toFixed(0) : 0 }}%</span>
            </div>
          </div>
          <div class="tp-overview-right">
            <el-button
              type="primary"
              size="small"
              :loading="taggingProgressStarting"
              :disabled="taggingProgressData?.is_active"
              @click="handleRestartTagging"
            >
              {{ taggingProgressData?.is_active ? '打标中...' : (taggingProgressData?.blogger_status === 'success' ? '重新打标' : '开始打标') }}
            </el-button>
          </div>
        </div>

        <!-- 博主聚合步骤 -->
        <div class="tp-stage-bar">
          <!-- 第一步：视频打标 -->
          <div class="tp-stage" :class="videoStageClass">
            <span class="tp-stage-dot" :class="videoStageClass"></span>
            <div class="tp-stage-info">
              <span class="tp-stage-title">① 视频打标</span>
              <span class="tp-stage-desc" v-if="taggingProgressData?.summary">
                {{ taggingProgressData.summary.success }}/{{ taggingProgressData.summary.total }} 完成
                <span v-if="taggingProgressData.summary.failed" style="color:#dc2626">
                  · {{ taggingProgressData.summary.failed }} 失败
                </span>
              </span>
            </div>
          </div>

          <span class="tp-stage-arrow">→</span>

          <!-- 第二步：博主聚合 -->
          <div class="tp-stage" :class="aggregateStageClass">
            <span class="tp-stage-dot" :class="aggregateStageClass"></span>
            <div class="tp-stage-info">
              <span class="tp-stage-title">② 博主聚合</span>
              <span class="tp-stage-desc">{{ aggregateStageDesc }}</span>
            </div>
          </div>

          <span class="tp-stage-arrow">→</span>

          <!-- 第三步：写回 -->
          <div class="tp-stage" :class="writebackStageClass">
            <span class="tp-stage-dot" :class="writebackStageClass"></span>
            <div class="tp-stage-info">
              <span class="tp-stage-title">③ 写回博主</span>
              <span class="tp-stage-desc">{{ writebackStageDesc }}</span>
            </div>
          </div>
        </div>

        <!-- 博主聚合失败错误信息 -->
        <div v-if="taggingProgressData?.blogger_error" class="tp-error-banner">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          聚合失败：{{ taggingProgressData.blogger_error }}
        </div>

        <!-- 打标完整结果 -->
        <div v-if="taggingProgressData?.result" class="tp-result">
          <!-- 一句话总结 -->
          <div v-if="taggingProgressData.result.one_sentence_summary" class="tp-result-summary">
            <span class="tp-result-summary-icon">💬</span>
            <span>{{ taggingProgressData.result.one_sentence_summary }}</span>
          </div>

          <div class="tp-result-tags">
            <!-- ① persona_tags: 基础人口 -->
            <div class="tp-result-group" v-if="taggingProgressData.result.persona_tags?.basic_demographics">
              <span class="tp-result-group-label">基础人口</span>
              <div class="tp-result-chips">
                <span v-if="taggingProgressData.result.persona_tags.basic_demographics.gender_or_sexuality_presentation" class="tp-chip tp-chip--demo">{{ taggingProgressData.result.persona_tags.basic_demographics.gender_or_sexuality_presentation }}</span>
                <span v-if="taggingProgressData.result.persona_tags.basic_demographics.age_range" class="tp-chip tp-chip--demo">{{ taggingProgressData.result.persona_tags.basic_demographics.age_range }}</span>
                <span v-if="taggingProgressData.result.persona_tags.basic_demographics.visual_ethnicity" class="tp-chip tp-chip--demo">{{ taggingProgressData.result.persona_tags.basic_demographics.visual_ethnicity }}</span>
                <span v-if="taggingProgressData.result.persona_tags.basic_demographics.body_type" class="tp-chip tp-chip--demo">{{ taggingProgressData.result.persona_tags.basic_demographics.body_type }}</span>
                <span v-if="taggingProgressData.result.persona_tags.basic_demographics.height_impression && taggingProgressData.result.persona_tags.basic_demographics.height_impression !== '无明显'" class="tp-chip tp-chip--demo">{{ taggingProgressData.result.persona_tags.basic_demographics.height_impression }}</span>
                <template v-if="taggingProgressData.result.persona_tags.basic_demographics.special_body_parts?.length">
                  <span v-for="p in taggingProgressData.result.persona_tags.basic_demographics.special_body_parts.filter(x => x !== '无明显特殊 Body 部位')" :key="p" class="tp-chip tp-chip--demo">{{ p }}</span>
                </template>
              </div>
            </div>
            <!-- ① persona_tags: 消费层级 / 气质 / 社会身份 / 场合 -->
            <div class="tp-result-group" v-if="taggingProgressData.result.persona_tags">
              <span class="tp-result-group-label">人设标签</span>
              <div class="tp-result-chips">
                <span v-if="taggingProgressData.result.persona_tags.consumption_tier" class="tp-chip tp-chip--consumption">{{ taggingProgressData.result.persona_tags.consumption_tier }}</span>
                <span v-if="taggingProgressData.result.persona_tags.temperament_psychology" class="tp-chip tp-chip--temperament">{{ taggingProgressData.result.persona_tags.temperament_psychology }}</span>
                <span v-if="taggingProgressData.result.persona_tags.social_identity" class="tp-chip tp-chip--identity">{{ taggingProgressData.result.persona_tags.social_identity }}</span>
                <span v-if="taggingProgressData.result.persona_tags.occasion" class="tp-chip tp-chip--occasion">{{ taggingProgressData.result.persona_tags.occasion }}</span>
              </div>
            </div>
            <!-- ① persona_tags: 置信度 -->
            <div class="tp-result-group" v-if="taggingProgressData.result.persona_tags?.confidence">
              <span class="tp-result-group-label">置信度</span>
              <div class="tp-result-chips">
                <span class="tp-chip tp-chip--meta">基础人口 {{ taggingProgressData.result.persona_tags.confidence.basic_demographics }}</span>
                <span class="tp-chip tp-chip--meta">消费层级 {{ taggingProgressData.result.persona_tags.confidence.consumption_tier }}</span>
                <span class="tp-chip tp-chip--meta">气质心理 {{ taggingProgressData.result.persona_tags.confidence.temperament_psychology }}</span>
              </div>
            </div>

            <!-- ② style_vector: 全部 32 维（按分数排序，>0 的都展示） -->
            <div class="tp-result-group" v-if="taggingProgressData.result.style_vector">
              <span class="tp-result-group-label">风格向量</span>
              <div class="tp-result-chips">
                <span
                  v-for="(score, style) in allStyles(taggingProgressData.result.style_vector)"
                  :key="style"
                  class="tp-chip tp-chip--style"
                  :class="score >= 0.5 ? 'tp-chip--style-hi' : ''"
                  :title="`${style}: ${(score * 100).toFixed(0)}%`"
                >{{ style }} {{ (score * 100).toFixed(0) }}%</span>
              </div>
            </div>

            <!-- ③ style_signature: color_palette -->
            <template v-if="taggingProgressData.result.style_signature">
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.color_palette">
                <span class="tp-result-group-label">色彩</span>
                <div class="tp-result-chips">
                  <span v-for="c in taggingProgressData.result.style_signature.color_palette.dominant_colors" :key="c" class="tp-chip tp-chip--color">{{ c }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.color_palette.temperature }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.color_palette.saturation }}</span>
                  <span class="tp-chip tp-chip--meta">对比度 {{ taggingProgressData.result.style_signature.color_palette.contrast }}</span>
                  <span v-for="c in taggingProgressData.result.style_signature.color_palette.signature_combos" :key="c" class="tp-chip tp-chip--color">{{ c }}</span>
                  <span class="tp-chip tp-chip--meta">单色倾向 {{ (taggingProgressData.result.style_signature.color_palette.monochromatic_tendency * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <!-- style_signature: material_profile -->
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.material_profile">
                <span class="tp-result-group-label">材质</span>
                <div class="tp-result-chips">
                  <span v-for="m in taggingProgressData.result.style_signature.material_profile.primary_materials" :key="m" class="tp-chip tp-chip--meta">{{ m }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.material_profile.texture_preference }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.material_profile.weight_preference }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.material_profile.transparency_level }}</span>
                  <span class="tp-chip tp-chip--meta">硬件感 {{ (taggingProgressData.result.style_signature.material_profile.hardware_affinity * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <!-- style_signature: silhouette_profile -->
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.silhouette_profile">
                <span class="tp-result-group-label">廓形</span>
                <div class="tp-result-chips">
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.silhouette_profile.fit_preference }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.silhouette_profile.proportion_play }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.silhouette_profile.structure_level }}</span>
                  <span class="tp-chip tp-chip--meta">层叠 {{ taggingProgressData.result.style_signature.silhouette_profile.layering_complexity }}</span>
                  <template v-if="taggingProgressData.result.style_signature.silhouette_profile.length_preference">
                    <span v-for="(v, k) in taggingProgressData.result.style_signature.silhouette_profile.length_preference" :key="k" class="tp-chip tp-chip--meta">{{ k }}: {{ v }}</span>
                  </template>
                </div>
              </div>
              <!-- style_signature: pattern_profile -->
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.pattern_profile">
                <span class="tp-result-group-label">图案</span>
                <div class="tp-result-chips">
                  <span v-for="p in taggingProgressData.result.style_signature.pattern_profile.pattern_types" :key="p" class="tp-chip tp-chip--meta">{{ p }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.pattern_profile.pattern_scale }}</span>
                  <span class="tp-chip tp-chip--meta">频率 {{ (taggingProgressData.result.style_signature.pattern_profile.pattern_frequency * 100).toFixed(0) }}%</span>
                  <span class="tp-chip tp-chip--meta">logo {{ taggingProgressData.result.style_signature.pattern_profile.logo_visibility }}</span>
                  <span class="tp-chip tp-chip--meta">混搭印花 {{ taggingProgressData.result.style_signature.pattern_profile.print_mixing ? '是' : '否' }}</span>
                </div>
              </div>
              <!-- style_signature: aesthetic_mood -->
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.aesthetic_mood">
                <span class="tp-result-group-label">气场</span>
                <div class="tp-result-chips">
                  <span class="tp-chip tp-chip--mood">{{ taggingProgressData.result.style_signature.aesthetic_mood.energy }}</span>
                  <span v-for="f in taggingProgressData.result.style_signature.aesthetic_mood.formality_range" :key="f" class="tp-chip tp-chip--mood">{{ f }}</span>
                  <span class="tp-chip tp-chip--mood">{{ taggingProgressData.result.style_signature.aesthetic_mood.gender_expression }}</span>
                  <span v-for="k in taggingProgressData.result.style_signature.aesthetic_mood.mood_keywords" :key="k" class="tp-chip tp-chip--mood">{{ k }}</span>
                  <span v-for="r in taggingProgressData.result.style_signature.aesthetic_mood.cultural_references" :key="r" class="tp-chip tp-chip--meta">{{ r }}</span>
                </div>
              </div>
              <!-- style_signature: occasion_vector Top 5 -->
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.occasion_vector">
                <span class="tp-result-group-label">场合向量</span>
                <div class="tp-result-chips">
                  <span
                    v-for="(score, occ) in topStyles(taggingProgressData.result.style_signature.occasion_vector, 5)"
                    :key="occ"
                    class="tp-chip tp-chip--occasion"
                  >{{ occ }} {{ (score * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <!-- style_signature: price_positioning -->
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.price_positioning">
                <span class="tp-result-group-label">价格定位</span>
                <div class="tp-result-chips">
                  <span class="tp-chip tp-chip--consumption">{{ taggingProgressData.result.style_signature.price_positioning.tier }}</span>
                  <span class="tp-chip tp-chip--meta">投资感 {{ (taggingProgressData.result.style_signature.price_positioning.investment_vs_trend * 100).toFixed(0) }}%</span>
                  <span class="tp-chip tp-chip--meta">品牌感知 {{ (taggingProgressData.result.style_signature.price_positioning.brand_consciousness * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <!-- style_signature: era_influence -->
              <div class="tp-result-group" v-if="taggingProgressData.result.style_signature.era_influence?.primary_era">
                <span class="tp-result-group-label">年代感</span>
                <div class="tp-result-chips">
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.era_influence.primary_era }}</span>
                  <span class="tp-chip tp-chip--meta">{{ taggingProgressData.result.style_signature.era_influence.era_authenticity }}</span>
                  <span class="tp-chip tp-chip--meta">未来感 {{ (taggingProgressData.result.style_signature.era_influence.retro_futurism * 100).toFixed(0) }}%</span>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- 视频列表 -->
        <div class="tp-video-list" v-if="taggingProgressData?.videos?.length">
          <div
            v-for="v in taggingProgressData.videos"
            :key="v.video_id"
            class="tp-video-item"
            :class="`is-${v.status}`"
          >
            <span class="tp-video-status-dot" :class="`is-${v.status}`"></span>
            <span class="tp-video-desc">{{ v.description }}</span>
            <span class="tp-video-status-label">{{ videoTaggingStatusLabel(v.status) }}</span>
          </div>
        </div>
        <div v-else-if="!taggingProgressLoading" class="tp-empty">暂无视频数据</div>
      </div>
    </el-dialog>

    <!-- 视频自定义全屏遮罩（固定铺满视口，CSS 控制 9:16） -->
    <teleport to="body">
      <div v-if="vcFullscreenVisible" class="vc-fullscreen-mask" @click.self="closeVcFullscreen">
        <button class="vc-fullscreen-close" @click="closeVcFullscreen">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
        <video
          v-if="vcFullscreenItem"
          :src="vcFullscreenItem.local_video_url || vcFullscreenItem.local_gcs_video_url"
          class="vc-fullscreen-video"
          controls
          autoplay
          playsinline
        />
      </div>
    </teleport>

    <!-- 标签搜索确认弹窗 -->
    <el-dialog
      v-model="showHashtagSearchDialog"
      title="标签搜索"
      width="480px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="al-supplement-body">
        <div class="al-supplement-scope">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span v-if="selectedMap.size > 0">将为已选 <b>{{ selectedMap.size }}</b> 个账号搜索并绑定 HashTag</span>
          <span v-else>将为全部 <b>{{ total }}</b> 个账号搜索并绑定 HashTag</span>
        </div>
        <div style="color:#6b7280;font-size:13px;line-height:1.6">
          任务会在后台执行：抓取每个账号绑定博主的热门视频 → 提取 HashTag → AI 过滤 → 自动写入账号。<br>
          抓取数量、AI 过滤提示词可在「AI博主配置」中设置。
        </div>
        <div class="al-hashtag-bind-bar">
          <span class="al-hashtag-bind-label">绑定方式：</span>
          <el-radio-group v-model="hashtagBindMode" size="small">
            <el-radio-button value="replace">覆盖原有标签</el-radio-button>
            <el-radio-button value="merge">追加合并</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <template #footer>
        <el-button @click="showHashtagSearchDialog = false">取消</el-button>
        <el-button type="primary" :loading="hashtagSearchLoading" @click="startHashtagSearch">开始搜索并绑定</el-button>
      </template>
    </el-dialog>

    <!-- Flag 过滤栏 -->
    <div class="al-filter-bar">
      <!-- 账号名搜索框 -->
      <div class="al-search-box">
        <svg class="al-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input
          v-model="searchQuery"
          class="al-search-input"
          placeholder="搜索账号名称..."
          @input="onSearchInput"
        />
        <button v-if="searchQuery" class="al-search-clear" @click="clearSearch">✕</button>
      </div>
      <div class="al-filter-flags">
        <button
          class="al-flag-filter-btn"
          :class="{ active: filterFlagId === null }"
          @click="handleFilterFlag(null)"
        >全部</button>
        <template v-for="flag in visibleFilterFlags" :key="flag.id">
          <button
            class="al-flag-filter-btn"
            :class="{ active: filterFlagId === flag.id, 'is-pinned': flag.is_pinned }"
            :style="filterFlagId === flag.id && flag.color ? { background: flag.color, borderColor: flag.color, color: '#fff' } : flag.color ? { borderColor: flag.color, color: flag.color } : {}"
            @click="handleFilterFlag(flag.id)"
          >
            <svg v-if="flag.is_pinned" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5v6h2v-6h5v-2l-2-2z"/></svg>
            <span class="al-flag-dot" v-else :style="flag.color ? { background: flag.color } : {}"></span>
            {{ flag.name }}
          </button>
        </template>
        <button v-if="hasMoreFlags" class="al-flag-expand-btn" @click="flagBarExpanded = !flagBarExpanded">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <polyline v-if="flagBarExpanded" points="18 15 12 9 6 15"/>
            <polyline v-else points="6 9 12 15 18 9"/>
          </svg>
          {{ flagBarExpanded ? '收起' : `展开全部 (${allFlags.length})` }}
        </button>
        <button class="al-flag-manage-btn" @click="openFlagManager">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          管理标识
        </button>
      </div>

      <!-- 字段筛选行 -->
      <div class="al-col-filters">
        <select class="al-col-filter-select" v-model="filterGender" @change="onFilterChange">
          <option value="">性别 · 全部</option>
          <option value="female">女</option>
          <option value="male">男</option>
          <option value="unisex">中性</option>
        </select>
        <select class="al-col-filter-select" v-model="filterAccountType" @change="onFilterChange">
          <option value="">类型 · 全部</option>
          <option value="exclusive">独享号</option>
          <option value="shared">共享号</option>
          <option value="persona">人设号</option>
        </select>
        <select class="al-col-filter-select" v-model="filterFaceMode" @change="onFilterChange">
          <option value="">面孔 · 全部</option>
          <option value="face">人脸</option>
          <option value="no_face">非人脸</option>
        </select>
        <select class="al-col-filter-select" v-model="filterProductCodeMode" @change="onFilterChange">
          <option value="">商品码 · 全部</option>
          <option value="with_code">带商品码</option>
          <option value="without_code">非商品码</option>
        </select>
        <select class="al-col-filter-select" v-model="filterAccountTier" @change="onFilterChange">
          <option value="">账号等级 · 全部</option>
          <option value="test">实验号</option>
          <option value="dev">常规号</option>
          <option value="prod">正式号</option>
        </select>
        <select class="al-col-filter-select" v-model="filterPlatformBindingStatus" @change="onFilterChange">
          <option value="">平台绑定 · 全部</option>
          <option value="bound">已绑定</option>
          <option value="confirmed">已确认</option>
          <option value="unbound">未绑定</option>
        </select>
        <select class="al-col-filter-select" v-model="filterClassificationType" @change="onClassificationTypeChange">
          <option value="">分类 · 全部</option>
          <option value="single">单核心</option>
          <option value="dual">双核心</option>
          <option value="chaos">混乱</option>
          <option value="insufficient">样本不足</option>
          <option value="unclassified">未分类</option>
        </select>
        <button v-if="hasActiveColFilters" class="al-col-filter-clear" @click="clearColFilters">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          清除筛选
        </button>
      </div>

      <!-- 分类细类二级筛选：单核心选 1，双核心选 2 -->
      <div v-if="filterClassificationType === 'single' || filterClassificationType === 'dual'" class="al-cat-filter">
        <span class="al-cat-filter-label">
          {{ filterClassificationType === 'single' ? '选择 1 个分类' : '选择 2 个分类' }}
          <span class="al-cat-filter-hint">（已选 {{ filterCategoryIndices.length }}/{{ filterClassificationType === 'single' ? 1 : 2 }}）</span>
        </span>
        <div class="al-cat-filter-pills">
          <button
            v-for="cat in CATEGORY_OPTIONS"
            :key="cat.key"
            type="button"
            class="al-cat-pill"
            :class="[
              `is-${cat.major}`,
              { active: filterCategoryIndices.includes(cat.key) },
            ]"
            @click.prevent="toggleCategoryFilter(cat.key)"
          >{{ cat.label }}</button>
        </div>
      </div>

      <!-- 多选批量操作栏 -->
      <transition name="bulk-bar">
        <div v-if="selectedIds.size > 0" class="al-bulk-bar">
          <span class="al-bulk-count">已选 {{ selectedIds.size }} 个</span>
          <button class="al-bulk-action-btn is-bind" @click="openBulkFlagDialog('bind')">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
            批量绑定标识
          </button>
          <button class="al-bulk-action-btn is-unbind" @click="openBulkFlagDialog('unbind')">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            批量移除标识
          </button>
          <button class="al-bulk-action-btn is-edit" @click="openBulkAttributeDialog">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
            批量修改属性
          </button>
          <button class="al-bulk-clear-btn" @click="clearSelection">取消选择</button>
        </div>
      </transition>
    </div>

    <!-- 已勾选 AI 博主统计 -->
    <div v-if="selectedMap.size > 0" class="al-selection-stats">
      <div class="al-selection-stats-header">
        <span class="al-selection-stats-title">已勾选 AI 博主统计</span>
        <span class="al-selection-stats-desc">数据随勾选博主动态更新，缺失/0 值不参与统计</span>
        <span class="al-selection-stats-count">已勾选 {{ selectedMap.size }} 个</span>
      </div>
      <div class="al-selection-stats-cards">
        <div class="al-stat-card is-followers">
          <div class="al-stat-card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div class="al-stat-card-body">
            <div class="al-stat-card-label">平均粉丝数</div>
            <div class="al-stat-card-value">{{ formatCount(selectionStats.avgFollowers) }}</div>
          </div>
        </div>
        <div class="al-stat-card is-views">
          <div class="al-stat-card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </div>
          <div class="al-stat-card-body">
            <div class="al-stat-card-label">平均 Views</div>
            <div class="al-stat-card-value">{{ formatCount(selectionStats.avgViews) }}</div>
          </div>
        </div>
        <div class="al-stat-card is-like">
          <div class="al-stat-card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
          </div>
          <div class="al-stat-card-body">
            <div class="al-stat-card-label">平均点赞率</div>
            <div class="al-stat-card-value">{{ formatPercent(selectionStats.avgLikeRate) }}</div>
          </div>
        </div>
        <div class="al-stat-card is-conversion">
          <div class="al-stat-card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
          </div>
          <div class="al-stat-card-body">
            <div class="al-stat-card-label">平均 AI 博主转化率</div>
            <div class="al-stat-card-value al-stat-card-value-empty">-</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Table list -->
    <div v-loading="loading" class="al-table-wrap">
      <div class="al-table-scroll">
      <table class="al-table">
        <thead>
          <tr>
            <th class="al-th al-th-check">
              <input
                type="checkbox"
                class="al-checkbox"
                :checked="allSelected"
                :indeterminate="someSelected"
                @change="e => toggleSelectAll(e.target.checked)"
              />
            </th>
            <th class="al-th al-th-media">头像 / 照片</th>
            <th class="al-th al-th-name">账号名称</th>
            <th class="al-th al-th-platform">平台绑定</th>
            <th class="al-th al-th-stat al-th-sortable" @click="toggleSort('followers_count')">
              <span class="al-th-label">粉丝数</span>
              <span class="al-sort-icon"><SortIcon field="followers_count" :sort-by="sortBy" :sort-order="sortOrder" /></span>
            </th>
            <th class="al-th al-th-stat al-th-sortable" @click="toggleSort('total_views')">
              <span class="al-th-label">总 Views</span>
              <span class="al-sort-icon"><SortIcon field="total_views" :sort-by="sortBy" :sort-order="sortOrder" /></span>
            </th>
            <th class="al-th al-th-stat al-th-sortable" @click="toggleSort('avg_views')">
              <span class="al-th-label">均 Views</span>
              <span class="al-sort-icon"><SortIcon field="avg_views" :sort-by="sortBy" :sort-order="sortOrder" /></span>
            </th>
            <th class="al-th al-th-stat al-th-sortable" @click="toggleSort('avg_like_rate')">
              <span class="al-th-label">点赞率</span>
              <span class="al-sort-icon"><SortIcon field="avg_like_rate" :sort-by="sortBy" :sort-order="sortOrder" /></span>
            </th>
            <th class="al-th al-th-stat">Link总点击</th>
            <th class="al-th al-th-stat">平均点击率</th>
            <th class="al-th al-th-date al-th-sortable" @click="toggleSort('latest_video_published_at')">
              <span class="al-th-label">最新发布</span>
              <span class="al-sort-icon"><SortIcon field="latest_video_published_at" :sort-by="sortBy" :sort-order="sortOrder" /></span>
            </th>
            <th class="al-th al-th-flags">标识</th>
            <th class="al-th al-th-tags">标签 / 博主</th>
            <th class="al-th al-th-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.id"
            class="al-tr"
            :class="{ 'is-selected': selectedIds.has(item.id) }"
            @click="goToDetail(item)"
          >
            <!-- 多选 -->
            <td class="al-td al-td-check" @click.stop>
              <input
                type="checkbox"
                class="al-checkbox"
                :checked="selectedIds.has(item.id)"
                @change="() => toggleSelectItem(item.id)"
              />
            </td>

            <!-- 头像/照片 -->
            <td class="al-td al-td-media" @click.stop>
              <div class="al-media-cell">
                <div class="al-photo-wrap" @click="previewMedia(item, 'photo')">
                  <img v-if="item.photo_url" :src="item.photo_url" class="al-photo-img" />
                  <div v-else class="al-photo-ph">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.7"><path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14l-5.5-5.5a2 2 0 0 0-2.828 0L4 21V5z"/><circle cx="15" cy="9" r="2"/></svg>
                  </div>
                </div>
                <div class="al-avatar-wrap" @click="previewMedia(item, 'avatar')">
                  <img v-if="item.avatar_url" :src="item.avatar_url" class="al-avatar-img" />
                  <div v-else class="al-avatar-ph">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="1.5"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
                  </div>
                </div>
                <span v-if="item.pending_publish_count" class="al-pending-badge" :title="`队列中 ${item.pending_publish_count} 条`">{{ item.pending_publish_count }}</span>
              </div>
            </td>

            <!-- 账号名称 -->
            <td class="al-td al-td-name">
              <div class="al-account-card">
              <div class="al-account-head">
                <div class="al-account-title-wrap">
                  <div class="al-name-main">{{ item.account_name }}</div>
                  <div v-if="item.account_handle" class="al-handle">@{{ item.account_handle }}</div>
                </div>
                <span class="ac-type-badge" :class="`ac-tier-${item.account_tier || 'test'}`">
                  {{ { test: '实验号', dev: '常规号', prod: '正式号' }[item.account_tier || 'test'] }}
                </span>
              </div>
              <div v-if="item.account_signature" class="al-signature">{{ item.account_signature }}</div>
              <div class="al-identity-grid">
                <span class="ac-type-badge" :class="`ac-type-${item.account_type || 'exclusive'}`">
                  {{ item.account_type === 'persona' ? '人设号' : item.account_type === 'exclusive' ? '独享号' : '共享号' }}
                </span>
                <span
                  class="ac-type-badge ac-face-badge"
                  :class="item.face_mode === 'no_face' ? 'ac-face-no' : 'ac-face-yes'"
                  @click.stop="toggleFaceMode(item)"
                >
                  {{ item.face_mode === 'no_face' ? '非人脸' : '人脸' }}
                </span>
                <span
                  class="ac-type-badge"
                  :class="`ac-gender-${item.gender || 'female'}`"
                  @click.stop="cycleGender(item)"
                >
                  {{ { male: '男', female: '女', unisex: '中性' }[item.gender || 'female'] }}
                </span>
                <span
                  class="ac-type-badge"
                  :class="item.product_code_mode === 'with_code' ? 'ac-product-code-yes' : 'ac-product-code-no'"
                >
                  {{ item.product_code_mode === 'with_code' ? '带商品码' : '非商品码' }}
                </span>
                <span v-if="item.ai_generation_status && item.ai_generation_status !== 'idle'" class="ac-ai-status" :class="`is-${item.ai_generation_status}`">
                  {{ aiGenerationStatusLabel(item.ai_generation_status) }}
                </span>
                <span v-if="item.hidden" class="ac-type-badge ac-hidden-badge">已隐藏</span>
              </div>

              <div v-if="item.supplement_status" class="ac-supplement-row" :class="`is-${item.supplement_status.status}`">
                <div class="ac-supplement-title">
                  <span class="ac-supplement-dot"></span>
                  <span>{{ supplementStatusLabel(item.supplement_status.status) }}</span>
                  <span class="ac-supplement-mode">{{ supplementModeLabel(item.supplement_status.mode) }}</span>
                </div>
                <div class="ac-supplement-lines">
                  <span v-if="item.supplement_status.current_unused_template_count !== null && item.supplement_status.current_unused_template_count !== undefined">
                    未使用模板 {{ item.supplement_status.current_unused_template_count || 0 }}/{{ item.supplement_status.target_unused_template_count || item.supplement_status.target_count || 0 }}
                  </span>
                  <span v-else>本轮新增 {{ item.supplement_status.completed_count || 0 }} 个</span>
                  <span v-if="item.supplement_status.status === 'running'">本轮请求 {{ item.supplement_status.requested_video_count || item.supplement_status.target_count || 0 }} 个</span>
                  <span v-else-if="item.supplement_status.status === 'failed'">目标 {{ item.supplement_status.target_unused_template_count || item.supplement_status.target_count || 0 }} 个</span>
                </div>
              </div>

              <!-- 分类状态行 -->
              <div class="al-account-metrics">
                <span v-if="item.classification_status === 'running'" class="ac-classify-badge is-running">分类中</span>
                <template v-if="item.classification_summary">
                  <span class="ac-classify-badge" :class="`is-${item.classification_summary.type}`">
                    <template v-if="item.classification_summary.type === 'single'">单核·{{ topSubLabel(item.classification_summary, item.classification_summary.primary) }}</template>
                    <template v-else-if="item.classification_summary.type === 'dual'">双核·{{ topSubLabel(item.classification_summary, item.classification_summary.primary) }}+{{ topSubLabel(item.classification_summary, item.classification_summary.secondary) }}</template>
                    <template v-else-if="item.classification_summary.type === 'chaos'">混乱</template>
                    <template v-else-if="item.classification_summary.type === 'insufficient'">样本不足</template>
                    <template v-else>未分类</template>
                  </span>
                  <span class="ac-metric-item">{{ item.classification_summary.success }}/{{ item.classification_summary.total }}分类</span>
                </template>
                <span class="ac-metric-item">{{ item.linked_video_count ?? 0 }}个视频</span>
                <span class="ac-metric-item" :title="`未使用 ${item.unused_template_count ?? 0} / 已使用 ${item.used_template_count ?? 0} 模板`">
                  {{ item.unused_template_count ?? 0 }}/{{ item.used_template_count ?? 0 }}模板
                </span>
                <span
                  v-if="(item.sub_task_success_denom ?? 0) > 0"
                  class="ac-metric-item"
                  :title="`最近 ${item.sub_task_success_sample ?? 0} 条子任务中：成功（暂存/队列中/已发布）${item.sub_task_success_numer ?? 0} / 决策样本（含待决策、决策未通过）${item.sub_task_success_denom ?? 0}`"
                >
                  成功率 {{ ((item.sub_task_success_rate ?? 0) * 100).toFixed(0) }}%
                </span>
              </div>
              <div v-if="item.style_description" class="al-style-desc">{{ item.style_description }}</div>
              <!-- KOL 短链 -->
              <div class="ac-kol-row">
                <span
                  v-if="item.kol_provision_status === 'pending'"
                  class="ac-kol-badge ac-kol-pending"
                  title="站内 KOL 创建中"
                >KOL 生成中</span>
                <template v-else-if="item.kol_provision_status === 'failed'">
                  <span
                    class="ac-kol-badge ac-kol-failed"
                    :title="item.kol_provision_error || '未知错误'"
                  >KOL 失败</span>
                  <button
                    class="ac-kol-retry-btn"
                    :disabled="retryingKolId === item.id"
                    :title="`重试 KOL 创建${item.kol_provision_error ? '\n错误: ' + item.kol_provision_error : ''}`"
                    @click.stop="handleRetryKol(item)"
                  >{{ retryingKolId === item.id ? '重试中…' : '重试' }}</button>
                </template>
                <template v-else>
                  <div v-if="kolReservationLinks(item).length" class="ac-kol-list">
                    <div
                      v-for="entry in kolReservationLinks(item)"
                      :key="entry.id"
                      class="ac-kol-platform-row"
                    >
                      <span
                        class="ac-kol-platform-tag"
                        :class="`ac-kol-platform-${entry.platform}`"
                      >{{ kolPlatformShort(entry.platform) }}</span>
                      <a
                        v-if="entry.short"
                        class="ac-kol-link"
                        :href="entry.short"
                        target="_blank"
                        rel="noopener"
                        @click.stop
                      >{{ entry.short }}</a>
                      <span v-else class="ac-kol-link-empty" :title="entry.long || ''">短链未生成</span>
                    </div>
                  </div>
                  <span
                    v-else-if="item.kol_user_id"
                    class="ac-kol-badge ac-kol-success"
                    :title="`kol_user_id=${item.kol_user_id}`"
                  >KOL 已创建</span>
                </template>
              </div>
              </div>
            </td>

            <!-- 平台绑定 -->
            <td class="al-td al-td-platform">
              <div v-if="item.channel_reservations?.length" class="al-bindings">
                <template v-for="reservation in boundChannelReservations(item)" :key="`bound-${reservation.id}`">
                  <span
                    class="ac-tag"
                    :class="[`ac-tag-${reservation.platform}`, reservation.channel_status === 'disabled' ? 'ac-tag-disabled' : '']"
                    :title="reservation.channel_status === 'disabled' ? reservationBoundLabel(reservation) + '（已禁用）' : reservationBoundLabel(reservation)"
                  >
                    <svg v-if="reservation.channel_status === 'disabled'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right:2px;flex-shrink:0"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    {{ reservationBoundLabel(reservation) }}
                  </span>
                </template>
                <span
                  v-for="reservation in unboundChannelReservations(item)"
                  :key="`reservation-${reservation.id}`"
                  class="ac-tag ac-tag-reserved"
                  :title="reservationDisplayLabel(reservation)"
                >{{ reservationDisplayLabel(reservation) }}</span>
              </div>
              <span v-else class="al-no-binding">未绑定</span>
            </td>

            <!-- 粉丝数 -->
            <td class="al-td al-td-stat">{{ formatCount(snapshotValue(item, 'followers_count')) }}</td>

            <!-- 总 Views -->
            <td class="al-td al-td-stat">{{ formatCount(snapshotValue(item, 'total_views')) }}</td>

            <!-- 均 Views -->
            <td class="al-td al-td-stat">{{ formatCount(snapshotValue(item, 'avg_views')) }}</td>

            <!-- 点赞率 -->
            <td class="al-td al-td-stat">{{ formatPercent(snapshotValue(item, 'avg_like_rate')) }}</td>

            <!-- Link 总点击 -->
            <td class="al-td al-td-stat">{{ formatCount(snapshotValue(item, 'total_kol_link_clicks')) }}</td>

            <!-- 平均点击率 -->
            <td class="al-td al-td-stat">{{ snapshotValue(item, 'avg_video_click_rate') != null ? formatPercent(snapshotValue(item, 'avg_video_click_rate') * 100) : '-' }}</td>

            <!-- 最新发布 -->
            <td class="al-td al-td-date">{{ formatSnapshotDate(snapshotValue(item, 'latest_video_published_at')) }}</td>

            <!-- 标识 -->
            <td class="al-td al-td-flags">
              <div v-if="item.bound_flags?.length" class="al-flags-wrap">
                <span v-for="flag in item.bound_flags" :key="flag.id" class="ac-flag-chip" :style="flag.color ? { background: flag.color + '22', borderColor: flag.color + '66', color: flag.color } : {}">
                  <span class="ac-flag-dot" :style="flag.color ? { background: flag.color } : {}"></span>
                  {{ flag.name }}
                </span>
              </div>
              <span v-else class="al-no-binding">—</span>
            </td>

            <!-- 标签 / 博主 -->
            <td class="al-td al-td-tags">
              <div v-if="item.bound_tags?.length" class="al-tags-wrap">
                <span v-for="tag in item.bound_tags" :key="tag.id" class="ac-tag-chip">
                  <span class="ac-tag-dot" :style="tag.color ? { background: tag.color } : {}"></span>
                  {{ tag.name }}
                </span>
              </div>
              <div v-if="item.tiktok_bloggers?.length" class="al-bloggers-wrap">
                <span
                  v-for="blogger in item.tiktok_bloggers"
                  :key="blogger.id"
                  class="ac-blogger-chip"
                  :title="blogger.blogger_name + (blogger.blogger_handle ? ' @' + blogger.blogger_handle : '')"
                >
                  <img v-if="blogger.avatar_url" :src="blogger.avatar_url" class="ac-blogger-avatar" />
                  <div v-else class="ac-blogger-avatar ac-blogger-avatar-ph">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
                  </div>
                  <span class="ac-blogger-name">{{ blogger.blogger_name }}</span>
                  <!-- 打标状态指示（可点击查看进度） -->
                  <span
                    v-if="blogger.tagging_status && blogger.tagging_status !== 'idle'"
                    class="ac-tagging-badge ac-tagging-badge--clickable"
                    :class="`ac-tagging-badge--${blogger.tagging_status}`"
                    :title="bloggerTaggingTitle(blogger) + ' · 点击查看进度'"
                    @click.stop="openTaggingProgress(blogger)"
                  >
                    <span v-if="blogger.tagging_status === 'pending' || blogger.tagging_status === 'running'">⏳</span>
                    <span v-else-if="blogger.tagging_status === 'success'">🏷</span>
                    <span v-else-if="blogger.tagging_status === 'failed'">✗</span>
                  </span>
                </span>
              </div>
              <!-- 打标结果展示（成功时） -->
              <div
                v-if="item.tiktok_bloggers?.some(b => b.tagging_status === 'success' && b.persona_tags)"
                class="al-persona-result-wrap"
              >
                <template v-for="blogger in item.tiktok_bloggers.filter(b => b.tagging_status === 'success' && b.persona_tags)" :key="blogger.id + '-tags'">
                  <div class="al-persona-result">
                    <span class="al-persona-label">{{ blogger.blogger_name }}</span>
                    <span v-if="blogger.persona_tags?.basic_demographics?.gender_or_sexuality_presentation" class="al-persona-chip al-persona-chip--demo">
                      {{ blogger.persona_tags.basic_demographics.gender_or_sexuality_presentation }}
                    </span>
                    <span v-if="blogger.persona_tags?.basic_demographics?.age_range" class="al-persona-chip al-persona-chip--demo">
                      {{ blogger.persona_tags.basic_demographics.age_range }}
                    </span>
                    <span v-if="blogger.persona_tags?.basic_demographics?.body_type" class="al-persona-chip al-persona-chip--demo">
                      {{ blogger.persona_tags.basic_demographics.body_type }}
                    </span>
                    <span v-if="blogger.persona_tags?.consumption_tier" class="al-persona-chip al-persona-chip--consumption">
                      {{ blogger.persona_tags.consumption_tier }}
                    </span>
                    <span v-if="blogger.persona_tags?.temperament_psychology" class="al-persona-chip al-persona-chip--temperament">
                      {{ blogger.persona_tags.temperament_psychology }}
                    </span>
                    <span v-if="blogger.persona_tags?.occasion" class="al-persona-chip al-persona-chip--occasion">
                      {{ blogger.persona_tags.occasion }}
                    </span>
                    <!-- Top 3 风格 -->
                    <template v-if="blogger.style_vector">
                      <span
                        v-for="(score, style) in topStyles(blogger.style_vector, 3)"
                        :key="style"
                        class="al-persona-chip al-persona-chip--style"
                        :title="`${style}: ${(score * 100).toFixed(0)}%`"
                      >
                        {{ style }} {{ (score * 100).toFixed(0) }}%
                      </span>
                    </template>
                  </div>
                </template>
              </div>
              <!-- Hashtags -->
              <div v-if="item.hashtags?.length" class="al-hashtags-wrap">
                <span v-for="tag in item.hashtags.slice(0, 5)" :key="tag" class="al-hashtag-chip">#{{ tag }}</span>
                <span v-if="item.hashtags.length > 5" class="al-hashtag-chip al-hashtag-more">+{{ item.hashtags.length - 5 }}</span>
              </div>
              <span v-if="!item.bound_tags?.length && !item.tiktok_bloggers?.length && !item.hashtags?.length" class="al-no-binding">—</span>
            </td>

            <!-- 操作 -->
            <td class="al-td al-td-actions" @click.stop>
              <div class="al-row-actions">
                <button class="ac-btn ac-btn-stats" @click="openInNewTab({ name: 'publication-stats', query: { account_id: item.id } })">统计</button>
                <button class="ac-btn ac-btn-analytics" @click="openAnalyticsDialog(item)">数据</button>
                <button class="ac-btn ac-btn-sync" :class="{ loading: syncingId === item.id }" @click="handleSyncAccount(item)">{{ syncingId === item.id ? '同步中' : '同步' }}</button>
                <button class="ac-btn ac-btn-template-sync" :class="{ loading: templateSyncingId === item.id }" @click="handleSyncTemplateTags(item)">{{ templateSyncingId === item.id ? '同步中' : '同步模板' }}</button>
                <button class="ac-btn ac-btn-classify" @click="openClassificationDialog(item)">分类</button>
                <button class="ac-btn ac-btn-edit" @click="openInNewTab(`/dashboard/accounts/${item.id}/edit`)">编辑</button>
                <button class="ac-btn ac-btn-del" :class="{ loading: deleting === item.id }" @click="handleDelete(item)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      </div><!-- end al-table-scroll -->
    </div>

    <!-- Flag 管理弹窗 -->
    <el-dialog
      v-model="showFlagManagerDialog"
      title="管理标识"
      width="520px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="fm-body">
        <!-- 新建 / 编辑表单 -->
        <div class="fm-form">
          <div class="fm-form-title">{{ editingFlag ? '编辑标识' : '新建标识' }}</div>
          <div class="fm-form-row">
            <input
              v-model="flagForm.name"
              class="fm-input"
              placeholder="标识名称"
              maxlength="100"
              @keyup.enter="saveFlagForm"
            />
            <div class="fm-color-picker">
              <div
                class="fm-color-preview"
                :style="{ background: flagForm.color || '#e2e8f0' }"
                :title="flagForm.color"
              ></div>
              <div class="fm-color-swatches">
                <button
                  v-for="c in FLAG_COLORS"
                  :key="c"
                  class="fm-swatch"
                  :class="{ active: flagForm.color === c }"
                  :style="{ background: c }"
                  @click="flagForm.color = c"
                ></button>
              </div>
            </div>
          </div>
          <label class="fm-pin-toggle">
            <input type="checkbox" v-model="flagForm.is_pinned" class="fm-pin-checkbox" />
            <span class="fm-pin-label">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5v6h2v-6h5v-2l-2-2z"/></svg>
              设为快捷标签（固定显示在过滤栏最前面）
            </span>
          </label>
          <div class="fm-form-actions">
            <button v-if="editingFlag" class="fm-cancel-btn" @click="cancelEditFlag">取消</button>
            <button class="fm-save-btn" :disabled="flagSaving" @click="saveFlagForm">
              {{ flagSaving ? '保存中…' : editingFlag ? '更新' : '创建' }}
            </button>
          </div>
        </div>

        <!-- 已有标识列表 -->
        <div class="fm-list">
          <div v-if="pinnedFlags.length > 0" class="fm-group">
            <div class="fm-group-label">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5v6h2v-6h5v-2l-2-2z"/></svg>
              快捷标签
            </div>
            <div v-for="flag in pinnedFlags" :key="flag.id" class="fm-item is-pinned">
              <span class="fm-item-dot" :style="flag.color ? { background: flag.color } : {}"></span>
              <span class="fm-item-name">{{ flag.name }}</span>
              <div class="fm-item-actions">
                <button class="fm-edit-btn" @click="startEditFlag(flag)">编辑</button>
                <button class="fm-del-btn" :class="{ loading: flagDeletingId === flag.id }" @click="handleDeleteFlag(flag)">删除</button>
              </div>
            </div>
          </div>
          <div v-if="unpinnedFlags.length > 0" class="fm-group">
            <div class="fm-group-label">全部标识（{{ unpinnedFlags.length }}）</div>
            <div v-for="flag in unpinnedFlags" :key="flag.id" class="fm-item">
              <span class="fm-item-dot" :style="flag.color ? { background: flag.color } : {}"></span>
              <span class="fm-item-name">{{ flag.name }}</span>
              <div class="fm-item-actions">
                <button class="fm-edit-btn" @click="startEditFlag(flag)">编辑</button>
                <button class="fm-del-btn" :class="{ loading: flagDeletingId === flag.id }" @click="handleDeleteFlag(flag)">删除</button>
              </div>
            </div>
          </div>
          <div v-if="allFlags.length === 0" class="fm-empty">暂无标识</div>
        </div>
      </div>
    </el-dialog>

    <!-- 批量绑定/移除标识弹窗 -->
    <el-dialog
      v-model="showBulkFlagDialog"
      :title="bulkFlagMode === 'bind' ? `批量绑定标识（已选 ${selectedIds.size} 个账号）` : `批量移除标识（已选 ${selectedIds.size} 个账号）`"
      width="460px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="bfd-body">
        <div class="bfd-hint">{{ bulkFlagMode === 'bind' ? '选择要绑定到选中账号的标识：' : '选择要从选中账号移除的标识：' }}</div>
        <div class="bfd-flags">
          <label
            v-for="flag in allFlags"
            :key="flag.id"
            class="bfd-flag-item"
            :class="{ selected: bulkFlagSelectedIds.includes(flag.id) }"
          >
            <input type="checkbox" :value="flag.id" v-model="bulkFlagSelectedIds" class="bfd-checkbox" />
            <span class="bfd-flag-dot" :style="flag.color ? { background: flag.color } : {}"></span>
            <span class="bfd-flag-name">{{ flag.name }}</span>
          </label>
        </div>
        <div v-if="allFlags.length === 0" class="bfd-empty">暂无标识，请先在「管理标识」中创建</div>
      </div>
      <template #footer>
        <el-button @click="showBulkFlagDialog = false">取消</el-button>
        <el-button
          :type="bulkFlagMode === 'bind' ? 'primary' : 'danger'"
          :loading="bulkFlagSaving"
          @click="handleBulkFlagSubmit"
        >
          {{ bulkFlagMode === 'bind' ? '确认绑定' : '确认移除' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量修改账号属性弹窗 -->
    <el-dialog
      v-model="showBulkAttributeDialog"
      width="640px"
      :close-on-click-modal="false"
      destroy-on-close
      class="bae-dialog"
    >
      <template #header>
        <div class="bae-header">
          <div class="bae-header-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
          </div>
          <div>
            <div class="bae-title">批量修改属性</div>
            <div class="bae-subtitle">已选 {{ selectedIds.size }} 个账号 · {{ bulkAttributeChangedCount }} 项变更</div>
          </div>
        </div>
      </template>
      <div class="bae-body">
        <div class="bae-summary">
          <span class="bae-summary-label">作用范围</span>
          <strong>{{ selectedIds.size }}</strong>
          <span>个账号</span>
          <span class="bae-summary-separator"></span>
          <span :class="bulkAttributeChangedCount > 0 ? 'bae-summary-active' : 'bae-summary-muted'">
            {{ bulkAttributeChangedCount > 0 ? `准备修改 ${bulkAttributeChangedCount} 项属性` : '未选择变更项' }}
          </span>
        </div>

        <div class="bae-grid">
          <section
            v-for="field in BULK_ATTRIBUTE_FIELDS"
            :key="field.key"
            class="bae-field"
            :class="[{ 'is-active': bulkAttributeForm[field.key] }, `is-${field.tone}`]"
          >
            <div class="bae-field-head">
              <span class="bae-field-icon" v-html="field.icon"></span>
              <div class="bae-field-title-wrap">
                <span class="bae-field-label">{{ field.label }}</span>
                <strong>{{ bulkAttributeValueLabel(field.key) }}</strong>
              </div>
            </div>
            <div class="bae-options">
              <button
                v-for="option in BULK_ATTRIBUTE_OPTIONS[field.key]"
                :key="option.value"
                type="button"
                class="bae-option"
                :class="{ active: bulkAttributeForm[field.key] === option.value, 'is-keep': option.value === '' }"
                @click="bulkAttributeForm[field.key] = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </section>
        </div>
      </div>
      <template #footer>
        <div class="bae-footer">
          <button
            type="button"
            class="bae-reset"
            :disabled="bulkAttributeChangedCount === 0 || bulkAttributeSaving"
            @click="resetBulkAttributeForm"
          >
            清空选择
          </button>
          <div class="bae-footer-actions">
            <el-button @click="showBulkAttributeDialog = false">取消</el-button>
            <el-button
              type="primary"
              :loading="bulkAttributeSaving"
              :disabled="bulkAttributeChangedCount === 0"
              @click="handleBulkAttributeSubmit"
            >
              确认修改
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-empty v-if="!loading && items.length === 0" description="暂无账号，点击「新建账号」开始" :image-size="80" />

    <el-dialog
      v-model="previewVisible"
      width="min(92vw, 960px)"
      top="5vh"
      append-to-body
      class="ac-preview-dialog"
    >
      <img v-if="previewImage.url" :src="previewImage.url" :alt="previewImage.title" class="ac-preview-image" />
      <template #header>
        <div class="ac-preview-title">{{ previewImage.title }}</div>
      </template>
    </el-dialog>

    <!-- Footer pagination -->
    <div v-if="total > 0" class="al-footer">
      <div class="al-pagination-left">
        <span class="al-count-text">显示 {{ startIdx }}-{{ endIdx }} 共 {{ total }} 条</span>
        <select v-model="pageSize" @change="handleSizeChange(pageSize)" class="al-simple-select">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
          <option :value="500">500</option>
        </select>
      </div>
      <div class="al-pagination">
        <button class="pg-btn" :disabled="page <= 1" @click="goPage(page - 1)">← 上一页</button>
        <template v-for="p in visiblePages" :key="p">
          <span v-if="p === '...'" class="pg-ellipsis">…</span>
          <button v-else class="pg-btn pg-num" :class="{ active: p === page }" @click="goPage(p)">{{ p }}</button>
        </template>
        <button class="pg-btn" :disabled="endIdx >= total" @click="goPage(page + 1)">下一页 →</button>
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
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { useRoute, useRouter } from 'vue-router'
import { openInNewTab } from '../utils/nav'
import { ElMessage, ElMessageBox } from 'element-plus'
import { bulkGenerateAIAccounts, bulkResumeAIAccountGeneration, fetchAccounts, deleteAccount, updateScheduledPublish, supplementTemplates, autoSupplementTemplates, bulkGenerateVideoTasks, bulkUpdateScheduledPublish, patchAccount, bulkUpdateAccountAttributes, bulkGenerateNameHandle, bulkSearchHashtags, exportVideoUrls, fetchPlatformStats, startAccountClassification, fetchAccountClassification, retryAccountClassificationFailed, batchClassifyVideos, previewTierEvaluation, applyTierEvaluation, retryKolProvision, fetchChannelAnalytics, bulkPersonaTagging, syncAccountTemplateTags } from '../api/accounts'
import { fetchFlags, createFlag, updateFlag, deleteFlag, bulkBindFlags, bulkUnbindFlags } from '../api/flags'
import { fetchBloggerTaggingProgress, submitBloggerTagging } from '../api/persona_tagging'
import { syncAccountSnapshots } from '../api/video_publications'
import { isDuplicateRequestError } from '../api/http'
import { fetchPipelineSettings, updatePipelineSettings, fetchTemplateSupplementConfig, updateTemplateSupplementConfig, fetchScheduledGenerationConfig, updateScheduledGenerationConfig } from '../api/settings'
import { downloadLatestPublishedVideos } from '../api/video_tasks'

const route = useRoute()
const router = useRouter()

const PLATFORM_LABELS = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram' }

// ── Sort icon component ───────────────────────────────────────────────────────
const SortIcon = defineComponent({
  props: { field: String, sortBy: String, sortOrder: String },
  setup(props) {
    return () => {
      const active = props.sortBy === props.field
      const desc = props.sortOrder === 'desc'
      const color = active ? '#6366f1' : '#cbd5e1'
      return h('svg', { width: 10, height: 12, viewBox: '0 0 10 12', fill: 'none', style: 'flex-shrink:0' }, [
        h('path', { d: 'M5 1L2 4h6L5 1z', fill: active && !desc ? '#6366f1' : color }),
        h('path', { d: 'M5 11L2 8h6L5 11z', fill: active && desc ? '#6366f1' : color }),
      ])
    }
  },
})

// ── Sort state ────────────────────────────────────────────────────────────────
const sortBy = ref(null)
const sortOrder = ref('desc')

function toggleSort(field) {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortBy.value = field
    sortOrder.value = 'desc'
  }
  page.value = 1
  loadData()
}

// ── Column filters ────────────────────────────────────────────────────────────
const filterGender = ref('')
const filterAccountType = ref('')
const filterFaceMode = ref('')
const filterProductCodeMode = ref('')
const filterAccountTier = ref('')
const filterPlatformBindingStatus = ref('')
const filterClassificationType = ref('')
const filterCategoryIndices = ref([])

// 分类体系（与后端 video_classification_service._CATEGORIES 保持一致）
const CATEGORY_OPTIONS = [
  // 美美展示类
  { key: 'beauty_static_pose',    label: '静态 Pose / 镜头展示类',         major: 'beauty' },
  { key: 'beauty_light_action',   label: '轻动作展示类',                   major: 'beauty' },
  { key: 'beauty_dance',          label: '音乐跳舞类',                     major: 'beauty' },
  { key: 'beauty_lipsync',        label: '歌曲对口型类',                   major: 'beauty' },
  { key: 'beauty_drama_light',    label: '影视 / 台词轻演绎类',            major: 'beauty' },
  // 穿搭方法类
  { key: 'method_single_silent',  label: '不带语音单套逐件穿搭型',         major: 'method' },
  { key: 'method_multi_look',     label: '不带语音多套完整 Look 切换型',   major: 'method' },
  { key: 'method_multi_build',    label: '不带语音多套逐件搭建型',         major: 'method' },
  { key: 'method_base_replace',   label: '不带语音 Base Look 替换单品型', major: 'method' },
  { key: 'method_multiway',       label: '不带语音单品多穿型',             major: 'method' },
  { key: 'method_before_after',   label: '不带语音 Before & After 优化型', major: 'method' },
  { key: 'method_compare',        label: '不带语音左右对比 / 并列对比型', major: 'method' },
  { key: 'method_voice_formula',  label: '带语音公式规则讲解型',           major: 'method' },
  { key: 'method_voice_steps',    label: '带语音步骤流程讲解型',           major: 'method' },
  { key: 'method_voice_diagnose', label: '带语音问题诊断 / 优化讲解型',   major: 'method' },
  { key: 'method_voice_compare',  label: '带语音对比判断讲解型',           major: 'method' },
  { key: 'method_voice_case',     label: '带语音案例拆解讲解型',           major: 'method' },
  { key: 'method_voice_standard', label: '带语音选择标准讲解型',           major: 'method' },
  { key: 'method_voice_system',   label: '带语音系统规划讲解型',           major: 'method' },
  // 购物决策类
  { key: 'shopping_brand',        label: '品牌导向型',                     major: 'shopping' },
  { key: 'shopping_single_item',  label: '单品种草型',                     major: 'shopping' },
  { key: 'shopping_dupe',         label: '大牌平替 / Dupe 型',             major: 'shopping' },
  { key: 'shopping_scene',        label: '场景需求型',                     major: 'shopping' },
  { key: 'shopping_list',         label: '清单合集型',                     major: 'shopping' },
  { key: 'shopping_compare',      label: '对比选择型',                     major: 'shopping' },
  // 人设生活类
  { key: 'lifestyle',             label: '人设生活类',                     major: 'lifestyle' },
  // 情景剧情类
  { key: 'drama',                 label: '情景剧情类',                     major: 'drama' },
  // 不能分类
  { key: 'unclassifiable',        label: '不能分类',                       major: 'unclassifiable' },
]

const hasActiveColFilters = computed(() =>
  filterGender.value || filterAccountType.value || filterFaceMode.value || filterProductCodeMode.value || filterAccountTier.value || filterPlatformBindingStatus.value || filterClassificationType.value || filterCategoryIndices.value.length > 0
)

function onFilterChange() {
  page.value = 1
  loadData()
}

function onClassificationTypeChange() {
  filterCategoryIndices.value = []
  onFilterChange()
}

function toggleCategoryFilter(key) {
  const max = filterClassificationType.value === 'dual' ? 2 : 1
  const list = filterCategoryIndices.value
  const pos = list.indexOf(key)
  if (pos >= 0) {
    list.splice(pos, 1)
  } else {
    if (list.length >= max) list.shift()
    list.push(key)
  }
  page.value = 1
  loadData({ silent: true })
}

function clearColFilters() {
  filterGender.value = ''
  filterAccountType.value = ''
  filterFaceMode.value = ''
  filterProductCodeMode.value = ''
  filterAccountTier.value = ''
  filterPlatformBindingStatus.value = ''
  filterClassificationType.value = ''
  filterCategoryIndices.value = []
  page.value = 1
  loadData()
}

const loading = ref(false)
const deleting = ref(null)

// 下载视频
const downloading = ref(false)

// KOL 失败重试
const retryingKolId = ref(null)
async function handleRetryKol(item) {
  retryingKolId.value = item.id
  // 本地立刻把状态切到 pending，UI 即时反馈
  item.kol_provision_status = 'pending'
  item.kol_provision_error = null
  try {
    const updated = await retryKolProvision(item.id)
    // 用后端返回的字段覆盖本地
    Object.assign(item, updated)
    if (updated.kol_provision_status === 'success') {
      ElMessage.success('KOL 重新创建成功')
    } else if (updated.kol_provision_status === 'failed') {
      ElMessage.error(updated.kol_provision_error || 'KOL 重试失败')
    } else {
      ElMessage.info('KOL 重试已提交')
    }
  } catch (err) {
    item.kol_provision_status = 'failed'
    item.kol_provision_error = err?.response?.data?.detail || err?.message || '重试失败'
    ElMessage.error(item.kol_provision_error)
  } finally {
    retryingKolId.value = null
  }
}

async function handleDownload() {
  if (downloading.value) return
  downloading.value = true
  try {
    const ids = selectedMap.value.size > 0 ? [...selectedMap.value.keys()] : null
    const blob = await downloadLatestPublishedVideos(ids)
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = 'videos_latest.zip'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(blobUrl), 10000)
    ElMessage.success('打包完成，已开始下载')
  } catch (e) {
    let errText = ''
    if (e?.response?.data instanceof Blob) {
      errText = await e.response.data.text().catch(() => '')
    } else if (typeof e?.response?.data === 'string') {
      errText = e.response.data
    }
    const detail = errText ? (JSON.parse(errText).detail || errText) : (e?.message || '')
    ElMessage.error(detail.includes('没有已发布') ? '暂无已发布的视频' : '下载失败，请稍后重试')
  } finally {
    downloading.value = false
  }
}
const exporting = ref(false)

async function handleExportVideoUrls() {
  if (exporting.value) return
  exporting.value = true
  try {
    const ids = selectedMap.value.size > 0 ? [...selectedMap.value.keys()] : null
    const blob = await exportVideoUrls(ids)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'ai_blogger_videos.xlsx'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 10000)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

const syncingId = ref(null)
const templateSyncingId = ref(null)

async function handleSyncAccount(item) {
  if (syncingId.value) return
  syncingId.value = item.id
  try {
    const r = await syncAccountSnapshots(item.id)
    ElMessage.success(r?.message || '同步任务已提交')
    await loadData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '同步失败')
  } finally {
    syncingId.value = null
  }
}

async function handleSyncTemplateTags(item) {
  if (templateSyncingId.value) return
  templateSyncingId.value = item.id
  try {
    const result = await syncAccountTemplateTags(item.id)
    const newlyBound = result?.newly_bound || 0
    const unused = result?.unused_templates || 0
    const used = result?.used_templates || 0
    ElMessage.success(`已补绑 ${newlyBound} 个模板，当前 ${unused}/${used} 模板`)
    await loadData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '同步模板失败')
  } finally {
    templateSyncingId.value = null
  }
}

const bulkGenerating = ref(false)
const personaTagging = ref(false)
const bulkRestarting = ref(false)
const showBulkContinueDialog = ref(false)
const bulkResumeStage = ref('current')
const items = ref([])
const previewVisible = ref(false)
const previewImage = ref({ url: '', title: '' })
const total = ref(0)
const page = ref(Number(route.query.page) || 1)
const pageSize = ref(20)

// ── 多选（跨页）────────────────────────────────────────────────────────────────
// Map<id, account对象> 跨页保留完整 account 信息
const selectedMap = ref(new Map())
const selectedIds = computed(() => new Set(selectedMap.value.keys()))

// 已勾选 AI 博主聚合统计：缺失/0 值不参与平均
const selectionStats = computed(() => {
  const accounts = [...selectedMap.value.values()]
  const avg = (key) => {
    let sum = 0
    let count = 0
    for (const a of accounts) {
      const raw = a?.performance_snapshot?.[key]
      const n = Number(raw)
      if (!Number.isFinite(n) || n <= 0) continue
      sum += n
      count += 1
    }
    return count > 0 ? sum / count : null
  }
  return {
    avgFollowers: avg('followers_count'),
    avgViews: avg('avg_views'),
    avgLikeRate: avg('avg_like_rate'),
  }
})

// ── Flag 相关 ─────────────────────────────────────────────────────────────────
const allFlags = ref([])
const filterFlagId = ref(null)
const searchQuery = ref('')
let _searchTimer = null
const flagBarExpanded = ref(false)
const FLAG_BAR_LIMIT = 20

const pinnedFlags = computed(() => allFlags.value.filter(f => f.is_pinned))
const unpinnedFlags = computed(() => allFlags.value.filter(f => !f.is_pinned))
// 过滤栏显示：快捷标签全显，其余按展开状态截断
const visibleFilterFlags = computed(() => {
  const pinned = pinnedFlags.value
  const unpinned = unpinnedFlags.value
  if (flagBarExpanded.value) return [...pinned, ...unpinned]
  const remain = FLAG_BAR_LIMIT - pinned.length
  return [...pinned, ...unpinned.slice(0, Math.max(0, remain))]
})
const hasMoreFlags = computed(() =>
  allFlags.value.length > FLAG_BAR_LIMIT ||
  (pinnedFlags.value.length < FLAG_BAR_LIMIT && unpinnedFlags.value.length > FLAG_BAR_LIMIT - pinnedFlags.value.length)
)

// Flag 管理弹窗
const showFlagManagerDialog = ref(false)
const flagForm = ref({ name: '', color: '#6366f1', is_pinned: false })
const editingFlag = ref(null)
const flagSaving = ref(false)
const flagDeletingId = ref(null)

const FLAG_COLORS = [
  '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f97316',
  '#eab308', '#22c55e', '#10b981', '#06b6d4', '#3b82f6',
  '#64748b', '#0f172a',
]

async function loadFlags() {
  try {
    allFlags.value = await fetchFlags()
  } catch { /* silent */ }
}

function openFlagManager() {
  flagForm.value = { name: '', color: '#6366f1', is_pinned: false }
  editingFlag.value = null
  showFlagManagerDialog.value = true
}

function startEditFlag(flag) {
  editingFlag.value = flag
  flagForm.value = { name: flag.name, color: flag.color || '#6366f1', is_pinned: !!flag.is_pinned }
}

function cancelEditFlag() {
  editingFlag.value = null
  flagForm.value = { name: '', color: '#6366f1', is_pinned: false }
}

async function saveFlagForm() {
  if (!flagForm.value.name.trim()) {
    ElMessage.warning('请输入标识名称')
    return
  }
  flagSaving.value = true
  try {
    if (editingFlag.value) {
      const updated = await updateFlag(editingFlag.value.id, {
        name: flagForm.value.name.trim(),
        color: flagForm.value.color || null,
        is_pinned: flagForm.value.is_pinned,
      })
      const idx = allFlags.value.findIndex(f => f.id === updated.id)
      if (idx >= 0) allFlags.value[idx] = updated
      // 重新排序：pinned 在前
      allFlags.value.sort((a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0) || new Date(a.created_at) - new Date(b.created_at))
      cancelEditFlag()
      ElMessage.success('已更新')
    } else {
      const created = await createFlag({
        name: flagForm.value.name.trim(),
        color: flagForm.value.color || null,
        is_pinned: flagForm.value.is_pinned,
      })
      allFlags.value.push(created)
      allFlags.value.sort((a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0) || new Date(a.created_at) - new Date(b.created_at))
      flagForm.value = { name: '', color: '#6366f1', is_pinned: false }
      ElMessage.success('已创建')
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    flagSaving.value = false
  }
}

async function handleDeleteFlag(flag) {
  try {
    await ElMessageBox.confirm(`确定删除标识「${flag.name}」？`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  flagDeletingId.value = flag.id
  try {
    await deleteFlag(flag.id)
    allFlags.value = allFlags.value.filter(f => f.id !== flag.id)
    if (filterFlagId.value === flag.id) {
      filterFlagId.value = null
      loadData()
    }
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  } finally {
    flagDeletingId.value = null
  }
}

// 批量绑定 flag 弹窗
const showBulkFlagDialog = ref(false)
const bulkFlagMode = ref('bind') // 'bind' | 'unbind'
const bulkFlagSelectedIds = ref([])
const bulkFlagSaving = ref(false)

// 批量生成名称/Handle/签名
const bulkNameHandleLoading = ref(false)

async function confirmBulkNameHandle() {
  if (bulkNameHandleLoading.value) return
  bulkNameHandleLoading.value = true
  try {
    const ids = selectedMap.value.size > 0 ? [...selectedMap.value.keys()] : null
    const result = await bulkGenerateNameHandle(ids)
    ElMessage.success(`已入队 ${result.queued_count} 个账号，生成完成后请刷新列表查看`)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    bulkNameHandleLoading.value = false
  }
}

// 标签搜索
const showHashtagSearchDialog = ref(false)
const hashtagSearchLoading = ref(false)
const hashtagBindMode = ref('replace')

function openHashtagSearchDialog() {
  showHashtagSearchDialog.value = true
}

async function startHashtagSearch() {
  if (hashtagSearchLoading.value) return
  hashtagSearchLoading.value = true
  try {
    const ids = selectedMap.value.size > 0 ? [...selectedMap.value.keys()] : null
    await bulkSearchHashtags(ids, hashtagBindMode.value)
    ElMessage.success('标签搜索任务已入队，完成后将自动绑定到账号，请稍后刷新查看')
    showHashtagSearchDialog.value = false
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败，请检查 Apify Token 和博主绑定配置')
  } finally {
    hashtagSearchLoading.value = false
  }
}

const bulkClassifying = ref(false)
const classifyForce = ref(false)
const showClassifyConfirmDialog = ref(false)
const classifyConfirmMode = ref('batch') // 'batch' | 'single'

function openClassifyConfirm(mode) {
  classifyConfirmMode.value = mode
  classifyForce.value = false
  showClassifyConfirmDialog.value = true
}

async function confirmClassify() {
  if (classifyConfirmMode.value === 'single') {
    await _doSingleClassify()
  } else {
    await _doBatchClassify()
  }
}

async function _doBatchClassify() {
  if (bulkClassifying.value) return
  const isSelection = selectedMap.value.size > 0
  const ids = isSelection ? [...selectedMap.value.keys()] : []
  let accountListFilters = null
  if (!isSelection) {
    accountListFilters = {}
    if (filterGender.value) accountListFilters.gender = filterGender.value
    if (filterAccountType.value) accountListFilters.account_type = filterAccountType.value
    if (filterFaceMode.value) accountListFilters.face_mode = filterFaceMode.value
    if (filterProductCodeMode.value) accountListFilters.product_code_mode = filterProductCodeMode.value
    if (filterAccountTier.value) accountListFilters.account_tier = filterAccountTier.value
    if (filterPlatformBindingStatus.value) accountListFilters.platform_binding_status = filterPlatformBindingStatus.value
    if (filterClassificationType.value) accountListFilters.classification_type = filterClassificationType.value
    if (filterCategoryIndices.value.length > 0) accountListFilters.category_keys = filterCategoryIndices.value
  }
  bulkClassifying.value = true
  try {
    const res = await batchClassifyVideos(ids, classifyForce.value, accountListFilters)
    ElMessage.success(`已入队 ${res.total_queued} 个视频，将逐账号依次分类`)
    showClassifyConfirmDialog.value = false
  } catch (e) {
    ElMessage.error('批量分类失败')
  } finally {
    bulkClassifying.value = false
  }
  loadItems().catch(() => {})
}

async function _doSingleClassify() {
  if (!classificationAccount.value || classificationStarting.value) return
  classificationStarting.value = true
  try {
    const result = await startAccountClassification(classificationAccount.value.id, classifyForce.value)
    ElMessage.success(`已入队 ${result.queued || 0} 个，跳过 ${result.skipped || 0} 个`)
    showClassifyConfirmDialog.value = false
    await refreshClassification()
    scheduleClassificationPoll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '启动分类失败')
  } finally {
    classificationStarting.value = false
  }
}

function openBulkFlagDialog(mode) {
  if (selectedIds.value.size === 0) {
    ElMessage.warning('请先勾选账号')
    return
  }
  bulkFlagMode.value = mode
  bulkFlagSelectedIds.value = []
  showBulkFlagDialog.value = true
}

async function handleBulkFlagSubmit() {
  if (bulkFlagSelectedIds.value.length === 0) {
    ElMessage.warning('请选择至少一个标识')
    return
  }
  bulkFlagSaving.value = true
  try {
    const accountIds = [...selectedIds.value]
    if (bulkFlagMode.value === 'bind') {
      await bulkBindFlags(accountIds, bulkFlagSelectedIds.value)
      ElMessage.success(`已为 ${accountIds.length} 个账号绑定标识`)
    } else {
      await bulkUnbindFlags(accountIds, bulkFlagSelectedIds.value)
      ElMessage.success(`已从 ${accountIds.length} 个账号移除标识`)
    }
    showBulkFlagDialog.value = false
    await loadData()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    bulkFlagSaving.value = false
  }
}

// 批量修改账号属性
const BULK_ATTRIBUTE_OPTIONS = {
  account_type: [
    { label: '不修改', value: '' },
    { label: '独享号', value: 'exclusive' },
    { label: '共享号', value: 'shared' },
    { label: '人设号', value: 'persona' },
  ],
  face_mode: [
    { label: '不修改', value: '' },
    { label: '人脸', value: 'face' },
    { label: '非人脸', value: 'no_face' },
  ],
  gender: [
    { label: '不修改', value: '' },
    { label: '男', value: 'male' },
    { label: '女', value: 'female' },
    { label: '中性', value: 'unisex' },
  ],
  product_code_mode: [
    { label: '不修改', value: '' },
    { label: '带商品码', value: 'with_code' },
    { label: '非商品码', value: 'without_code' },
  ],
  account_tier: [
    { label: '不修改', value: '' },
    { label: '实验号', value: 'test' },
    { label: '常规号', value: 'dev' },
    { label: '正式号', value: 'prod' },
  ],
  hidden: [
    { label: '不修改', value: '' },
    { label: '显示', value: 'false' },
    { label: '隐藏', value: 'true' },
  ],
}

const BULK_ATTRIBUTE_FIELDS = [
  {
    key: 'account_type',
    label: '账号类型',
    tone: 'indigo',
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6"/><path d="M9 15h6"/></svg>',
  },
  {
    key: 'face_mode',
    label: '人脸',
    tone: 'cyan',
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M9 10h.01"/><path d="M15 10h.01"/><path d="M9 15c1.6 1 4.4 1 6 0"/></svg>',
  },
  {
    key: 'gender',
    label: '性别',
    tone: 'rose',
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.4-4 4.1-6 8-6s6.6 2 8 6"/></svg>',
  },
  {
    key: 'product_code_mode',
    label: '商品码',
    tone: 'emerald',
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z"/><path d="M7 7h.01"/></svg>',
  },
  {
    key: 'account_tier',
    label: '账号等级',
    tone: 'amber',
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 2 15 8.5 22 9.5l-5 4.8 1.2 7L12 17.8 5.8 21.3 7 14.3 2 9.5l7-1Z"/></svg>',
  },
  {
    key: 'hidden',
    label: '隐藏',
    tone: 'slate',
    icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
  },
]

const showBulkAttributeDialog = ref(false)
const bulkAttributeSaving = ref(false)
const bulkAttributeForm = ref({
  account_type: '',
  face_mode: '',
  gender: '',
  product_code_mode: '',
  account_tier: '',
  hidden: '',
})

function resetBulkAttributeForm() {
  bulkAttributeForm.value = {
    account_type: '',
    face_mode: '',
    gender: '',
    product_code_mode: '',
    account_tier: '',
    hidden: '',
  }
}

const bulkAttributeChangedCount = computed(() =>
  ['account_type', 'face_mode', 'gender', 'product_code_mode', 'account_tier', 'hidden']
    .filter(key => !!bulkAttributeForm.value[key]).length
)

function bulkAttributeValueLabel(key) {
  return BULK_ATTRIBUTE_OPTIONS[key]?.find(option => option.value === bulkAttributeForm.value[key])?.label || '不修改'
}

function openBulkAttributeDialog() {
  if (selectedIds.value.size === 0) {
    ElMessage.warning('请先勾选账号')
    return
  }
  resetBulkAttributeForm()
  showBulkAttributeDialog.value = true
}

function buildBulkAttributePayload() {
  const payload = { account_ids: [...selectedIds.value] }
  for (const key of ['account_type', 'face_mode', 'gender', 'product_code_mode', 'account_tier']) {
    if (bulkAttributeForm.value[key]) {
      payload[key] = bulkAttributeForm.value[key]
    }
  }
  if (bulkAttributeForm.value.hidden !== '') {
    payload.hidden = bulkAttributeForm.value.hidden === 'true'
  }
  return payload
}

async function handleBulkAttributeSubmit() {
  if (bulkAttributeSaving.value) return
  const payload = buildBulkAttributePayload()
  const changedFields = Object.keys(payload).filter(k => k !== 'account_ids')
  if (changedFields.length === 0) {
    ElMessage.warning('请选择至少一个要修改的字段')
    return
  }

  bulkAttributeSaving.value = true
  try {
    const result = await bulkUpdateAccountAttributes(payload)
    if (result.updated_count > 0) {
      ElMessage.success(`已修改 ${result.updated_count} 个账号`)
      showBulkAttributeDialog.value = false
      clearSelection()
      await loadData()
    } else {
      ElMessage.info('没有可修改的账号')
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '批量修改失败')
  } finally {
    bulkAttributeSaving.value = false
  }
}

// 多选（跨页保留）
function toggleSelectAll(checked) {
  const next = new Map(selectedMap.value)
  if (checked) {
    items.value.forEach(i => next.set(i.id, i))
  } else {
    // 只取消当前页的选中
    items.value.forEach(i => next.delete(i.id))
  }
  selectedMap.value = next
}

function toggleSelectItem(id) {
  const next = new Map(selectedMap.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    const item = items.value.find(i => i.id === id)
    if (item) next.set(id, item)
  }
  selectedMap.value = next
}

function clearSelection() {
  selectedMap.value = new Map()
}

const allSelected = computed(() =>
  items.value.length > 0 && items.value.every(i => selectedIds.value.has(i.id))
)
const someSelected = computed(() =>
  items.value.some(i => selectedIds.value.has(i.id)) && !allSelected.value
)

function syncUrl() {
  const query = {}
  if (page.value > 1) query.page = String(page.value)
  if (filterFlagId.value) query.flag_id = filterFlagId.value
  router.replace({ query })
}

function handleFilterFlag(flagId) {
  filterFlagId.value = flagId
  page.value = 1
  jumpPage.value = 1
  syncUrl()
  loadData()
}

function onSearchInput() {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => {
    page.value = 1
    jumpPage.value = 1
    loadData()
  }, 300)
}

function clearSearch() {
  searchQuery.value = ''
  page.value = 1
  jumpPage.value = 1
  loadData()
}

// AI 博主配置弹窗
const showAISettingsDialog = ref(false)
const aiSettingsLoading = ref(false)
const aiSettingsSaving = ref(false)
const aiSettingsForm = ref({
  _pipeline: null,
  ai_account_analysis_sample_size: 10,
  ai_account_video_prompt: '',
  ai_account_video_model: 'gemini-3.1-pro-preview',
  ai_account_name_prompt: '',
  ai_account_name_model: 'gemini-3.1-pro-preview',
  ai_account_avatar_prompt: '',
  ai_account_avatar_model: 'gemini-3.1-flash-image-preview',
  ai_account_avatar_size: '1:1',
  ai_account_avatar_quality: '1K',
  ai_account_photo_image_prompt: '',
  ai_account_exclusive_name_prompt: '',
  ai_account_shared_name_prompt: '',
  hashtag_search_top_n: 100,
  hashtag_filter_model: 'gemini-3.1-pro-preview',
  hashtag_filter_prompt: '',
  video_classify_model: 'gemini-3.1-pro-preview',
  video_classify_prompt: '',
  video_classify_temperature: 0.7,
  classify_min_sample: 3,
  classify_beauty_threshold_pct: 75,
  classify_method_threshold_pct: 60,
  classify_shopping_threshold_pct: 55,
  classify_lifestyle_threshold_pct: 55,
  classify_drama_threshold_pct: 65,
  classify_dual_combined_threshold_pct: 80,
  tier_video_sample_count: 7,
  tier_avg_play_threshold: 700,
  tier_activity_days: 7,
  tier_min_video_count: 6,
  tier_daily_formal_growth_min_rate: 0.0,
  tier_daily_formal_growth_max_rate: 0.06,
  sub_task_success_sample_size: 10,
})

async function openAISettings() {
  showAISettingsDialog.value = true
  aiSettingsLoading.value = true
  try {
    const data = await fetchPipelineSettings()
    aiSettingsForm.value._pipeline = data
    aiSettingsForm.value.ai_account_analysis_sample_size = data.ai_account_analysis_sample_size ?? 10
    aiSettingsForm.value.ai_account_video_prompt = data.ai_account_video_prompt || ''
    aiSettingsForm.value.ai_account_video_model = data.ai_account_video_model || 'gemini-3.1-pro-preview'
    aiSettingsForm.value.ai_account_name_prompt = data.ai_account_name_prompt || ''
    aiSettingsForm.value.ai_account_name_model = data.ai_account_name_model || 'gemini-3.1-pro-preview'
    aiSettingsForm.value.ai_account_avatar_prompt = data.ai_account_avatar_prompt || ''
    aiSettingsForm.value.ai_account_avatar_model = data.ai_account_avatar_model || 'gemini-3.1-flash-image-preview'
    aiSettingsForm.value.ai_account_avatar_size = data.ai_account_avatar_size || '1:1'
    aiSettingsForm.value.ai_account_avatar_quality = data.ai_account_avatar_quality || '1K'
    aiSettingsForm.value.ai_account_photo_image_prompt = data.ai_account_photo_image_prompt || ''
    aiSettingsForm.value.ai_account_exclusive_name_prompt = data.ai_account_exclusive_name_prompt || ''
    aiSettingsForm.value.ai_account_shared_name_prompt = data.ai_account_shared_name_prompt || ''
    aiSettingsForm.value.hashtag_search_top_n = data.hashtag_search_top_n ?? 100
    aiSettingsForm.value.hashtag_filter_model = data.hashtag_filter_model || 'gemini-3.1-pro-preview'
    aiSettingsForm.value.hashtag_filter_prompt = data.hashtag_filter_prompt || ''
    aiSettingsForm.value.video_classify_model = data.video_classify_model || 'gemini-3.1-pro-preview'
    aiSettingsForm.value.video_classify_prompt = data.video_classify_prompt || ''
    aiSettingsForm.value.video_classify_temperature = data.video_classify_temperature ?? 0.7
    aiSettingsForm.value.classify_min_sample = data.classify_min_sample ?? 3
    aiSettingsForm.value.classify_beauty_threshold_pct = Math.round((data.classify_beauty_threshold ?? 0.75) * 100)
    aiSettingsForm.value.classify_method_threshold_pct = Math.round((data.classify_method_threshold ?? 0.60) * 100)
    aiSettingsForm.value.classify_shopping_threshold_pct = Math.round((data.classify_shopping_threshold ?? 0.55) * 100)
    aiSettingsForm.value.classify_lifestyle_threshold_pct = Math.round((data.classify_lifestyle_threshold ?? 0.55) * 100)
    aiSettingsForm.value.classify_drama_threshold_pct = Math.round((data.classify_drama_threshold ?? 0.65) * 100)
    aiSettingsForm.value.classify_dual_combined_threshold_pct = Math.round((data.classify_dual_combined_threshold ?? 0.80) * 100)
    aiSettingsForm.value.tier_video_sample_count = data.tier_video_sample_count ?? 7
    aiSettingsForm.value.tier_avg_play_threshold = data.tier_avg_play_threshold ?? 700
    aiSettingsForm.value.tier_activity_days = data.tier_activity_days ?? 7
    aiSettingsForm.value.tier_min_video_count = data.tier_min_video_count ?? 6
    aiSettingsForm.value.tier_daily_formal_growth_min_rate = data.tier_daily_formal_growth_min_rate ?? 0.0
    aiSettingsForm.value.tier_daily_formal_growth_max_rate = data.tier_daily_formal_growth_max_rate ?? 0.06
    aiSettingsForm.value.sub_task_success_sample_size = data.sub_task_success_sample_size ?? 10
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '加载配置失败')
  } finally {
    aiSettingsLoading.value = false
  }
}

async function saveAISettings() {
  if (aiSettingsSaving.value) return
  aiSettingsSaving.value = true
  try {
    const base = aiSettingsForm.value._pipeline || {}
    const payload = {
      ...base,
      ai_account_analysis_sample_size: aiSettingsForm.value.ai_account_analysis_sample_size,
      ai_account_video_prompt: aiSettingsForm.value.ai_account_video_prompt,
      ai_account_video_model: aiSettingsForm.value.ai_account_video_model,
      ai_account_name_prompt: aiSettingsForm.value.ai_account_name_prompt,
      ai_account_name_model: aiSettingsForm.value.ai_account_name_model,
      ai_account_avatar_prompt: aiSettingsForm.value.ai_account_avatar_prompt,
      ai_account_avatar_model: aiSettingsForm.value.ai_account_avatar_model,
      ai_account_avatar_size: aiSettingsForm.value.ai_account_avatar_size,
      ai_account_avatar_quality: aiSettingsForm.value.ai_account_avatar_quality,
      ai_account_photo_image_prompt: aiSettingsForm.value.ai_account_photo_image_prompt,
      ai_account_exclusive_name_prompt: aiSettingsForm.value.ai_account_exclusive_name_prompt,
      ai_account_shared_name_prompt: aiSettingsForm.value.ai_account_shared_name_prompt,
      hashtag_search_top_n: aiSettingsForm.value.hashtag_search_top_n,
      hashtag_filter_model: aiSettingsForm.value.hashtag_filter_model,
      hashtag_filter_prompt: aiSettingsForm.value.hashtag_filter_prompt,
      video_classify_model: aiSettingsForm.value.video_classify_model,
      video_classify_prompt: aiSettingsForm.value.video_classify_prompt,
      video_classify_temperature: aiSettingsForm.value.video_classify_temperature,
      classify_min_sample: aiSettingsForm.value.classify_min_sample,
      classify_beauty_threshold: (aiSettingsForm.value.classify_beauty_threshold_pct ?? 75) / 100,
      classify_method_threshold: (aiSettingsForm.value.classify_method_threshold_pct ?? 60) / 100,
      classify_shopping_threshold: (aiSettingsForm.value.classify_shopping_threshold_pct ?? 55) / 100,
      classify_lifestyle_threshold: (aiSettingsForm.value.classify_lifestyle_threshold_pct ?? 55) / 100,
      classify_drama_threshold: (aiSettingsForm.value.classify_drama_threshold_pct ?? 65) / 100,
      classify_dual_combined_threshold: (aiSettingsForm.value.classify_dual_combined_threshold_pct ?? 80) / 100,
      tier_video_sample_count: aiSettingsForm.value.tier_video_sample_count,
      tier_avg_play_threshold: aiSettingsForm.value.tier_avg_play_threshold,
      tier_activity_days: aiSettingsForm.value.tier_activity_days,
      tier_min_video_count: aiSettingsForm.value.tier_min_video_count,
      tier_daily_formal_growth_min_rate: aiSettingsForm.value.tier_daily_formal_growth_min_rate,
      tier_daily_formal_growth_max_rate: aiSettingsForm.value.tier_daily_formal_growth_max_rate,
      sub_task_success_sample_size: aiSettingsForm.value.sub_task_success_sample_size,
    }
    await updatePipelineSettings(payload)
    ElMessage.success('配置已保存')
    showAISettingsDialog.value = false
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '保存失败')
  } finally {
    aiSettingsSaving.value = false
  }
}

// ── 账号分级重判预览 / 应用 ──────────────────────────────────────────────────
const showTierEvalPreviewDialog = ref(false)
const tierEvalPreviewLoading = ref(false)
const tierEvalApplying = ref(false)
const tierEvalChanges = ref([])
const tierEvalSummary = ref({ promote_to_dev: 0, demote_to_test: 0, total: 0 })

function tierLabel(tier) {
  return { test: '实验号', dev: '常规号', prod: '正式号' }[tier] || tier
}

async function openTierEvalPreview() {
  if (tierEvalPreviewLoading.value) return
  tierEvalPreviewLoading.value = true
  try {
    const data = await previewTierEvaluation()
    tierEvalChanges.value = data.changes || []
    tierEvalSummary.value = data.summary || { promote_to_dev: 0, demote_to_test: 0, total: 0 }
    showTierEvalPreviewDialog.value = true
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '预览失败')
  } finally {
    tierEvalPreviewLoading.value = false
  }
}

async function applyTierEvalChanges() {
  if (tierEvalApplying.value) return
  if (tierEvalChanges.value.length === 0) {
    showTierEvalPreviewDialog.value = false
    return
  }
  tierEvalApplying.value = true
  try {
    const res = await applyTierEvaluation(tierEvalChanges.value)
    ElMessage.success(`已应用：升 ${res.promoted} 降 ${res.demoted}（跳过 ${res.skipped}）`)
    showTierEvalPreviewDialog.value = false
    await loadData()  // 刷新列表展示新 tier
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '应用失败')
  } finally {
    tierEvalApplying.value = false
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const startIdx = computed(() => total.value === 0 ? 0 : (page.value - 1) * pageSize.value + 1)
const endIdx = computed(() => Math.min(page.value * pageSize.value, total.value))
const jumpPage = ref(page.value)

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

function platformLabel(p) { return PLATFORM_LABELS[p] || p }
function bindingDisplayLabel(binding) {
  const platform = platformLabel(binding.platform)
  const channelName = binding.channel_name?.trim()
  const channelId = binding.channel_id?.trim()
  return channelName ? `${platform} · ${channelName}` : channelId ? `${platform} · ${channelId}` : platform
}
function boundChannelReservations(item) {
  return (item.channel_reservations || []).filter(r => r?.status === 'bound')
}
function unboundChannelReservations(item) {
  return (item.channel_reservations || []).filter(r => r?.platform && r?.status !== 'bound')
}
function reservationBoundLabel(reservation) {
  const platform = platformLabel(reservation.platform)
  const channelName = reservation.channel_name?.trim()
  const channelId = reservation.channel_id?.trim()
  return channelName ? `${platform} · ${channelName}` : channelId ? `${platform} · ${channelId}` : platform
}
function reservationDisplayLabel(reservation) {
  const platform = platformLabel(reservation.platform)
  const statusMap = { reserved: '已占位', confirmed: '已确认', bound: '已绑定' }
  return `${platform} · ${statusMap[reservation.status] || reservation.status || '已占位'}`
}
function snapshotValue(item, key) {
  return item?.performance_snapshot?.[key]
}
// 列表里 KOL 短链列：返回所有带 long_link/short_link 的 reservation
// 排序优先 youtube → tiktok → instagram → 其它
const _KOL_PLATFORM_ORDER = ['youtube', 'tiktok', 'instagram']
function kolReservationLinks(item) {
  const reservations = (item?.channel_reservations || []).filter(
    r => r?.kol_short_link || r?.kol_long_link
  )
  reservations.sort((a, b) => {
    const ia = _KOL_PLATFORM_ORDER.indexOf(a.platform)
    const ib = _KOL_PLATFORM_ORDER.indexOf(b.platform)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })
  return reservations.map(r => ({
    id: r.id,
    platform: r.platform,
    short: r.kol_short_link || '',
    long: r.kol_long_link || '',
  }))
}

function kolPlatformShort(platform) {
  return { youtube: 'YT', tiktok: 'TT', instagram: 'IG' }[platform] || (platform || '').slice(0, 2).toUpperCase()
}

function aiGenerationStatusLabel(status) {
  const map = {
    pending: '排队中',
    video_analyzing: '分析视频',
    name_generating: '生成名称',
    photo_generating: '生成照片候选',
    awaiting_photo_selection: '待选照片',
    avatar_generating: '生成头像',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

function supplementStatusLabel(status) {
  const map = {
    running: '补充中',
    completed: '补充完成',
    failed: '补充失败',
  }
  return map[status] || status
}

function supplementModeLabel(mode) {
  const map = {
    auto: '自动补充',
    exclusive: '人设补充',
    shared: '共享补充',
  }
  return map[mode] || mode
}

function formatCount(value) {
  if (value == null || value === '') return '-'
  const n = Number(value)
  if (Number.isNaN(n)) return String(value)
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

function formatPercent(value) {
  if (value == null || value === '') return '-'
  const n = Number(value)
  if (Number.isNaN(n)) return String(value)
  return `${n.toFixed(1)}%`
}

function formatSnapshotDate(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

function previewMedia(item, type) {
  const isAvatar = type === 'avatar'
  const url = isAvatar ? item.avatar_url : item.photo_url
  if (!url) return
  previewImage.value = {
    url,
    title: `${item.account_name}${isAvatar ? '头像' : '照片'}`
  }
  previewVisible.value = true
}

function goToDetail(item) {
  openInNewTab(`/dashboard/accounts/${item.id}`)
}

async function loadData({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filterFlagId.value) params.flag_id = filterFlagId.value
    if (searchQuery.value.trim()) params.search = searchQuery.value.trim()
    if (sortBy.value) { params.sort_by = sortBy.value; params.sort_order = sortOrder.value }
    if (filterGender.value) params.gender = filterGender.value
    if (filterAccountType.value) params.account_type = filterAccountType.value
    if (filterFaceMode.value) params.face_mode = filterFaceMode.value
    if (filterProductCodeMode.value) params.product_code_mode = filterProductCodeMode.value
    if (filterAccountTier.value) params.account_tier = filterAccountTier.value
    if (filterPlatformBindingStatus.value) params.platform_binding_status = filterPlatformBindingStatus.value
    if (filterClassificationType.value) params.classification_type = filterClassificationType.value
    if (filterCategoryIndices.value.length > 0) params.category_keys = filterCategoryIndices.value.join(',')
    const data = await fetchAccounts(params)
    items.value = data.items || []
    total.value = data.total || 0
  } catch (err) {
    if (isDuplicateRequestError(err)) return
    ElMessage.error(err?.response?.data?.detail || '加载失败')
  } finally {
    if (!silent) loading.value = false
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

function openBulkContinueDialog() {
  if (bulkRestarting.value) return
  showBulkContinueDialog.value = true
}

async function handleBulkContinueAIGeneration() {
  if (bulkRestarting.value) return

  bulkRestarting.value = true
  try {
    const ids = selectedMap.value.size > 0 ? [...selectedMap.value.keys()] : null
    const result = await bulkResumeAIAccountGeneration(bulkResumeStage.value, ids)
    if (result.status === 'no_accounts') {
      ElMessage.info(
        bulkResumeStage.value === 'current'
          ? '没有可继续的 AI 博主任务'
          : '没有找到可从该阶段重跑的 AI 博主'
      )
      return
    }
    ElMessage.success(`已继续 ${result.resumed_count || 0} 个任务，跳过 ${result.skipped_count || 0} 个`)
    showBulkContinueDialog.value = false
    await loadData()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '一键继续失败')
  } finally {
    bulkRestarting.value = false
  }
}

async function handleBulkGenerateAIAccounts() {
  if (bulkGenerating.value) return

  try {
    await ElMessageBox.confirm(
      '将根据"已有关联视频、但尚未绑定任何 AI 博主账号"的标签批量创建账号，并统一进入后端队列排队生成。确定继续？',
      '确认生成',
      { confirmButtonText: '开始生成', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  bulkGenerating.value = true
  try {
    const result = await bulkGenerateAIAccounts()
    if (result.status === 'no_tags') {
      ElMessage.info('没有可生成的标签，所有有视频的标签都已绑定 AI 博主')
      return
    }
    ElMessage.success(`已创建并入队 ${result.created_count || 0} 个 AI 博主`)
    await loadData()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '一键生成失败')
  } finally {
    bulkGenerating.value = false
  }
}

function bloggerTaggingTitle(blogger) {
  const statusMap = { pending: '打标排队中', running: '打标进行中', success: '打标完成', failed: '打标失败' }
  return statusMap[blogger.tagging_status] || blogger.tagging_status
}

// ── 人设打标进度 dialog ──────────────────────────────────────────────────────
const showTaggingProgressDialog = ref(false)
const taggingProgressBlogger = ref(null)
const taggingProgressData = ref(null)
const taggingProgressLoading = ref(false)
const taggingProgressStarting = ref(false)
let _taggingProgressPollTimer = null
let _taggingProgressPollSeq = 0

function taggingStatusLabel(status) {
  const map = {
    not_started: '未开始',
    pending: '排队中',
    checking_videos: '检查视频',
    waiting_videos: '等待视频打标',
    aggregating: '聚合中',
    running: '进行中',
    success: '打标完成',
    failed: '打标失败',
  }
  return map[status] || status || '未开始'
}

const videoStageClass = computed(() => {
  const s = taggingProgressData.value?.summary
  if (!s) return 'is-not_started'
  if (s.running > 0 || s.pending > 0) return 'is-running'
  if (s.success > 0 && s.failed === 0 && s.pending === 0 && s.running === 0) return 'is-success'
  if (s.failed > 0 && s.pending === 0 && s.running === 0) return 'is-partial'
  if (s.success > 0) return 'is-partial'
  return 'is-not_started'
})

const aggregateStageDesc = computed(() => {
  const bs = taggingProgressData.value?.blogger_status
  const map = {
    not_started: '等待视频完成',
    pending: '排队中',
    checking_videos: '检查视频数量...',
    waiting_videos: '等待视频打标完成...',
    aggregating: '正在聚合博主标签...',
    success: '聚合完成',
    failed: '聚合失败',
  }
  return map[bs] || '等待中'
})

const writebackStageClass = computed(() => {
  const wb = taggingProgressData.value?.writeback_status
  const bs = taggingProgressData.value?.blogger_status
  if (bs !== 'success') return 'is-not_started'
  if (!wb || wb === 'idle') return 'is-not_started'
  if (wb === 'pending' || wb === 'running') return 'is-running'
  if (wb === 'success') return taggingProgressData.value?.writeback_done ? 'is-success' : 'is-partial'
  if (wb === 'failed') return 'is-failed'
  return 'is-not_started'
})

const writebackStageDesc = computed(() => {
  const wb = taggingProgressData.value?.writeback_status
  const bs = taggingProgressData.value?.blogger_status
  const done = taggingProgressData.value?.writeback_done
  if (bs !== 'success') return '等待中'
  if (wb === 'running') return '写回中...'
  if (wb === 'success' && done) return '已写回博主标签'
  if (wb === 'success' && !done) return '写回未完成'
  if (wb === 'pending') return '写回中...'
  if (wb === 'failed') return '写回失败'
  return '等待中'
})

const aggregateStageClass = computed(() => {
  const wb = taggingProgressData.value?.writeback_status
  const bs = taggingProgressData.value?.blogger_status
  if (!bs || bs === 'not_started') return 'is-not_started'
  if (bs === 'aggregating' || bs === 'checking_videos' || wb === 'running') return 'is-running'
  if (bs === 'waiting_videos' || bs === 'pending') return 'is-pending'
  if (bs === 'success') return 'is-success'
  if (bs === 'failed') return 'is-failed'
  return 'is-not_started'
})

function videoTaggingStatusLabel(status) {
  const map = {
    not_started: '未开始',
    pending: '排队',
    running: '处理中',
    success: '完成',
    failed: '失败',
  }
  return map[status] || status
}

function _clearTaggingProgressPoll() {
  if (_taggingProgressPollTimer) clearTimeout(_taggingProgressPollTimer)
  _taggingProgressPollTimer = null
  _taggingProgressPollSeq++
}

function _shouldKeepTaggingPoll() {
  const d = taggingProgressData.value
  if (!d) return false
  if (d.is_active) return true
  const s = d.summary
  if (s && (s.running > 0 || s.pending > 0)) return true
  // 视频都完成了但博主还在聚合/写回，继续轮询
  if (d.writeback_status === 'pending') return true
  return false
}

async function _refreshTaggingProgress() {
  if (!taggingProgressBlogger.value) return
  const bloggerId = taggingProgressBlogger.value.id
  try {
    const res = await fetchBloggerTaggingProgress(bloggerId)
    if (!taggingProgressBlogger.value || taggingProgressBlogger.value.id !== bloggerId) return
    taggingProgressData.value = res.data
  } catch (e) {
    // 静默失败，不打断轮询
  }
}

function _scheduleTaggingPoll() {
  _clearTaggingProgressPoll()
  if (!showTaggingProgressDialog.value) return
  if (!_shouldKeepTaggingPoll()) return
  const seq = ++_taggingProgressPollSeq
  _taggingProgressPollTimer = setTimeout(async () => {
    if (seq !== _taggingProgressPollSeq) return
    if (!showTaggingProgressDialog.value) return
    await _refreshTaggingProgress()
    _scheduleTaggingPoll()
  }, 3000)
}

async function openTaggingProgress(blogger) {
  taggingProgressBlogger.value = blogger
  taggingProgressData.value = null
  showTaggingProgressDialog.value = true
  taggingProgressLoading.value = true
  try {
    const res = await fetchBloggerTaggingProgress(blogger.id)
    taggingProgressData.value = res.data
  } catch (e) {
    ElMessage.error('加载打标进度失败')
  } finally {
    taggingProgressLoading.value = false
  }
  _scheduleTaggingPoll()
}

function closeTaggingProgressDialog() {
  _clearTaggingProgressPoll()
  taggingProgressBlogger.value = null
  taggingProgressData.value = null
  showTaggingProgressDialog.value = false
}

async function handleRestartTagging() {
  if (!taggingProgressBlogger.value) return
  const isRestart = taggingProgressData.value?.blogger_status === 'success'
  if (isRestart) {
    try {
      await ElMessageBox.confirm(
        '将清除该博主所有视频的已有打标结果，从头重新打标。确定继续？',
        '确认重新打标',
        { confirmButtonText: '确定重打', cancelButtonText: '取消', type: 'warning' }
      )
    } catch { return }
  }
  taggingProgressStarting.value = true
  try {
    await submitBloggerTagging(taggingProgressBlogger.value.id, { force: isRestart })
    ElMessage.success(isRestart ? '已清除旧结果并入队重新打标' : '已入队打标')
    await _refreshTaggingProgress()
    _scheduleTaggingPoll()
    await loadData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    taggingProgressStarting.value = false
  }
}

function topStyles(styleVector, n = 3) {
  if (!styleVector) return {}
  return Object.fromEntries(
    Object.entries(styleVector)
      .filter(([, v]) => v > 0)
      .sort(([, a], [, b]) => b - a)
      .slice(0, n)
  )
}

function allStyles(styleVector) {
  if (!styleVector) return {}
  return Object.fromEntries(
    Object.entries(styleVector)
      .filter(([, v]) => v > 0)
      .sort(([, a], [, b]) => b - a)
  )
}

const showPersonaTagConfirmDialog = ref(false)
const personaTagConfirmIds = ref([])
const personaTagForce = ref(false)

function handleBulkPersonaTagging() {
  if (personaTagging.value) return
  personaTagConfirmIds.value = selectedMap.value.size > 0 ? [...selectedMap.value.keys()] : []
  personaTagForce.value = false
  showPersonaTagConfirmDialog.value = true
}

async function confirmPersonaTagging() {
  personaTagging.value = true
  try {
    const accountIds = personaTagConfirmIds.value
    const result = await bulkPersonaTagging(accountIds.length ? accountIds : null, personaTagForce.value)
    showPersonaTagConfirmDialog.value = false
    ElMessage.success(result.message || `已为 ${result.queued} 个博主入队打标`)
    await loadData()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '人设打标失败')
  } finally {
    personaTagging.value = false
  }
}

async function handleDelete(item) {
  try {
    await ElMessageBox.confirm(
      `确定删除账号「${item.account_name}」？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning', customClass: 'premium-delete-dialog' }
    )
  } catch { return }

  deleting.value = item.id
  try {
    await deleteAccount(item.id)
    ElMessage.success('已删除')
    await loadData()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  } finally {
    deleting.value = null
  }
}

async function toggleFaceMode(item) {
  const newMode = item.face_mode === 'no_face' ? 'face' : 'no_face'
  try {
    await patchAccount(item.id, { face_mode: newMode })
    item.face_mode = newMode
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '切换失败')
  }
}

const GENDER_CYCLE = ['male', 'female', 'unisex']
async function cycleGender(item) {
  const current = item.gender || 'female'
  const next = GENDER_CYCLE[(GENDER_CYCLE.indexOf(current) + 1) % GENDER_CYCLE.length]
  try {
    await patchAccount(item.id, { gender: next })
    item.gender = next
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '切换失败')
  }
}

// ── 一键生成 ────────────────────────────────────────────────────────────────

const bulkVideoGenerating = ref(false)
const bulkVideoGenProgress = ref({ current: 0, total: 0 })
const showBulkGenDialog = ref(false)
const bulkGenForm = ref({ mode: 'unused', fill_mode: 'count', limit: 5, subtaskCount: 1 })


function handleBulkVideoGenerate() {
  if (bulkVideoGenerating.value) return
  bulkGenForm.value = { mode: 'unused', fill_mode: 'count', limit: 5, subtaskCount: 1 }
  showBulkGenDialog.value = true
}

async function startBulkVideoGenerate() {
  const { mode, limit, fill_mode } = bulkGenForm.value
  if (fill_mode === 'target_total' && limit <= 0) {
    ElMessage.warning('"补充到 X 个" 模式下数量必须大于 0')
    return
  }
  showBulkGenDialog.value = false
  bulkVideoGenerating.value = true

  try {
    const isSelection = selectedMap.value.size > 0
    let accountIds = []
    let filters = null

    if (isSelection) {
      accountIds = [...selectedMap.value.values()].map(a => a.id)
    } else {
      filters = {}
      if (filterGender.value) filters.gender = filterGender.value
      if (filterAccountType.value) filters.account_type = filterAccountType.value
      if (filterFaceMode.value) filters.face_mode = filterFaceMode.value
      if (filterProductCodeMode.value) filters.product_code_mode = filterProductCodeMode.value
      if (filterAccountTier.value) filters.account_tier = filterAccountTier.value
      if (filterPlatformBindingStatus.value) filters.platform_binding_status = filterPlatformBindingStatus.value
      if (filterClassificationType.value) filters.classification_type = filterClassificationType.value
      if (filterCategoryIndices.value.length > 0) filters.category_keys = filterCategoryIndices.value
      if (filterFlagId.value) filters.flag_id = filterFlagId.value
      if (searchQuery.value.trim()) filters.search = searchQuery.value.trim()
    }

    const result = await bulkGenerateVideoTasks(accountIds, mode, limit, bulkGenForm.value.subtaskCount, fill_mode, filters)
    const skipMsg = result.skipped_accounts > 0 ? `，${result.skipped_accounts} 个账号无可用模板` : ''
    ElMessage.success(result.message || `后台已启动，预计创建 ${result.planned || 0} 个生成任务${skipMsg}`)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '一键生成失败')
  } finally {
    bulkVideoGenerating.value = false
  }
}

// ── 一键定时 ────────────────────────────────────────────────────────────────

const CRON_PRESETS = [
  { label: '每天8点',    cron: '0 8 * * *' },
  { label: '每天10点',   cron: '0 10 * * *' },
  { label: '每天12点',   cron: '0 12 * * *' },
  { label: '每天20点',   cron: '0 20 * * *' },
  { label: '隔天10点',   cron: '0 10 */2 * *' },
  { label: '每周一10点', cron: '0 10 * * 1' },
]

const showBulkScheduleDialog = ref(false)
const savingBulkSchedule = ref(false)
const bulkScheduleForm = ref({
  publish_cron: '',
  publish_window_minutes: 0,
  publish_count: 1,
})

const bulkSchedulePreview = computed(() => {
  const cron = bulkScheduleForm.value.publish_cron?.trim()
  if (!cron) return '请先选择快捷规则或输入 Cron 表达式'
  const preset = CRON_PRESETS.find(p => p.cron === cron)
  const label = preset ? preset.label : `Cron: ${cron}`
  const win = bulkScheduleForm.value.publish_window_minutes
  const count = bulkScheduleForm.value.publish_count
  const winStr = win > 0 ? `，到点后随机延迟最多 ${win} 分钟` : ''
  return `${label}${winStr}，每次发布 ${count} 个视频（按队列顺序）`
})

function openBulkScheduleDialog() {
  bulkScheduleForm.value = { publish_cron: '', publish_window_minutes: 0, publish_count: 1 }
  showBulkScheduleDialog.value = true
}

async function handleBulkSchedule() {
  if (savingBulkSchedule.value) return
  if (!bulkScheduleForm.value.publish_cron?.trim()) {
    ElMessage.warning('请先设置 Cron 表达式')
    return
  }

  savingBulkSchedule.value = true

  const isSelection = selectedMap.value.size > 0
  const accountIds = isSelection ? [...selectedMap.value.values()].map(a => a.id) : []
  let filters = null
  if (!isSelection) {
    filters = {}
    if (filterGender.value) filters.gender = filterGender.value
    if (filterAccountType.value) filters.account_type = filterAccountType.value
    if (filterFaceMode.value) filters.face_mode = filterFaceMode.value
    if (filterProductCodeMode.value) filters.product_code_mode = filterProductCodeMode.value
    if (filterAccountTier.value) filters.account_tier = filterAccountTier.value
    if (filterPlatformBindingStatus.value) filters.platform_binding_status = filterPlatformBindingStatus.value
    if (filterClassificationType.value) filters.classification_type = filterClassificationType.value
    if (filterCategoryIndices.value.length > 0) filters.category_keys = filterCategoryIndices.value
    if (filterFlagId.value) filters.flag_id = filterFlagId.value
    if (searchQuery.value.trim()) filters.search = searchQuery.value.trim()
  }

  try {
    const result = await bulkUpdateScheduledPublish(accountIds, {
      publish_enabled: true,
      publish_cron: bulkScheduleForm.value.publish_cron,
      publish_window_minutes: bulkScheduleForm.value.publish_window_minutes,
      publish_count: bulkScheduleForm.value.publish_count,
    }, filters)
    ElMessage.success(`已为 ${result.updated_count} 个账号设置定时发布`)
    showBulkScheduleDialog.value = false
    await loadData({ silent: true })
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '批量定时失败')
  } finally {
    savingBulkSchedule.value = false
  }
}


// ── 补充模板 ────────────────────────────────────────────────────────────────

const showSupplementDialog = ref(false)
const supplementing = ref(false)
const supplementForm = ref({
  templateType: 'shared',
  targetUnusedTemplateCount: 10,
  minViewCount: 10000,
  publishedAfter: '2024-01-01',
  maxDurationSeconds: 30,
  categoryKeys: [],
})
const showSupplementScheduleDialog = ref(false)
const supplementScheduleSaving = ref(false)
const supplementSchedulePresets = [
  { label: '每天10点', cron: '0 10 * * *' },
  { label: '每天18点', cron: '0 18 * * *' },
  { label: '每6小时', cron: '0 */6 * * *' },
]
const supplementScheduleForm = ref({
  enabled: false,
  cron: '0 10 * * *',
  targetUnusedTemplateCount: 10,
  minViewCount: 10000,
  publishedAfter: '2024-01-01',
  maxDurationSeconds: 30,
  categoryKeys: [],
  maxRounds: 2,
})
const scheduledGenerationPresets = [
  { label: '每天10点', cron: '0 10 * * *' },
  { label: '每天18点', cron: '0 18 * * *' },
  { label: '每6小时', cron: '0 */6 * * *' },
]
const scheduledGenerationMajorKeys = ['beauty', 'method', 'shopping', 'lifestyle', 'drama']
const showScheduledGenerationDialog = ref(false)
const scheduledGenerationSaving = ref(false)

function buildScheduledGenerationRules(raw = {}) {
  return scheduledGenerationMajorKeys.reduce((acc, major) => {
    const item = raw?.[major] || {}
    acc[major] = {
      enabled: Boolean(item.enabled),
      min_views: Number(item.min_views ?? 5000),
      repeat_count: Number(item.repeat_count ?? 3),
    }
    return acc
  }, {})
}

const scheduledGenerationForm = ref({
  enabled: false,
  cron: '0 10 * * *',
  lookbackDays: 2,
  targetUnpublishedCount: 5,
  subtaskCount: 1,
  unusedTemplateMonths: 3,
  usedTemplateCooldownDays: 30,
  categoryRules: buildScheduledGenerationRules(),
})

function openSupplementDialog() {
  supplementForm.value = {
    templateType: 'shared',
    targetUnusedTemplateCount: 10,
    minViewCount: 10000,
    publishedAfter: '2024-01-01',
    maxDurationSeconds: 30,
    categoryKeys: [],
  }
  showSupplementDialog.value = true
}

function toggleSupplementCategory(key) {
  const values = supplementForm.value.categoryKeys || []
  if (values.includes(key)) {
    supplementForm.value.categoryKeys = values.filter(v => v !== key)
  } else {
    supplementForm.value.categoryKeys = [...values, key]
  }
}

function toggleSupplementScheduleCategory(key) {
  const values = supplementScheduleForm.value.categoryKeys || []
  if (values.includes(key)) {
    supplementScheduleForm.value.categoryKeys = values.filter(v => v !== key)
  } else {
    supplementScheduleForm.value.categoryKeys = [...values, key]
  }
}

function buildSupplementFiltersFromForm(form, includeCategories = true) {
  return {
    min_view_count: form.minViewCount,
    published_after: form.publishedAfter,
    max_duration_seconds: form.maxDurationSeconds,
    category_keys: includeCategories ? [...(form.categoryKeys || [])] : [],
  }
}

async function handleSupplement() {
  if (supplementing.value) return
  supplementing.value = true

  const isSelection = selectedMap.value.size > 0
  const accountIds = isSelection ? [...selectedMap.value.keys()] : []
  let accountListFilters = null
  if (!isSelection) {
    accountListFilters = {}
    if (filterGender.value) accountListFilters.gender = filterGender.value
    if (filterAccountType.value) accountListFilters.account_type = filterAccountType.value
    if (filterFaceMode.value) accountListFilters.face_mode = filterFaceMode.value
    if (filterProductCodeMode.value) accountListFilters.product_code_mode = filterProductCodeMode.value
    if (filterAccountTier.value) accountListFilters.account_tier = filterAccountTier.value
    if (filterPlatformBindingStatus.value) accountListFilters.platform_binding_status = filterPlatformBindingStatus.value
    if (filterClassificationType.value) accountListFilters.classification_type = filterClassificationType.value
    if (filterCategoryIndices.value.length > 0) accountListFilters.category_keys = filterCategoryIndices.value
  }

  // shared 模式不使用弹窗过滤条件（走内部 pipeline_settings 默认）
  const filters = supplementForm.value.templateType === 'shared'
    ? null
    : buildSupplementFiltersFromForm(supplementForm.value, supplementForm.value.templateType === 'exclusive')
  const target = supplementForm.value.targetUnusedTemplateCount
  try {
    let result
    if (supplementForm.value.templateType === 'auto') {
      result = await autoSupplementTemplates(accountIds, target, filters, accountListFilters)
    } else {
      result = await supplementTemplates(
        accountIds,
        supplementForm.value.templateType,
        target,
        filters,
        accountListFilters,
      )
    }
    showSupplementDialog.value = false
    ElMessage.success(result.message || '已启动补充模板任务')
    await loadData({ silent: true })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '启动补充模板失败')
  } finally {
    supplementing.value = false
  }
}

async function openSupplementScheduleDialog() {
  try {
    const data = await fetchTemplateSupplementConfig()
    const filters = data.template_supplement_filters || {}
    supplementScheduleForm.value = {
      enabled: data.template_supplement_schedule_enabled ?? false,
      cron: data.template_supplement_schedule_cron || '0 10 * * *',
      targetUnusedTemplateCount: data.template_supplement_target_unused_count || 10,
      minViewCount: filters.min_view_count ?? 10000,
      publishedAfter: filters.published_after || '2024-01-01',
      maxDurationSeconds: filters.max_duration_seconds ?? 30,
      categoryKeys: Array.isArray(filters.category_keys) ? filters.category_keys : [],
      maxRounds: data.template_supplement_max_rounds || 2,
    }
    showSupplementScheduleDialog.value = true
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '加载定时补充配置失败')
  }
}

async function saveSupplementSchedule() {
  if (supplementScheduleSaving.value) return
  supplementScheduleSaving.value = true
  try {
    await updateTemplateSupplementConfig({
      template_supplement_schedule_enabled: supplementScheduleForm.value.enabled,
      template_supplement_schedule_cron: supplementScheduleForm.value.cron || '0 10 * * *',
      template_supplement_target_unused_count: supplementScheduleForm.value.targetUnusedTemplateCount,
      template_supplement_filters: buildSupplementFiltersFromForm(supplementScheduleForm.value, true),
      template_supplement_max_rounds: supplementScheduleForm.value.maxRounds || 2,
    })
    showSupplementScheduleDialog.value = false
    ElMessage.success(supplementScheduleForm.value.enabled ? '定时补充已启用' : '定时补充已关闭')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '保存定时补充配置失败')
  } finally {
    supplementScheduleSaving.value = false
  }
}

async function openScheduledGenerationDialog() {
  try {
    const data = await fetchScheduledGenerationConfig()
    scheduledGenerationForm.value = {
      enabled: data.scheduled_generation_enabled ?? false,
      cron: data.scheduled_generation_cron || '0 10 * * *',
      lookbackDays: data.scheduled_generation_lookback_days || 2,
      targetUnpublishedCount: data.scheduled_generation_target_unpublished_count || 5,
      subtaskCount: data.scheduled_generation_subtask_count || 1,
      unusedTemplateMonths: data.scheduled_generation_unused_template_months || 3,
      usedTemplateCooldownDays: data.scheduled_generation_used_template_cooldown_days ?? 30,
      categoryRules: buildScheduledGenerationRules(data.scheduled_generation_category_rules || {}),
    }
    showScheduledGenerationDialog.value = true
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '加载定时生成配置失败')
  }
}

async function saveScheduledGenerationConfig() {
  if (scheduledGenerationSaving.value) return
  scheduledGenerationSaving.value = true
  try {
    await updateScheduledGenerationConfig({
      scheduled_generation_enabled: scheduledGenerationForm.value.enabled,
      scheduled_generation_cron: scheduledGenerationForm.value.cron || '0 10 * * *',
      scheduled_generation_lookback_days: scheduledGenerationForm.value.lookbackDays || 2,
      scheduled_generation_target_unpublished_count: scheduledGenerationForm.value.targetUnpublishedCount || 5,
      scheduled_generation_subtask_count: scheduledGenerationForm.value.subtaskCount || 1,
      scheduled_generation_unused_template_months: scheduledGenerationForm.value.unusedTemplateMonths || 3,
      scheduled_generation_used_template_cooldown_days: scheduledGenerationForm.value.usedTemplateCooldownDays ?? 30,
      scheduled_generation_category_rules: scheduledGenerationForm.value.categoryRules,
    })
    showScheduledGenerationDialog.value = false
    ElMessage.success(scheduledGenerationForm.value.enabled ? '定时生成已启用' : '定时生成已关闭')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '保存定时生成配置失败')
  } finally {
    scheduledGenerationSaving.value = false
  }
}

// ── 视频分类 ────────────────────────────────────────────────────────────────

const MAJOR_KEYS = ['beauty', 'method', 'shopping', 'lifestyle', 'drama', 'unclassifiable']
const RANKABLE_MAJOR_KEYS = ['beauty', 'method', 'shopping', 'lifestyle', 'drama']
const MAJOR_LABEL_MAP = {
  beauty:         '美美展示类',
  method:         '穿搭方法类',
  shopping:       '购物决策类',
  lifestyle:      '人设生活类',
  drama:          '情景剧情类',
  unclassifiable: '不能分类',
}

const DEFAULT_CLASSIFY_PROMPT = '你将看到一个穿搭/时尚类短视频，请判断视频内容最贴合下列分类中的哪一个，'
  + '只输出对应的 category_key 字符串，不要输出任何额外文字。\n\n分类列表（格式：key — 名称 [大类]）：\n'
  + CATEGORY_OPTIONS.map(c => `${c.key} — ${c.label} [${MAJOR_LABEL_MAP[c.major]}]`).join('\n')
  + '\n\n输出格式：JSON 对象 {"category_key": "<key>"}'

const showDefaultPrompt = ref(false)

function majorLabel(key) {
  return MAJOR_LABEL_MAP[key] || key || '—'
}

function topSubLabel(summary, majorKey) {
  const counts = summary?.category_counts
  if (!counts) return majorLabel(majorKey)
  let bestLabel = null
  let bestCount = 0
  for (const cat of CATEGORY_OPTIONS) {
    if (cat.major !== majorKey) continue
    const c = Number(counts[cat.key] || 0)
    if (c > bestCount) { bestCount = c; bestLabel = cat.label }
  }
  return bestLabel || majorLabel(majorKey)
}

// ── 频道数据分析弹窗 ──────────────────────────────────────────────────────────
const showAnalyticsDialog = ref(false)
const analyticsAccount = ref(null)
const analyticsActivePlatform = ref('')
const analyticsPlatforms = ref([])
const analyticsDateRange = ref([
  (() => { const d = new Date(); d.setDate(d.getDate() - 29); return d.toISOString().slice(0, 10) })(),
  new Date().toISOString().slice(0, 10),
])
const analyticsLoading = ref(false)
const analyticsError = ref('')
const analyticsData = ref(null)

const anaChart1Ref = ref(null)
const anaChart2Ref = ref(null)
const anaChart3Ref = ref(null)
const anaChart4Ref = ref(null)
const anaChart5Ref = ref(null)
let _anaCharts = []
let _anaResizeHandler = null

const analyticsLinkTotalConversion = computed(() => {
  const d = analyticsData.value
  if (!d || !d.total_video_views || d.total_link_clicks == null) return '0.00%'
  return ((d.total_link_clicks / d.total_video_views) * 100).toFixed(2) + '%'
})

function _getAnalyticsPlatforms(account) {
  const seen = new Set()
  return (account.channel_reservations || [])
    .filter(r => r.platform && r.status === 'bound' && !seen.has(r.platform) && seen.add(r.platform))
    .map(r => r.platform)
}

function _getUnboundPlatforms(account) {
  // 有 reservation 但未 bound 的平台（confirmed/reserved）
  const bound = new Set(_getAnalyticsPlatforms(account))
  const seen = new Set()
  return (account.channel_reservations || [])
    .filter(r => r.platform && !bound.has(r.platform) && !seen.has(r.platform) && seen.add(r.platform))
    .map(r => r.platform)
}

async function openAnalyticsDialog(item) {
  analyticsAccount.value = item
  const platforms = _getAnalyticsPlatforms(item)
  analyticsPlatforms.value = platforms
  analyticsActivePlatform.value = platforms[0] || ''
  analyticsData.value = null
  analyticsError.value = ''
  showAnalyticsDialog.value = true

  if (!platforms.length) {
    const unbound = _getUnboundPlatforms(item)
    if (unbound.length) {
      analyticsError.value = `频道尚未完成绑定（${unbound.join('、')} 处于占用状态），暂无数据`
    } else {
      analyticsError.value = '该账号未绑定任何平台频道'
    }
    return
  }

  await loadAnalyticsData()
}

function closeAnalyticsDialog() {
  showAnalyticsDialog.value = false
  analyticsAccount.value = null
  analyticsData.value = null
  analyticsError.value = ''
  disposeAnaCharts()
}

async function switchAnalyticsPlatform(p) {
  analyticsActivePlatform.value = p
  await loadAnalyticsData()
}

async function loadAnalyticsData() {
  if (!analyticsAccount.value || !analyticsActivePlatform.value) return
  const [startDate, endDate] = analyticsDateRange.value || []
  if (!startDate || !endDate) return

  analyticsLoading.value = true
  analyticsError.value = ''
  analyticsData.value = null
  disposeAnaCharts()
  try {
    const data = await fetchChannelAnalytics(analyticsAccount.value.id, {
      platform: analyticsActivePlatform.value,
      startDate,
      endDate,
    })
    analyticsData.value = data
    await nextTick()
    // el-dialog 有淡入动画，nextTick 只保证 vdom diff，需等动画结束 canvas 才有实际尺寸
    setTimeout(() => renderAnaCharts(data), 150)
  } catch (e) {
    analyticsError.value = e?.response?.data?.detail || '加载失败'
  } finally {
    analyticsLoading.value = false
  }
}

function _lineChartOption(title, dates, values, { yFormatter = v => v, color = '#3b82f6' } = {}) {
  return {
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const p = params[0]
        return `${p.axisValue}<br/>${p.marker}${yFormatter(p.value)}`
      },
    },
    grid: { top: 12, right: 20, bottom: 40, left: 60 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11, rotate: 30 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 11, formatter: yFormatter },
    },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color, width: 2 },
      itemStyle: { color },
      areaStyle: { color: color + '22' },
    }],
  }
}

function renderAnaCharts(data) {
  disposeAnaCharts()
  const refs = [anaChart1Ref, anaChart2Ref, anaChart3Ref, anaChart4Ref, anaChart5Ref]
  _anaCharts = refs.map(r => r.value ? echarts.init(r.value) : null)

  // 对齐日期轴：以 views 日期为主轴，clicks 按日期 map
  const viewsByDt = Object.fromEntries((data.daily_views || []).map(d => [d.dt, d]))
  const clicksByDt = Object.fromEntries((data.daily_clicks || []).map(d => [d.dt, d.daily_clicks]))

  // 合并所有日期
  const allDates = [...new Set([
    ...(data.daily_views || []).map(d => d.dt),
    ...(data.daily_clicks || []).map(d => d.dt),
  ])].sort()

  const dailyViews = allDates.map(dt => viewsByDt[dt]?.daily_view_increment ?? 0)

  // Link 累计点击（按时间累加）
  let cumClicks = 0
  const cumulativeClicks = allDates.map(dt => {
    cumClicks += clicksByDt[dt] ?? 0
    return cumClicks
  })
  const dailyClicks = allDates.map(dt => clicksByDt[dt] ?? 0)

  // 日转化率
  const dailyConversion = allDates.map((dt, i) => {
    const views = dailyViews[i]
    const clicks = dailyClicks[i]
    if (!views) return 0
    return +((clicks / views) * 100).toFixed(4)
  })

  // 总转化率（累计点击 / 截至当天 day_end_views）
  const totalConversion = allDates.map((dt, i) => {
    const totalViews = viewsByDt[dt]?.day_end_views ?? 0
    const clicks = cumulativeClicks[i]
    if (!totalViews) return 0
    return +((clicks / totalViews) * 100).toFixed(4)
  })

  const pctFmt = v => v + '%'
  const colors = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444']
  const configs = [
    { values: dailyViews, color: colors[0] },
    { values: cumulativeClicks, color: colors[1] },
    { values: dailyClicks, color: colors[2] },
    { values: dailyConversion, color: colors[3], yFormatter: pctFmt },
    { values: totalConversion, color: colors[4], yFormatter: pctFmt },
  ]

  _anaCharts.forEach((chart, i) => {
    if (!chart) return
    const cfg = configs[i]
    chart.setOption(_lineChartOption('', allDates, cfg.values, { color: cfg.color, yFormatter: cfg.yFormatter }))
    chart.resize()
  })

  if (!_anaResizeHandler) {
    _anaResizeHandler = () => _anaCharts.forEach(c => c?.resize())
    window.addEventListener('resize', _anaResizeHandler)
  }
}

function disposeAnaCharts() {
  if (_anaResizeHandler) {
    window.removeEventListener('resize', _anaResizeHandler)
    _anaResizeHandler = null
  }
  _anaCharts.forEach(c => c?.dispose())
  _anaCharts = []
}

const showClassificationDialog = ref(false)
const classificationLoading = ref(false)
const classificationStarting = ref(false)
const classificationRetrying = ref(false)
const classificationAccount = ref(null)
const classificationView = ref(null)
const vcMajorChartRef = ref(null)
const vcCategoryChartRef = ref(null)
let _vcMajorChart = null
let _vcCategoryChart = null
let _vcResizeHandler = null
let _classificationPollTimer = null
let _classificationPollSeq = 0

const vcFullscreenVisible = ref(false)
const vcFullscreenItem = ref(null)

function openVcFullscreen(v) {
  vcFullscreenItem.value = v
  vcFullscreenVisible.value = true
}
function closeVcFullscreen() {
  vcFullscreenVisible.value = false
  vcFullscreenItem.value = null
}
function _onVcFsKeydown(e) {
  if (e.key === 'Escape' && vcFullscreenVisible.value) closeVcFullscreen()
}
document.addEventListener('keydown', _onVcFsKeydown)

const MAJOR_COLORS = {
  display: '#ec4899',
  knowledge: '#3b82f6',
  persona: '#8b5cf6',
  trending: '#f97316',
}

const classificationSummary = computed(() => classificationView.value?.summary?.summary || null)

const classificationGroups = computed(() => {
  const view = classificationView.value
  if (!view) return []
  const groups = {
    processing: { key: 'processing', label: '分类中', items: [] },
    pending: { key: 'pending', label: '排队中', items: [] },
    success: { key: 'success', label: '已完成', items: [] },
    failed: { key: 'failed', label: '失败', items: [] },
    not_started: { key: 'not_started', label: '未开始', items: [] },
    no_local_video: { key: 'no_local_video', label: '无本地视频', items: [] },
  }
  for (const v of view.videos || []) {
    const key = groups[v.status] ? v.status : 'not_started'
    groups[key].items.push(v)
  }
  return [groups.processing, groups.pending, groups.success, groups.failed, groups.not_started, groups.no_local_video]
})

function clearClassificationPolling() {
  if (_classificationPollTimer) {
    clearTimeout(_classificationPollTimer)
    _classificationPollTimer = null
  }
  _classificationPollSeq += 1
}

function shouldKeepPolling() {
  const view = classificationView.value
  if (!view) return false
  if (view.summary?.classification_status === 'running') return true
  const summary = view.summary?.summary
  if (summary && (summary.pending > 0 || summary.processing > 0)) return true
  return false
}

async function refreshClassification() {
  if (!classificationAccount.value) return
  const accountId = classificationAccount.value.id
  try {
    const data = await fetchAccountClassification(accountId)
    if (!classificationAccount.value || classificationAccount.value.id !== accountId) return
    classificationView.value = data
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载分类数据失败')
  }
}

function scheduleClassificationPoll() {
  clearClassificationPolling()
  if (!showClassificationDialog.value) return
  if (!shouldKeepPolling()) return
  const seq = ++_classificationPollSeq
  _classificationPollTimer = setTimeout(async () => {
    if (seq !== _classificationPollSeq) return
    if (!showClassificationDialog.value) return
    await refreshClassification()
    scheduleClassificationPoll()
  }, 3000)
}

async function openClassificationDialog(item) {
  classificationAccount.value = item
  classificationView.value = null
  showClassificationDialog.value = true
  classificationLoading.value = true
  try {
    await refreshClassification()
  } finally {
    classificationLoading.value = false
  }
  await nextTick()
  ensureClassificationCharts()
  renderClassificationCharts()
  scheduleClassificationPoll()
}

function closeClassificationDialog() {
  clearClassificationPolling()
  disposeClassificationCharts()
  classificationAccount.value = null
  classificationView.value = null
}

function ensureClassificationCharts() {
  if (!_vcMajorChart && vcMajorChartRef.value) {
    _vcMajorChart = echarts.init(vcMajorChartRef.value)
  }
  if (!_vcCategoryChart && vcCategoryChartRef.value) {
    _vcCategoryChart = echarts.init(vcCategoryChartRef.value)
  }
  if (!_vcResizeHandler) {
    _vcResizeHandler = () => {
      _vcMajorChart?.resize()
      _vcCategoryChart?.resize()
    }
    window.addEventListener('resize', _vcResizeHandler)
  }
}

function disposeClassificationCharts() {
  if (_vcResizeHandler) {
    window.removeEventListener('resize', _vcResizeHandler)
    _vcResizeHandler = null
  }
  _vcMajorChart?.dispose()
  _vcCategoryChart?.dispose()
  _vcMajorChart = null
  _vcCategoryChart = null
}

function renderClassificationCharts() {
  const summary = classificationSummary.value
  const categories = classificationView.value?.categories || []
  if (!summary) return

  if (_vcMajorChart) {
    const counts = summary.counts || {}
    _vcMajorChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 4, left: 'center', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
      series: [{
        name: '大类占比',
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        label: { show: true, formatter: '{b}\n{d}%', fontSize: 11 },
        labelLine: { length: 6, length2: 6 },
        data: MAJOR_KEYS.map(k => ({
          name: majorLabel(k),
          value: counts[k] || 0,
          itemStyle: { color: MAJOR_COLORS[k] },
        })),
      }],
    }, true)
  }

  if (_vcCategoryChart) {
    const cc = summary.category_counts || {}
    const labels = categories.map(c => c.label)
    const values = categories.map(c => cc[String(c.index)] || 0)
    const colors = categories.map(c => MAJOR_COLORS[c.major] || '#94a3b8')
    _vcCategoryChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { top: 16, right: 16, bottom: 70, left: 40 },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: { fontSize: 10, interval: 0, rotate: 35, color: '#475569' },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        axisLabel: { fontSize: 11, color: '#64748b' },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
      },
      series: [{
        name: '视频数',
        type: 'bar',
        data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
        barMaxWidth: 28,
        label: { show: true, position: 'top', fontSize: 10 },
      }],
    }, true)
  }
}

watch(classificationSummary, () => {
  if (showClassificationDialog.value) {
    nextTick(() => {
      ensureClassificationCharts()
      renderClassificationCharts()
    })
  }
}, { deep: true })

async function handleRetryFailed() {
  if (!classificationAccount.value || classificationRetrying.value) return
  classificationRetrying.value = true
  try {
    const result = await retryAccountClassificationFailed(classificationAccount.value.id)
    ElMessage.success(`已重新入队 ${result.queued || 0} 个失败任务`)
    await refreshClassification()
    scheduleClassificationPoll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '重试失败')
  } finally {
    classificationRetrying.value = false
  }
}

onUnmounted(() => {
  clearClassificationPolling()
  disposeAnaCharts()
})

const platformStats = ref([])
const platformStatsLoading = ref(false)

const PLATFORM_STATS_MOCK = [
  { platform: 'tiktok',    bound: 0, confirmed: 0, no_stock: 0, unbound: 0 },
  { platform: 'youtube',   bound: 0, confirmed: 0, no_stock: 0, unbound: 0 },
  { platform: 'instagram', bound: 0, confirmed: 0, no_stock: 0, unbound: 0 },
]

async function loadPlatformStats() {
  platformStats.value = PLATFORM_STATS_MOCK
  platformStatsLoading.value = true
  try {
    const data = await fetchPlatformStats()
    platformStats.value = data.platforms || PLATFORM_STATS_MOCK
  } catch {
    // 后端未启动时保留 mock，不白屏
  } finally {
    platformStatsLoading.value = false
  }
}

const PLATFORM_META = {
  tiktok: {
    label: 'TikTok',
    tag: 'TRENDING',
    tagColor: '#1a1a1a',
    tagBg: '#f0f0f0',
    icon: `<svg width="28" height="28" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="8" fill="#010101"/><path d="M22.5 8.5a5.5 5.5 0 0 1-3.5-1.3V19a5 5 0 1 1-4-4.9V11a8 8 0 1 0 7.5 8V8.5z" fill="white"/></svg>`,
  },
  youtube: {
    label: 'YouTube',
    tag: 'GLOBAL',
    tagColor: '#dc2626',
    tagBg: '#fef2f2',
    icon: `<svg width="28" height="28" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="8" fill="#FF0000"/><path d="M26 11.5s-.3-1.9-1.1-2.7c-1-.9-2.2-.9-2.7-1C19.6 7.5 16 7.5 16 7.5s-3.6 0-6.2.3c-.5.1-1.7.1-2.7 1-.8.8-1.1 2.7-1.1 2.7S6 13.7 6 16v2.2c0 2.3.3 4.5.3 4.5s.3 1.9 1.1 2.7c1 .9 2.4.9 3 1 2.1.2 9 .2 9 .2s3.6 0 6.2-.3c.5-.1 1.7-.1 2.7-1 .8-.8 1.1-2.7 1.1-2.7S30 20.3 30 18v-2.1c0-2.3-.3-4.5-.3-4.5zM13.5 20V12l7 4-7 4z" fill="white"/></svg>`,
  },
  instagram: {
    label: 'Instagram',
    tag: 'VISUAL',
    tagColor: '#c026d3',
    tagBg: '#fdf4ff',
    icon: `<svg width="28" height="28" viewBox="0 0 32 32" fill="none"><defs><linearGradient id="ig-grad" x1="0" y1="32" x2="32" y2="0" gradientUnits="userSpaceOnUse"><stop stop-color="#f9ce34"/><stop offset="0.33" stop-color="#ee2a7b"/><stop offset="1" stop-color="#6228d7"/></linearGradient></defs><rect width="32" height="32" rx="8" fill="url(#ig-grad)"/><rect x="8" y="8" width="16" height="16" rx="4.5" stroke="white" stroke-width="2" fill="none"/><circle cx="16" cy="16" r="4" stroke="white" stroke-width="2" fill="none"/><circle cx="21" cy="11" r="1.2" fill="white"/></svg>`,
  },
}

onMounted(() => {
  loadFlags()
  loadData()
  loadPlatformStats()
})
</script>

<style scoped>
.al-page {
  padding: 28px 32px;
  min-height: 100%;
  animation: rise 0.3s ease;
}

/* ── 平台统计卡片 ─────────────────────────────────────────────── */
.ps-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
  min-height: 60px;
}

.ps-card {
  background: #fff;
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ps-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ps-platform-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.ps-platform-name {
  font-size: 17px;
  font-weight: 700;
  color: #111;
  flex: 1;
}

.ps-platform-tag {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 3px 8px;
  border-radius: 6px;
}

.ps-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.ps-stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ps-stat-label {
  font-size: 12px;
  color: #9ca3af;
}

.ps-stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #111;
  line-height: 1;
}

.ps-stat-warn {
  color: #3b82f6;
}

.ps-stat-muted {
  color: #6b7280;
}

.ps-status-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #92400e;
  background: #fffbeb;
  border-radius: 8px;
  padding: 8px 10px;
}

.ps-status-ok {
  color: #166534;
  background: #f0fdf4;
}

.ps-status-info {
  color: #1e40af;
  background: #eff6ff;
}

.al-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 12px;
}

.al-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.al-more-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 14px;
  border: 1px solid #e2e8f0 !important;
  background: #f8fafc !important;
  color: #475569 !important;
  display: flex;
  align-items: center;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.al-more-btn:hover {
  background: #f1f5f9 !important;
  border-color: #cbd5e1 !important;
  color: #1e293b !important;
}

.al-title {
  font-size: 26px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.03em;
  margin: 0;
}

.al-bulk-resume-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.al-bulk-resume-hint {
  font-size: 13px;
  line-height: 1.7;
  color: #475569;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px 14px;
}

.al-bulk-resume-desc {
  font-size: 13px;
  line-height: 1.7;
  color: #1e40af;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  padding: 12px 14px;
}

.bae-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

:deep(.bae-dialog) {
  border-radius: 12px;
}

:deep(.bae-dialog .el-dialog__header) {
  padding: 18px 22px 14px;
  margin-right: 0;
  border-bottom: 1px solid #eef2f7;
}

:deep(.bae-dialog .el-dialog__body) {
  padding: 18px 22px 8px;
}

:deep(.bae-dialog .el-dialog__footer) {
  padding: 14px 22px 18px;
  border-top: 1px solid #eef2f7;
}

.bae-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bae-header-icon {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #0f766e;
  background: #ecfeff;
  border: 1px solid #a5f3fc;
  flex-shrink: 0;
}

.bae-title {
  font-size: 16px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.3;
}

.bae-subtitle {
  margin-top: 3px;
  font-size: 12px;
  color: #64748b;
}

.bae-summary {
  min-height: 42px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  font-size: 13px;
}

.bae-summary-label {
  color: #64748b;
  font-weight: 600;
}

.bae-summary strong {
  color: #0f172a;
  font-size: 15px;
}

.bae-summary-separator {
  width: 1px;
  height: 14px;
  background: #cbd5e1;
  margin: 0 4px;
}

.bae-summary-active {
  color: #047857;
  font-weight: 700;
}

.bae-summary-muted {
  color: #94a3b8;
  font-weight: 600;
}

.bae-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.bae-field {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  background: #fff;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
}

.bae-field.is-active {
  border-color: #94a3b8;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
}

.bae-field.is-indigo.is-active {
  border-color: #818cf8;
  background: #f8faff;
}

.bae-field.is-cyan.is-active {
  border-color: #22d3ee;
  background: #f0fdff;
}

.bae-field.is-rose.is-active {
  border-color: #f9a8d4;
  background: #fff7fb;
}

.bae-field.is-emerald.is-active {
  border-color: #6ee7b7;
  background: #f4fdf9;
}

.bae-field.is-amber.is-active {
  border-color: #fcd34d;
  background: #fffbeb;
}

.bae-field-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.bae-field-icon {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #475569;
  background: #f1f5f9;
  flex-shrink: 0;
}

.bae-field.is-indigo.is-active .bae-field-icon {
  color: #4f46e5;
  background: #eef2ff;
}

.bae-field.is-cyan.is-active .bae-field-icon {
  color: #0891b2;
  background: #cffafe;
}

.bae-field.is-rose.is-active .bae-field-icon {
  color: #be185d;
  background: #fce7f3;
}

.bae-field.is-emerald.is-active .bae-field-icon {
  color: #047857;
  background: #d1fae5;
}

.bae-field.is-amber.is-active .bae-field-icon {
  color: #b45309;
  background: #fef3c7;
}

.bae-field-title-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bae-field-label {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.bae-field-title-wrap strong {
  color: #0f172a;
  font-size: 14px;
  line-height: 1.25;
}

.bae-options {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.bae-option {
  height: 28px;
  padding: 0 10px;
  border-radius: 7px;
  border: 1px solid #dbe4ef;
  background: #fff;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}

.bae-option:hover {
  border-color: #94a3b8;
  background: #f8fafc;
}

.bae-option.active {
  border-color: #0f172a;
  background: #0f172a;
  color: #fff;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.14);
}

.bae-option.is-keep.active {
  border-color: #cbd5e1;
  background: #f8fafc;
  color: #64748b;
  box-shadow: none;
}

.bae-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.bae-reset {
  height: 32px;
  padding: 0 10px;
  border-radius: 7px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.bae-reset:hover:not(:disabled) {
  border-color: #94a3b8;
  color: #334155;
  background: #f8fafc;
}

.bae-reset:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.bae-footer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.al-add-btn {
  display: flex;
  align-items: center;
  font-weight: 600;
  height: 40px;
  border-radius: 10px;
  padding: 0 18px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
}

/* Table */
/* 外层容器：边框/圆角/阴影 */
.al-table-wrap {
  width: 100%;
  margin-bottom: 28px;
  border: 1px solid #e8edf5;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,.04);
  position: relative;
  overflow: hidden; /* 裁剪圆角 — sticky 列在此容器内仍可正常工作 */
}

/* 内层滚动容器：横向滚动，sticky 在这里生效 */
.al-table-scroll {
  width: 100%;
  overflow-x: auto;
  overflow-y: visible;
}

.al-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  min-width: 1660px;
  table-layout: fixed;
}

.al-th {
  padding: 11px 14px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-align: left;
  background: #f8fafc;
  border-bottom: 1px solid #e8edf5;
  white-space: nowrap;
  user-select: none;
}

/* Sticky Header Cells */
.al-th.al-th-check,
.al-th.al-th-media,
.al-th.al-th-name {
  position: sticky;
  z-index: 30;
  background: #f8fafc;
}

.al-th:first-child { border-top-left-radius: 14px; }
.al-th:last-child  { border-top-right-radius: 14px; }

.al-th-check    { width: 44px; text-align: center; left: 0; border-right: 1px solid #e8edf5; }
.al-th-media    { width: 118px; left: 44px; border-right: 1px solid #e8edf5; }
.al-th-name     { width: 420px; left: 162px; box-shadow: 2px 0 5px -2px rgba(0,0,0,0.1); border-right: 1px solid #e8edf5; }
.al-th-platform { width: 180px; }
.al-th-stat     { width: 100px; text-align: right; }
.al-th-date     { width: 130px; }
.al-th-flags    { width: 160px; }
.al-th-tags     { width: 220px; }
.al-th-actions  { width: 160px; text-align: center; }

/* Sortable header */
.al-th-sortable {
  cursor: pointer;
}
.al-th-sortable:hover {
  background: #f1f5fb;
  color: #4f46e5;
}
.al-th-label {
  display: inline;
}
.al-sort-icon {
  display: inline-flex;
  align-items: center;
  margin-left: 4px;
  vertical-align: middle;
}

/* Column filter bar */
.al-col-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px 0 2px;
}
.al-col-filter-select {
  height: 28px;
  padding: 0 24px 0 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E") no-repeat right 7px center;
  background-size: 10px 6px;
  font-size: 12px;
  color: #374151;
  appearance: none;
  cursor: pointer;
  transition: border-color 0.15s;
  outline: none;
}
.al-col-filter-select:hover {
  border-color: #a5b4fc;
}
.al-col-filter-select:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99,102,241,0.12);
}
.al-col-filter-clear {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid #fca5a5;
  border-radius: 6px;
  background: #fff;
  color: #ef4444;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.al-col-filter-clear:hover {
  background: #fee2e2;
}

.al-cat-filter {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 0 2px;
  flex-wrap: wrap;
}
.al-cat-filter-label {
  flex-shrink: 0;
  font-size: 12px;
  color: #475569;
  line-height: 26px;
  font-weight: 500;
}
.al-cat-filter-hint {
  color: #94a3b8;
  font-weight: normal;
  margin-left: 4px;
}
.al-cat-filter-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
  min-width: 0;
}
.al-cat-pill {
  height: 26px;
  padding: 0 10px;
  border-radius: 13px;
  border: 1px solid #e2e8f0;
  background: #fff;
  font-size: 12px;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.al-cat-pill:hover {
  border-color: #a5b4fc;
  color: #4338ca;
}
.al-cat-pill.active {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
  font-weight: 500;
}
.al-cat-pill.is-display.active { background: #ec4899; border-color: #ec4899; }
.al-cat-pill.is-knowledge.active { background: #3b82f6; border-color: #3b82f6; }
.al-cat-pill.is-persona.active { background: #f59e0b; border-color: #f59e0b; }
.al-cat-pill.is-trending.active { background: #10b981; border-color: #10b981; }

/* 已勾选 AI 博主统计 */
.al-selection-stats {
  margin: 12px 0;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}
.al-selection-stats-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.al-selection-stats-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}
.al-selection-stats-desc {
  font-size: 12px;
  color: #94a3b8;
  flex: 1;
}
.al-selection-stats-count {
  font-size: 12px;
  color: #4338ca;
  background: #eef2ff;
  padding: 3px 10px;
  border-radius: 10px;
  font-weight: 500;
}
.al-selection-stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.al-stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
}
.al-stat-card-icon {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.al-stat-card.is-followers .al-stat-card-icon { background: #ede9fe; color: #7c3aed; }
.al-stat-card.is-views .al-stat-card-icon { background: #dbeafe; color: #2563eb; }
.al-stat-card.is-like .al-stat-card-icon { background: #dcfce7; color: #16a34a; }
.al-stat-card.is-conversion .al-stat-card-icon { background: #ffedd5; color: #ea580c; }
.al-stat-card-body { min-width: 0; flex: 1; }
.al-stat-card-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}
.al-stat-card-value {
  font-size: 20px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.2;
}
.al-stat-card-value-empty { color: #cbd5e1; font-weight: 500; }
@media (max-width: 1100px) {
  .al-selection-stats-cards { grid-template-columns: repeat(2, 1fr); }
}

.al-tr {
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid #f1f5f9;
}

.al-tr.is-selected {
  background: #eef2ff;
}

.al-tr:last-child { border-bottom: none; }

.al-tr:hover { background: #f8faff; }

.al-td {
  padding: 16px 14px;
  vertical-align: middle;
  font-size: 13px;
  color: #1e293b;
  background: #fff; /* Opaque background for sticky columns */
}

/* Sticky Data Cells */
.al-td.al-td-check,
.al-td.al-td-media,
.al-td.al-td-name {
  position: sticky;
  z-index: 20;
}

.al-td-check  { text-align: center; width: 44px; left: 0; border-right: 1px solid #f1f5f9; }
.al-td-media  { width: 118px; left: 44px; border-right: 1px solid #f1f5f9; }
.al-td-name   { width: 420px; left: 162px; box-shadow: 2px 0 5px -2px rgba(0,0,0,0.1); border-right: 1px solid #f1f5f9; }
.al-td-flags   { width: 160px; }
.al-td-actions { text-align: center; width: 160px; }

/* Name cell adjustments for fixed layout */
.al-account-card {
  display: flex;
  flex-direction: column;
  gap: 9px;
  max-width: 392px;
}

.al-account-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.al-account-title-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.al-name-handle {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin-bottom: 4px;
  min-width: 0;
  width: 100%;
}
.al-handle {
  font-size: 12px;
  font-weight: 600;
  color: #6366f1;
}
.al-signature {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.al-tr:hover .al-td.al-td-check,
.al-tr:hover .al-td.al-td-media,
.al-tr:hover .al-td.al-td-name {
  background: #f8faff;
}

.al-tr.is-selected .al-td.al-td-check,
.al-tr.is-selected .al-td.al-td-media,
.al-tr.is-selected .al-td.al-td-name {
  background: #eef2ff;
}

.al-td-stat {
  text-align: right;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: #0f172a;
}

.al-td-date {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}

/* Media cell */
.al-media-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
}

.al-photo-wrap {
  width: 52px;
  height: 52px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  cursor: zoom-in;
  background: linear-gradient(135deg, #eef2ff, #f5f3ff);
  display: flex;
  align-items: center;
  justify-content: center;
}

.al-photo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.al-photo-ph {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.al-avatar-wrap {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  cursor: zoom-in;
  background: #eef2ff;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,.1);
}

.al-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.al-avatar-ph {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.al-pending-badge {
  position: absolute;
  top: -4px;
  left: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: rgba(234, 88, 12, 0.96);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 2px 6px rgba(194, 65, 12, 0.3);
}

/* Name cell */
.al-name-main {
  font-size: 16px;
  font-weight: 750;
  color: #0f172a;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 270px;
}

.al-handle {
  font-size: 12px;
  line-height: 1.2;
  color: #4f46e5;
  font-weight: 600;
}

.al-signature {
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.al-identity-grid {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.al-account-metrics {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 2px;
}

.al-style-desc {
  font-size: 11px;
  color: #64748b;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 360px;
}

/* Platform cell */
.al-bindings {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.al-no-binding {
  font-size: 12px;
  color: #94a3b8;
}

/* Tags / Flags cell */
.al-flags-wrap,
.al-tags-wrap,
.al-bloggers-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 4px;
}

.ac-flag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 20px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 11px;
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
}

.ac-flag-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  flex-shrink: 0;
}

/* Row actions */
.al-row-actions {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 5px;
  justify-content: center;
}

/* Shared chip / badge styles */
.al-hashtags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
}
.al-hashtag-chip {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 20px;
  background: #ede9fe;
  color: #6d28d9;
  white-space: nowrap;
}
.al-hashtag-chip.al-hashtag-more {
  background: #f3f4f6;
  color: #6b7280;
}

.ac-blogger-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  background: #f8faff;
  border: 1px solid #e0e7ff;
  border-radius: 20px;
  padding: 3px 8px 3px 3px;
  max-width: 140px;
}

.ac-blogger-avatar {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}

.ac-blogger-avatar-ph {
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ac-blogger-name {
  font-size: 11px;
  font-weight: 500;
  color: #4f46e5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90px;
}

.ac-tagging-badge {
  font-size: 10px;
  line-height: 1;
  flex-shrink: 0;
}
.ac-tagging-badge--clickable {
  cursor: pointer;
  border-radius: 3px;
  padding: 1px 2px;
  transition: background 0.15s;
}
.ac-tagging-badge--clickable:hover { background: rgba(0,0,0,0.06); }
.ac-tagging-badge--success { opacity: 0.9; }
.ac-tagging-badge--failed { opacity: 0.7; }

/* 人设打标进度 dialog */
.tp-body { display: flex; flex-direction: column; gap: 14px; }

.tp-overview {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}
.tp-overview-left { display: flex; flex-direction: column; gap: 6px; flex: 1; }
.tp-overview-right { flex-shrink: 0; }

.tp-overview-status { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #334155; }
.tp-status-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #cbd5e1; flex-shrink: 0;
}
.tp-status-dot.is-pending, .tp-status-dot.is-checking_videos,
.tp-status-dot.is-waiting_videos, .tp-status-dot.is-aggregating {
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245,158,11,.2);
  animation: tp-pulse 1.2s ease-in-out infinite;
}
.tp-status-dot.is-running {
  background: #6366f1;
  box-shadow: 0 0 0 3px rgba(99,102,241,.2);
  animation: tp-pulse 1.2s ease-in-out infinite;
}
.tp-status-dot.is-success { background: #16a34a; }
.tp-status-dot.is-failed { background: #dc2626; }
.tp-status-dot.is-not_started { background: #94a3b8; }
.tp-status-label { font-size: 12px; color: #64748b; }

@keyframes tp-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.tp-overview-counts { font-size: 12px; color: #475569; }

.tp-progress-bar-wrap { display: flex; align-items: center; gap: 8px; }
.tp-progress-bar {
  flex: 1;
  height: 6px;
  background: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
  display: flex;
}
.tp-progress-fill {
  height: 100%;
  transition: width 0.4s ease;
  flex-shrink: 0;
}
.tp-progress-fill--success { background: #16a34a; }
.tp-progress-fill--running { background: #6366f1; }
.tp-progress-fill--failed { background: #dc2626; }
.tp-progress-pct { font-size: 11px; color: #64748b; min-width: 30px; text-align: right; }

.tp-video-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 380px;
  overflow-y: auto;
}
.tp-video-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #f8fafc;
  font-size: 12px;
}
.tp-video-item.is-success { background: #f0fdf4; }
.tp-video-item.is-running { background: #eef2ff; }
.tp-video-item.is-failed { background: #fef2f2; }
.tp-video-item.is-pending { background: #fffbeb; }

.tp-video-status-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  background: #94a3b8;
}
.tp-video-status-dot.is-success { background: #16a34a; }
.tp-video-status-dot.is-running { background: #6366f1; animation: tp-pulse 1.2s ease-in-out infinite; }
.tp-video-status-dot.is-failed { background: #dc2626; }
.tp-video-status-dot.is-pending { background: #f59e0b; }

.tp-video-desc { flex: 1; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tp-video-status-label { flex-shrink: 0; font-size: 11px; color: #64748b; min-width: 42px; text-align: right; }
.tp-video-item.is-success .tp-video-status-label { color: #16a34a; }
.tp-video-item.is-running .tp-video-status-label { color: #6366f1; }
.tp-video-item.is-failed .tp-video-status-label { color: #dc2626; }
.tp-video-item.is-pending .tp-video-status-label { color: #d97706; }

.tp-empty { text-align: center; color: #94a3b8; font-size: 13px; padding: 24px 0; }

/* 完整结果区域 */
.tp-result {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.tp-result-summary {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}
.tp-result-summary-icon { flex-shrink: 0; font-size: 14px; }
.tp-result-tags { display: flex; flex-direction: column; gap: 8px; }
.tp-result-group { display: flex; align-items: flex-start; gap: 8px; }
.tp-result-group-label {
  flex-shrink: 0;
  width: 68px;
  font-size: 11px;
  color: #94a3b8;
  padding-top: 2px;
  text-align: right;
}
.tp-result-chips { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; }
.tp-chip {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
}
.tp-chip--demo    { background:#eff6ff; color:#3b82f6; border:1px solid #bfdbfe; }
.tp-chip--consumption { background:#fefce8; color:#ca8a04; border:1px solid #fde68a; }
.tp-chip--temperament { background:#fdf4ff; color:#a855f7; border:1px solid #e9d5ff; }
.tp-chip--identity    { background:#f0fdf4; color:#16a34a; border:1px solid #bbf7d0; }
.tp-chip--occasion    { background:#ecfdf5; color:#059669; border:1px solid #a7f3d0; }
.tp-chip--style       { background:#fff7ed; color:#ea580c; border:1px solid #fed7aa; }
.tp-chip--style-hi    { background:#ffedd5; font-weight:700; border-color:#fb923c; }
.tp-chip--color       { background:#f1f5f9; color:#475569; border:1px solid #e2e8f0; }
.tp-chip--mood        { background:#fdf4ff; color:#9333ea; border:1px solid #e9d5ff; }
.tp-chip--meta        { background:#f8fafc; color:#64748b; border:1px solid #e2e8f0; }

/* 步骤条 */
.tp-stage-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.tp-stage {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}
.tp-stage-arrow { color: #cbd5e1; font-size: 14px; flex-shrink: 0; }
.tp-stage-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  background: #cbd5e1;
}
.tp-stage-dot.is-running { background: #6366f1; animation: tp-pulse 1.2s ease-in-out infinite; }
.tp-stage-dot.is-pending { background: #f59e0b; animation: tp-pulse 1.2s ease-in-out infinite; }
.tp-stage-dot.is-success { background: #16a34a; }
.tp-stage-dot.is-partial { background: #f59e0b; }
.tp-stage-dot.is-failed { background: #dc2626; }
.tp-stage-dot.is-not_started { background: #cbd5e1; }
.tp-stage-info { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.tp-stage-title { font-size: 12px; font-weight: 600; color: #334155; }
.tp-stage-desc { font-size: 11px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tp-stage.is-success .tp-stage-title { color: #16a34a; }
.tp-stage.is-failed .tp-stage-title { color: #dc2626; }
.tp-stage.is-running .tp-stage-title { color: #6366f1; }

/* 错误 banner */
.tp-error-banner {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  font-size: 12px;
  color: #dc2626;
  word-break: break-all;
}

/* 打标结果区域 */
.al-persona-result-wrap {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 4px;
}

.al-persona-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
}

.al-persona-label {
  font-size: 10px;
  color: #94a3b8;
  margin-right: 2px;
  white-space: nowrap;
}

.al-persona-chip {
  display: inline-block;
  font-size: 10px;
  font-weight: 500;
  padding: 1px 5px;
  border-radius: 4px;
  white-space: nowrap;
}

.al-persona-chip--demo {
  background: #eff6ff;
  color: #3b82f6;
  border: 1px solid #bfdbfe;
}

.al-persona-chip--consumption {
  background: #fefce8;
  color: #ca8a04;
  border: 1px solid #fde68a;
}

.al-persona-chip--temperament {
  background: #fdf4ff;
  color: #a855f7;
  border: 1px solid #e9d5ff;
}

.al-persona-chip--occasion {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #bbf7d0;
}

.al-persona-chip--style {
  background: #fff7ed;
  color: #ea580c;
  border: 1px solid #fed7aa;
}

/* 人设打标按钮 */
.al-tagging-btn {
  background: #fff7ed;
  border-color: #fed7aa;
  color: #ea580c;
}
.al-tagging-btn:hover {
  background: #ffedd5;
  border-color: #fdba74;
  color: #c2410c;
}

.ac-tag-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 11px;
  color: #334155;
  font-weight: 500;
  white-space: nowrap;
}

.ac-tag-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ac-tag {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  white-space: nowrap;
}

.ac-tag-youtube  { background: #fef2f2; color: #dc2626; }
.ac-tag-tiktok   { background: #f1f5f9; color: #0f172a; }
.ac-tag-instagram { background: #fef3c7; color: #92400e; }
.ac-tag-reserved { background: #ecfeff; color: #0e7490; border: 1px solid #a5f3fc; }
.ac-tag-disabled {
  background: #fff1f2 !important;
  color: #be123c !important;
  border: 1.5px solid #fda4af !important;
  text-decoration: line-through;
  opacity: 0.85;
}

/* Account type badge */
.ac-type-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 4px 9px;
  border-radius: 8px;
  flex-shrink: 0;
  white-space: nowrap;
  line-height: 1.15;
}

.ac-type-persona {
  background: #ede9fe;
  color: #6d28d9;
}

.ac-type-traffic,
.ac-type-shared {
  background: #dbeafe;
  color: #1d4ed8;
}

.ac-type-exclusive {
  background: #fef3c7;
  color: #d97706;
}

.ac-face-yes {
  background: #dcfce7;
  color: #15803d;
}

.ac-face-no {
  background: #fef3c7;
  color: #b45309;
}

.ac-gender-male {
  background: #dbeafe;
  color: #1d4ed8;
}

.ac-gender-female {
  background: #fce7f3;
  color: #be185d;
}

.ac-gender-unisex {
  background: #f3e8ff;
  color: #7c3aed;
}

.ac-product-code-yes {
  background: #ecfdf5;
  color: #047857;
}

.ac-product-code-no {
  background: #f1f5f9;
  color: #64748b;
}

.ac-tier-test {
  background: #f1f5f9;
  color: #64748b;
}

.ac-tier-dev {
  background: #fef3c7;
  color: #b45309;
}

.ac-tier-prod {
  background: #dcfce7;
  color: #15803d;
}

.ac-ai-status {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 9px;
  border-radius: 8px;
  background: #e2e8f0;
  color: #475569;
  white-space: nowrap;
}

.ac-ai-status.is-pending,
.ac-ai-status.is-video_analyzing,
.ac-ai-status.is-name_generating,
.ac-ai-status.is-photo_generating,
.ac-ai-status.is-avatar_generating {
  background: #dbeafe;
  color: #1d4ed8;
}

.ac-ai-status.is-awaiting_photo_selection {
  background: #fef3c7;
  color: #b45309;
}

.ac-ai-status.is-failed {
  background: #fee2e2;
  color: #b91c1c;
}

.ac-ai-status.is-completed {
  background: #dcfce7;
  color: #15803d;
}

.ac-hidden-badge {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #cbd5e1;
}

.ac-supplement-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 11px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  max-width: 100%;
}

.ac-supplement-row.is-running {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.ac-supplement-row.is-completed {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.ac-supplement-row.is-failed {
  border-color: #fecaca;
  background: #fef2f2;
}

.ac-supplement-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  white-space: nowrap;
}

.ac-supplement-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #94a3b8;
  flex-shrink: 0;
}

.ac-supplement-row.is-running .ac-supplement-dot { background: #2563eb; }
.ac-supplement-row.is-completed .ac-supplement-dot { background: #16a34a; }
.ac-supplement-row.is-failed .ac-supplement-dot { background: #dc2626; }

.ac-supplement-mode {
  font-weight: 600;
  color: #64748b;
}

.ac-supplement-lines {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px 10px;
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
}

.ac-classify-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  flex-wrap: wrap;
}
.ac-classify-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 4px 8px;
  border-radius: 8px;
  background: #f1f5f9;
  color: #64748b;
  line-height: 1.15;
}
.ac-classify-badge.is-running { background: #ede9fe; color: #6d28d9; }
.ac-classify-badge.is-single  { background: #dcfce7; color: #15803d; }
.ac-classify-badge.is-dual    { background: #dbeafe; color: #1d4ed8; }
.ac-classify-badge.is-chaos   { background: #fee2e2; color: #b91c1c; }
.ac-classify-badge.is-insufficient { background: #fef3c7; color: #b45309; }
.ac-classify-count,
.ac-metric-item {
  font-size: 11px;
  color: #64748b;
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  padding: 4px 8px;
  line-height: 1.15;
}

/* 分类确认弹窗 */
.al-classify-confirm-option {
  margin-top: 16px;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.al-classify-force-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #0f172a;
  cursor: pointer;
  user-select: none;
}
.al-classify-force-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
}

/* 批量分类按钮 */
.al-classify-btn {
  border-color: #ddd6fe !important;
  color: #6d28d9 !important;
  background: #f5f3ff !important;
}
.al-classify-btn:hover:not(:disabled) {
  border-color: #c4b5fd !important;
  background: #ede9fe !important;
}

.ac-btn {
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 7px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ac-btn-stats {
  border-color: #bae6fd;
  color: #0369a1;
  background: #f0f9ff;
}

.ac-btn-stats:hover {
  border-color: #7dd3fc;
  color: #0284c7;
  background: #e0f2fe;
}

.ac-btn-classify {
  border-color: #ddd6fe;
  color: #6d28d9;
  background: #f5f3ff;
}

.ac-btn-classify:hover {
  border-color: #a78bfa;
  color: #5b21b6;
  background: #ede9fe;
}

.ac-btn-edit:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}

.ac-btn-del {
  border-color: #fecaca;
  color: #dc2626;
  background: #fef2f2;
}

.ac-btn-del:hover {
  border-color: #fca5a5;
  color: #b91c1c;
  background: #fee2e2;
}

.ac-btn-sync {
  border-color: #fde68a;
  color: #92400e;
  background: #fffbeb;
}

.ac-btn-sync:hover {
  border-color: #fcd34d;
  color: #78350f;
  background: #fef3c7;
}

.ac-btn-template-sync {
  border-color: #bbf7d0;
  color: #15803d;
  background: #f0fdf4;
}

.ac-btn-template-sync:hover {
  border-color: #86efac;
  color: #166534;
  background: #dcfce7;
}

.ac-btn.loading {
  opacity: 0.5;
  pointer-events: none;
}

/* Footer */
.al-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0 8px;
  border-top: 1px solid #f1f5f9;
}

.al-pagination-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.al-count-text {
  font-size: 13px;
  color: #94a3b8;
}

.al-simple-select {
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  outline: none;
  padding: 0 4px;
}

.al-simple-select:hover {
  color: #64748b;
}

.al-pagination {
  display: flex;
  gap: 8px;
}

.ac-preview-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.ac-preview-image {
  display: block;
  width: 100%;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 12px;
  background: #f8fafc;
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

.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }

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

.pg-jump-go {
  padding: 7px 12px;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

@media (max-width: 640px) {
  .al-page { padding: 16px; }
  .al-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
  .bae-grid { grid-template-columns: 1fr; }
  .bae-footer { align-items: stretch; flex-direction: column-reverse; }
  .bae-footer-actions { justify-content: flex-end; width: 100%; }
  .bae-reset { width: 100%; }
}

/* 一键生成按钮 */
.al-gen-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(16,185,129,0.25) !important;
  background: rgba(16,185,129,0.07) !important;
  color: #059669 !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.al-gen-btn:hover:not(:disabled) {
  background: rgba(16,185,129,0.14) !important;
  border-color: rgba(16,185,129,0.45) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(16,185,129,0.18);
}
.al-gen-btn:active { transform: translateY(1px); }
.al-gen-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

/* 一键定时按钮 */
.al-schedule-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(59,130,246,0.25) !important;
  background: rgba(59,130,246,0.07) !important;
  color: #2563eb !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.al-schedule-btn:hover:not(:disabled) {
  background: rgba(59,130,246,0.14) !important;
  border-color: rgba(59,130,246,0.45) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59,130,246,0.18);
}
.al-schedule-btn:active { transform: translateY(1px); }
.al-schedule-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

/* 批量定时发布弹窗内元素 */
.al-schedule-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.al-schedule-presets button {
  font-size: 13px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
}
.al-schedule-presets button:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}
.al-schedule-presets button.active {
  border-color: #6366f1;
  background: #6366f1;
  color: #fff;
  font-weight: 600;
}
.al-preset-btn {
  font-size: 13px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
}
.al-preset-btn:hover { border-color: #6366f1; color: #6366f1; background: #eef2ff; }
.al-preset-btn.active { border-color: #6366f1; background: #6366f1; color: #fff; font-weight: 600; }
.al-schedule-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 6px;
}
.al-schedule-unit {
  font-size: 13px;
  color: #64748b;
  margin-left: 10px;
}
.al-schedule-preview {
  font-size: 13px;
  color: #1e40af;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  padding: 10px 14px;
  line-height: 1.6;
}

.al-tasks-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(99,102,241,0.2) !important;
  background: rgba(99,102,241,0.05) !important;
  color: #4f46e5 !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}

.al-tasks-btn:hover {
  background: rgba(99,102,241,0.12) !important;
  border-color: rgba(99,102,241,0.4) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99,102,241,0.15);
}

.al-tasks-btn:active {
  transform: translateY(1px);
}

.al-config-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(139,92,246,0.2) !important;
  background: rgba(139,92,246,0.05) !important;
  color: #7c3aed !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}

.al-config-btn:hover {
  background: rgba(139,92,246,0.12) !important;
  border-color: rgba(139,92,246,0.4) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(139,92,246,0.15);
}

.al-config-btn:active {
  transform: translateY(1px);
}

.al-restart-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(245,158,11,0.2) !important;
  background: rgba(245,158,11,0.05) !important;
  color: #d97706 !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}

.al-restart-btn:hover {
  background: rgba(245,158,11,0.12) !important;
  border-color: rgba(245,158,11,0.4) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(245,158,11,0.15);
}

.al-restart-btn:active {
  transform: translateY(1px);
}

.al-restart-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

/* 补充模板按钮 */
.al-supplement-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(234,88,12,0.2) !important;
  background: rgba(234,88,12,0.06) !important;
  color: #c2410c !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.al-supplement-btn:hover:not(:disabled) {
  background: rgba(234,88,12,0.12) !important;
  border-color: rgba(234,88,12,0.4) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(234,88,12,0.16);
}
.al-supplement-btn:active { transform: translateY(1px); }
.al-supplement-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

.al-namehandle-btn {
  font-weight: 600;
  border-radius: 10px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid rgba(124,58,237,0.2) !important;
  background: rgba(124,58,237,0.06) !important;
  color: #6d28d9 !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.al-namehandle-btn:hover:not(:disabled) {
  background: rgba(124,58,237,0.12) !important;
  border-color: rgba(124,58,237,0.4) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(124,58,237,0.16);
}
.al-namehandle-btn:active { transform: translateY(1px); }
.al-namehandle-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

/* 标签搜索按钮 */
.al-hashtag-btn {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: 1.5px solid #7c3aed;
  background: #fff;
  color: #7c3aed;
  white-space: nowrap;
}
.al-hashtag-btn:hover:not(:disabled) {
  background: #7c3aed;
  color: #fff;
  box-shadow: 0 2px 8px rgba(124,58,237,0.18);
}
.al-hashtag-btn:active { transform: translateY(1px); }
.al-hashtag-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

/* 标签搜索弹窗 */
.al-hashtag-pre {
  padding: 4px 0 8px;
}
.al-hashtag-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
}
.al-hashtag-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.al-hashtag-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ef4444;
  font-size: 14px;
  padding: 12px;
  background: #fef2f2;
  border-radius: 8px;
}
.al-hashtag-meta {
  font-size: 13px;
  color: #6b7280;
}
.al-hashtag-block {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
}
.al-hashtag-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}
.al-hashtag-block-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
.al-hashtag-copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: #6366f1;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 5px;
}
.al-hashtag-copy-btn:hover { background: #ede9fe; }
.al-hashtag-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 14px;
  max-height: 180px;
  overflow-y: auto;
}
.al-hashtag-tags-raw {
  max-height: 130px;
}
.al-hashtag-tag {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  background: #f3f4f6;
  color: #374151;
  cursor: pointer;
  transition: all 0.12s;
}
.al-hashtag-tag:hover { background: #e0e7ff; color: #4338ca; }
.al-hashtag-tag.is-filtered {
  background: #ede9fe;
  color: #6d28d9;
}
.al-hashtag-tag.is-filtered:hover { background: #ddd6fe; }
.al-hashtag-bind-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0 2px;
  border-top: 1px solid #f3f4f6;
  margin-top: 4px;
}
.al-hashtag-bind-label {
  font-size: 13px;
  color: #6b7280;
  white-space: nowrap;
}

/* 补充模板弹窗 */
.al-supplement-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.al-supplement-scope {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: #475569;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 14px;
  line-height: 1.5;
}
.al-supplement-scope svg { flex-shrink: 0; color: #6366f1; }
.al-supplement-scope b { color: #0f172a; font-weight: 700; }

.al-auto-supplement-tip {
  margin: 10px 0 4px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
}
.al-auto-supplement-tip-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #475569;
}
.al-auto-supplement-tip-warn {
  color: #92400e;
}
.al-auto-supplement-tip-warn svg { flex-shrink: 0; color: #d97706; }

.al-supplement-category-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.al-supplement-category-group {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  align-items: flex-start;
}

.al-supplement-category-major {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 26px;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.al-supplement-major-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #94a3b8;
  flex-shrink: 0;
}

.al-supplement-major-dot.is-display { background: #ec4899; }
.al-supplement-major-dot.is-knowledge { background: #3b82f6; }
.al-supplement-major-dot.is-persona { background: #f59e0b; }
.al-supplement-major-dot.is-trending { background: #10b981; }
.al-supplement-major-dot.is-beauty { background: #ec4899; }
.al-supplement-major-dot.is-method { background: #3b82f6; }
.al-supplement-major-dot.is-shopping { background: #f59e0b; }
.al-supplement-major-dot.is-lifestyle { background: #10b981; }
.al-supplement-major-dot.is-drama { background: #8b5cf6; }
.al-supplement-major-dot.is-unclassifiable { background: #94a3b8; }

.al-scheduled-rule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.al-scheduled-rule-row {
  display: grid;
  grid-template-columns: minmax(110px, 1fr) 56px minmax(190px, 220px) minmax(150px, 170px);
  align-items: center;
  gap: 10px;
  min-height: 38px;
}

.al-scheduled-rule-name,
.al-scheduled-rule-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 12px;
  color: #475569;
}

.al-scheduled-rule-name {
  font-weight: 600;
  color: #334155;
}

.al-scheduled-rule-field span {
  flex-shrink: 0;
}

@media (max-width: 720px) {
  .al-scheduled-rule-row {
    grid-template-columns: 1fr;
    gap: 8px;
    align-items: flex-start;
  }
}

.al-supplement-types {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

.al-supplement-type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  border-radius: 12px;
  border: 2px solid #e2e8f0;
  background: #f8fafc;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
}
.al-supplement-type-card:hover:not(.is-disabled) {
  border-color: #6366f1;
  background: #eef2ff;
}
.al-supplement-type-card.active {
  border-color: #6366f1;
  background: #eef2ff;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.12);
}
.al-supplement-type-card.is-disabled {
  opacity: 0.45;
  cursor: not-allowed;
  background: #f1f5f9;
}

.al-supplement-type-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6366f1;
}
.al-supplement-type-card.active .al-supplement-type-icon {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
}
.al-supplement-type-card.is-disabled .al-supplement-type-icon {
  color: #94a3b8;
}

.al-supplement-type-name {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}
.al-supplement-type-card.is-disabled .al-supplement-type-name {
  color: #94a3b8;
}

.al-supplement-type-desc {
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}
.al-supplement-type-card.is-disabled .al-supplement-type-desc {
  color: #94a3b8;
}

.al-supplement-config {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.al-supplement-config-label {
  font-size: 13px;
  color: #334155;
  font-weight: 500;
}
.al-supplement-config-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.al-supplement-minus,
.al-supplement-plus {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  line-height: 1;
}
.al-supplement-minus:hover,
.al-supplement-plus:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}
.al-supplement-num {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  min-width: 28px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.al-supplement-num-hint {
  font-size: 13px;
  color: #94a3b8;
}
.al-supplement-filters {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
}
.al-supplement-filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.al-supplement-filter-row label {
  font-size: 12px;
  color: #475569;
  width: 92px;
  flex-shrink: 0;
}
.al-supplement-filter-hint {
  font-size: 12px;
  color: #94a3b8;
}

/* AI 配置弹窗内容 */
.ai-cfg-body {
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 4px;
}

.ai-cfg-section {
  background: #f8fafc;
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 16px;
  border: 1px solid #e2e8f0;
}

.ai-cfg-section:last-child { margin-bottom: 0; }

.ai-cfg-section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.ai-cfg-tag {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  background: #e2e8f0;
  padding: 3px 10px;
  border-radius: 6px;
  white-space: nowrap;
}

.ai-cfg-desc {
  font-size: 12px;
  color: #94a3b8;
}

.ai-default-prompt-toggle {
  flex-shrink: 0;
  background: none;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  color: #6366f1;
  cursor: pointer;
  line-height: 1.6;
}
.ai-default-prompt-toggle:hover { background: #f5f3ff; }
.ai-default-prompt-box {
  margin-top: 8px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 12px;
  color: #475569;
  white-space: pre-wrap;
  line-height: 1.6;
  font-family: monospace;
  max-height: 260px;
  overflow-y: auto;
  width: 100%;
}

/* ── 账号分级重判预览弹窗 ─────────────────────────────────────────────── */
.tier-eval-body { min-height: 120px; }
.tier-eval-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #374151;
  padding: 8px 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  margin-bottom: 12px;
}
.tier-eval-summary-sep {
  width: 1px;
  height: 14px;
  background: #cbd5e1;
}
.tier-eval-promote { color: #15803d; font-weight: 600; }
.tier-eval-demote { color: #b45309; font-weight: 600; }
.tier-eval-empty {
  text-align: center;
  color: #9ca3af;
  padding: 32px 0;
  font-size: 13px;
}
.tier-eval-list {
  max-height: 480px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tier-eval-item {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px 12px;
  display: grid;
  grid-template-columns: 1fr auto 1.4fr;
  gap: 12px;
  align-items: center;
  background: #fff;
}
.tier-eval-item.is-promote { border-left: 3px solid #22c55e; }
.tier-eval-item.is-demote { border-left: 3px solid #f59e0b; }
.tier-eval-name {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  word-break: break-word;
}
.tier-eval-tier-flow {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.tier-eval-arrow {
  color: #94a3b8;
  font-weight: 700;
}
.tier-chip {
  display: inline-flex;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}
.tier-chip-test { background: #f1f5f9; color: #64748b; }
.tier-chip-dev { background: #fef3c7; color: #b45309; }
.tier-chip-prod { background: #dcfce7; color: #15803d; }
.tier-eval-reason {
  font-size: 12px;
  color: #64748b;
  text-align: right;
  word-break: break-word;
}

/* ── Flag 过滤栏 ──────────────────────────────────────────────────────────── */
.al-filter-bar {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.al-search-box {
  position: relative;
  display: flex;
  align-items: center;
  width: 260px;
}
.al-search-icon {
  position: absolute;
  left: 10px;
  color: #94a3b8;
  pointer-events: none;
  flex-shrink: 0;
}
.al-search-input {
  width: 100%;
  height: 34px;
  padding: 0 30px 0 32px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  color: #1e293b;
  background: #f8fafc;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.al-search-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
  background: #fff;
}
.al-search-input::placeholder { color: #94a3b8; }
.al-search-clear {
  position: absolute;
  right: 8px;
  background: none;
  border: none;
  cursor: pointer;
  color: #94a3b8;
  font-size: 12px;
  padding: 2px 4px;
  line-height: 1;
}
.al-search-clear:hover { color: #475569; }

.al-filter-flags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.al-flag-filter-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 20px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.al-flag-filter-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}

.al-flag-filter-btn.active {
  font-weight: 700;
}

.al-flag-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #94a3b8;
  flex-shrink: 0;
}

.al-flag-filter-btn.is-pinned {
  font-weight: 600;
}

.al-flag-expand-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 20px;
  border: 1px solid #e2e8f0;
  background: #f1f5f9;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.al-flag-expand-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}

.al-flag-manage-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 20px;
  border: 1px dashed #cbd5e1;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.15s;
}

.al-flag-manage-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #f8f9ff;
}

/* ── 多选 checkbox ─────────────────────────────────────────────────────────── */
.al-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: #6366f1;
}

/* ── 批量操作栏 ───────────────────────────────────────────────────────────── */
.al-bulk-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 10px;
}

.al-bulk-count {
  font-size: 13px;
  font-weight: 700;
  color: #4f46e5;
  margin-right: 4px;
}

.al-bulk-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid;
  cursor: pointer;
  transition: all 0.15s;
}

.al-bulk-action-btn.is-bind {
  border-color: #a5b4fc;
  background: #fff;
  color: #4f46e5;
}

.al-bulk-action-btn.is-bind:hover {
  background: #6366f1;
  color: #fff;
  border-color: #6366f1;
}

.al-bulk-action-btn.is-unbind {
  border-color: #fca5a5;
  background: #fff;
  color: #dc2626;
}

.al-bulk-action-btn.is-unbind:hover {
  background: #ef4444;
  color: #fff;
  border-color: #ef4444;
}

.al-bulk-action-btn.is-generate {
  border-color: #a78bfa;
  background: #fff;
  color: #7c3aed;
}

.al-bulk-action-btn.is-generate:hover {
  background: #7c3aed;
  color: #fff;
  border-color: #7c3aed;
}

.al-bulk-action-btn.is-edit {
  border-color: #67e8f9;
  background: #fff;
  color: #0891b2;
}

.al-bulk-action-btn.is-edit:hover {
  background: #0891b2;
  color: #fff;
  border-color: #0891b2;
}

.al-bulk-clear-btn {
  font-size: 12px;
  font-weight: 500;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #94a3b8;
  cursor: pointer;
  margin-left: auto;
  transition: all 0.15s;
}

.al-bulk-clear-btn:hover {
  color: #475569;
  border-color: #cbd5e1;
}

.bulk-bar-enter-active,
.bulk-bar-leave-active {
  transition: all 0.2s ease;
}

.bulk-bar-enter-from,
.bulk-bar-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ── Flag 管理弹窗 ─────────────────────────────────────────────────────────── */
.fm-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.fm-form {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fm-form-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
}

.fm-form-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.fm-input {
  flex: 1;
  height: 36px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0 12px;
  font-size: 14px;
  color: #0f172a;
  outline: none;
  transition: border-color 0.15s;
}

.fm-input:focus {
  border-color: #6366f1;
}

.fm-color-picker {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fm-color-preview {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,.15);
  flex-shrink: 0;
}

.fm-color-swatches {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  max-width: 180px;
}

.fm-swatch {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  transition: transform 0.12s, border-color 0.12s;
  outline: none;
}

.fm-swatch:hover { transform: scale(1.2); }
.fm-swatch.active { border-color: #fff; box-shadow: 0 0 0 2px #6366f1; }

.fm-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.fm-cancel-btn {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #64748b;
  cursor: pointer;
}

.fm-save-btn {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 16px;
  border-radius: 8px;
  border: none;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s;
}

.fm-save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 快捷标签开关 */
.fm-pin-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.fm-pin-checkbox {
  width: 14px;
  height: 14px;
  accent-color: #6366f1;
  cursor: pointer;
  flex-shrink: 0;
}

.fm-pin-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: #475569;
}

.fm-list { display: flex; flex-direction: column; gap: 10px; }

/* 分组 */
.fm-group { display: flex; flex-direction: column; gap: 5px; }

.fm-group-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-bottom: 2px;
}

.fm-item.is-pinned {
  border-color: #e0e7ff;
  background: #f5f3ff;
}

.fm-empty {
  font-size: 13px;
  color: #cbd5e1;
  text-align: center;
  padding: 12px;
}

.fm-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #f1f5f9;
  border-radius: 10px;
  background: #fff;
}

.fm-item-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #e2e8f0;
  flex-shrink: 0;
}

.fm-item-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: #334155;
}

.fm-item-actions {
  display: flex;
  gap: 5px;
}

.fm-edit-btn,
.fm-del-btn {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #fff;
  cursor: pointer;
  transition: all 0.12s;
}

.fm-edit-btn { color: #6366f1; border-color: #c7d2fe; background: #eef2ff; }
.fm-edit-btn:hover { background: #6366f1; color: #fff; }

.fm-del-btn { color: #dc2626; border-color: #fecaca; background: #fef2f2; }
.fm-del-btn:hover { background: #ef4444; color: #fff; border-color: #ef4444; }
.fm-del-btn.loading { opacity: 0.5; pointer-events: none; }

/* ── 批量标识弹窗 ──────────────────────────────────────────────────────────── */
.bfd-body { display: flex; flex-direction: column; gap: 14px; }

.bfd-hint {
  font-size: 13px;
  color: #475569;
}

.bfd-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.bfd-flag-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  cursor: pointer;
  transition: all 0.12s;
  user-select: none;
}

.bfd-flag-item:hover { border-color: #a5b4fc; background: #eef2ff; }

.bfd-flag-item.selected {
  border-color: #6366f1;
  background: #eef2ff;
  font-weight: 600;
}

.bfd-checkbox { display: none; }

.bfd-flag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
}

.bfd-flag-name { font-size: 13px; color: #334155; }

.bfd-empty {
  font-size: 13px;
  color: #94a3b8;
  text-align: center;
  padding: 16px;
}

/* ── 视频分类弹窗 ────────────────────────────────────────────────── */
.vc-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 70vh;
  overflow: auto;
}

.vc-overview {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.vc-overview-left { display: flex; flex-direction: column; gap: 6px; }

.vc-overview-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #64748b;
}

.vc-status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #cbd5e1;
}
.vc-status-dot.is-running { background: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,.18); }
.vc-status-dot.is-idle { background: #94a3b8; }

.vc-overview-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.vc-type-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 500;
}
.vc-type-tag.is-single { background: #dcfce7; color: #166534; }
.vc-type-tag.is-dual { background: #dbeafe; color: #1d4ed8; }
.vc-type-tag.is-chaos { background: #fee2e2; color: #991b1b; }
.vc-type-tag.is-insufficient { background: #fef3c7; color: #92400e; }
.vc-type-tag.is-none { background: #e5e7eb; color: #4b5563; }

.vc-type-name { font-size: 14px; font-weight: 600; color: #0f172a; }

.vc-overview-counts { font-size: 12px; color: #475569; }

.vc-overview-right { display: flex; gap: 8px; align-items: center; }

.vc-charts {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 12px;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}
.vc-chart { width: 100%; }
.vc-chart-major { height: 220px; }
.vc-chart-category { height: 220px; min-width: 0; }

.vc-groups { display: flex; flex-direction: column; gap: 14px; }

.vc-group-header {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 8px;
}
.vc-group-name {
  font-size: 13px; font-weight: 600; color: #0f172a;
}
.vc-group-name.is-processing { color: #6366f1; }
.vc-group-name.is-pending { color: #ca8a04; }
.vc-group-name.is-success { color: #16a34a; }
.vc-group-name.is-failed { color: #dc2626; }
.vc-group-name.is-not_started { color: #94a3b8; }
.vc-group-name.is-no_local_video { color: #f59e0b; }

.vc-group-count {
  font-size: 11px; color: #64748b;
  background: #f1f5f9;
  border-radius: 999px;
  padding: 1px 8px;
}

.vc-group-list { display: flex; flex-direction: column; gap: 6px; }

.vc-item {
  display: flex; gap: 10px;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fff;
}
.vc-item.is-processing { border-color: #c7d2fe; background: #eef2ff; }
.vc-item.is-failed { border-color: #fecaca; background: #fef2f2; }
.vc-item.is-not_started, .vc-item.is-no_local_video { background: #fafafa; opacity: 0.7; }

.vc-item-thumb {
  width: 108px; height: 192px;   /* 9:16 */
  border-radius: 4px;
  background: #0f172a;
  flex-shrink: 0;
  overflow: hidden;
  position: relative;
  cursor: pointer;
}
.vc-thumb-video {
  width: 100%; height: 100%; object-fit: cover;
  background: #000;
  display: block;
}
.vc-item-thumb-expand {
  position: absolute;
  top: 4px; right: 4px;
  width: 24px; height: 24px;
  background: rgba(0,0,0,0.45);
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}
.vc-item-thumb:hover .vc-item-thumb-expand { opacity: 1; }

/* 自定义全屏遮罩 */
.vc-fullscreen-mask {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.vc-fullscreen-video {
  height: 100vh;
  width: calc(100vh * 9 / 16);
  max-width: 100vw;
  object-fit: contain;
  background: #000;
  display: block;
}
.vc-fullscreen-close {
  position: absolute;
  top: 16px; right: 16px;
  width: 36px; height: 36px;
  background: rgba(255,255,255,0.15);
  border: none;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  color: #fff;
  z-index: 1;
}
.vc-fullscreen-close:hover { background: rgba(255,255,255,0.3); }
.vc-item-thumb-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: #94a3b8;
  background: #f1f5f9;
}

.vc-item-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.vc-item-title {
  font-size: 13px; color: #0f172a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.vc-item-meta { font-size: 11px; color: #64748b; }
.vc-item-cat { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.vc-major-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.vc-major-tag.is-display { background: #fce7f3; color: #be185d; }
.vc-major-tag.is-knowledge { background: #dbeafe; color: #1d4ed8; }
.vc-major-tag.is-persona { background: #ede9fe; color: #6d28d9; }
.vc-major-tag.is-trending { background: #ffedd5; color: #c2410c; }
.vc-cat-label { font-size: 12px; color: #334155; }
.vc-item-status { font-size: 12px; color: #64748b; }
.vc-item-status.is-warn { color: #d97706; }
.vc-item-status.is-muted { color: #94a3b8; }
.vc-item-error {
  font-size: 12px;
  color: #dc2626;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.vc-empty {
  text-align: center;
  font-size: 13px;
  color: #94a3b8;
  padding: 24px;
}

.ac-kol-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-width: 0;
}
.ac-kol-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ac-kol-pending { background: #fef3c7; color: #b45309; }
.ac-kol-failed  { background: #fee2e2; color: #b91c1c; }
.ac-kol-success { background: #dcfce7; color: #15803d; }
.ac-kol-retry-btn {
  margin-left: 4px;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid #fca5a5;
  background: #fff;
  color: #b91c1c;
  cursor: pointer;
  line-height: 1.4;
}
.ac-kol-retry-btn:hover:not(:disabled) {
  background: #fee2e2;
  border-color: #ef4444;
}
.ac-kol-retry-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ac-kol-link {
  color: #2563eb;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ac-kol-link:hover { text-decoration: underline; }
.ac-kol-link-empty {
  color: #94a3b8;
  font-style: italic;
  font-family: monospace;
  font-size: 11px;
}
.ac-kol-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
  min-width: 0;
}
.ac-kol-platform-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.ac-kol-platform-tag {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
  background: #e2e8f0;
  color: #334155;
  text-transform: uppercase;
  min-width: 24px;
  text-align: center;
  line-height: 1.35;
  flex-shrink: 0;
}
.ac-kol-platform-youtube   { background: #fee2e2; color: #b91c1c; }
.ac-kol-platform-tiktok    { background: #1e293b; color: #f8fafc; }
.ac-kol-platform-instagram { background: #fce7f3; color: #9d174d; }

/* ── ac-btn-analytics ─────────────────────────────────────────────────── */
.ac-btn-analytics {
  background: #ede9fe;
  color: #6d28d9;
  border-color: #c4b5fd;
}
.ac-btn-analytics:hover { background: #ddd6fe; }

/* ── 频道数据分析弹窗 (ana-*) ─────────────────────────────────────────── */
.ana-body { padding: 0 2px; }

.ana-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.ana-platform-tabs {
  display: flex;
  gap: 6px;
}
.ana-tab {
  padding: 4px 14px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
  font-size: 13px;
  cursor: pointer;
  text-transform: capitalize;
  transition: background .15s, color .15s;
}
.ana-tab.active {
  background: #6d28d9;
  color: #fff;
  border-color: #6d28d9;
}
.ana-tab:hover:not(.active) { background: #ede9fe; color: #6d28d9; }

.ana-metrics {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.ana-metric-card {
  flex: 1;
  min-width: 160px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 16px;
}
.ana-metric-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}
.ana-metric-value {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.2;
}

.ana-charts { display: flex; flex-direction: column; gap: 20px; }
.ana-chart-row {}
.ana-chart-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 6px;
}
.ana-chart-canvas { height: 160px; width: 100%; display: block; }

.ana-loading, .ana-error, .ana-empty {
  text-align: center;
  padding: 40px 0;
  color: #94a3b8;
  font-size: 14px;
}
.ana-error { color: #ef4444; }
</style>
