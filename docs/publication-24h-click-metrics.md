# 数据统计页 24h 点击统计改造说明

## 目标

这次改造给「数据统计」页面补了两项新指标：

- `24h 点击次数`
- `24h 点击率`

口径统一为：

- 统计窗口：`视频发布完成时间 completed_at` 到 `completed_at + 24 小时`
- 点击次数：该窗口内，视频所属 AI 博主短链/长链在事件库中的点击总和
- 点击率：`24h 点击次数 / 24h 时刻抓取到的播放量`

其中：

- 不是按自然日统计
- 不是有史以来累计点击
- 当 `views_24h_snapshot` 为 `0` 或缺失时，不展示点击率

## 数据来源

### 点击数据

点击数据来自 BigQuery：

- 表：`my-project-8584-jetonai.decom.dwd_event_log`
- 事件：`event_name = 'v_thirdapp_open'`
- 链接字段：`JSON_VALUE(args, '$.current_url')`
- 来源字段过滤：`JSON_VALUE(args, '$.sf') != ''`

最终查询不是按天累计，而是按精确时间窗：

```sql
SELECT COUNT(*) AS clicks_24h
FROM `my-project-8584-jetonai.decom.dwd_event_log`
WHERE DATE(logAt_timestamp) BETWEEN DATE(@window_start) AND DATE(TIMESTAMP_SUB(@window_end, INTERVAL 1 SECOND))
  AND logAt_timestamp >= @window_start
  AND logAt_timestamp < @window_end
  AND event_name = 'v_thirdapp_open'
  AND JSON_VALUE(args, '$.sf') != ''
  AND JSON_VALUE(args, '$.current_url') IN UNNEST(@links)
```

说明：

- `DATE(...)` 只用于分区裁剪
- 真正的归因口径由 `logAt_timestamp >= @window_start AND logAt_timestamp < @window_end` 决定

### 播放量数据

播放量仍然来自现有发布 metrics 接口。

在点击任务触发时，会同步拉取一次该视频的 metrics，并把当时的播放量固化到：

- `views_24h_snapshot`

这样可以保证点击率口径稳定，不会被后续持续增长的总播放量稀释。

## 数据库变更

### `video_publications`

新增字段：

- `click_metrics_24h_snapshot JSON`

用途：

- 存放 24 小时点击快照、24 小时播放量快照、CTR 以及明细链接

典型结构：

```json
{
  "status": "completed",
  "window_start_at": "2026-05-22T10:37:00+00:00",
  "window_end_at": "2026-05-23T10:37:00+00:00",
  "synced_at": "2026-05-23T10:42:00+00:00",
  "views_24h_snapshot": 120300,
  "total_clicks_24h": 612,
  "ctr_24h": 0.51,
  "links": [
    {
      "platform": "youtube",
      "short_link": "https://alvc.me/xxxx",
      "long_link": "https://www.alvinclub.ai/en-us/m/vibe?...",
      "query_links": [
        "https://alvc.me/xxxx",
        "https://www.alvinclub.ai/en-us/m/vibe?..."
      ],
      "query_link_counts": [
        { "link": "https://alvc.me/xxxx", "clicks": 612 }
      ],
      "clicks": 612
    }
  ],
  "error_message": null
}
```

Alembic migration：

- `backend/alembic/versions/0059_add_publication_click_metrics_snapshot.py`

## 后端改造

### 1. 新增点击统计服务

文件：

- `backend/app/services/publication_click_metrics_service.py`

职责：

- 扫描满足 `completed_at + 24h <= now` 的发布记录
- 找出该发布对应平台的渠道绑定
- 读取绑定上的 `kol_short_link / kol_long_link`
- 对短链和长链统一去重后一起查询
- 聚合点击次数
- 再调用现有 metrics 接口抓一次 24h 播放量
- 生成并落库 `click_metrics_24h_snapshot`

关键点：

- 一条发布如果有多个平台，会把多个平台的链接点击数求和
- 同一平台会同时查询短链和长链，避免埋点只落其中一种格式
- 已完成快照不会重复跑；失败记录可以重跑

### 2. 新增独立调度器

文件：

- `backend/app/services/publication_click_metrics_scheduler.py`

职责：

- 独立于现有每日 metrics scheduler
- 按轮询方式扫描“已到 24h 且未完成快照”的发布记录

默认配置：

- `PUBLICATION_CLICK_METRICS_POLL_INTERVAL_SEC=600`

即每 10 分钟轮询一次。

这样做的原因：

- 你的需求是“每个视频到 24 小时自动触发”
- 不适合挂到现有每天固定时刻的 scheduler 上

### 3. 接入应用启动

文件：

- `backend/app/main.py`

应用启动时会同时启动：

- 原有指标同步调度器
- 新的 24h 点击快照调度器

### 4. 接入统计页 API

文件：

- `backend/app/services/video_publication_service.py`
- `backend/app/api/v1/video_publications.py`
- `backend/app/schemas/video_publication.py`

新增返回字段：

- `clicks_24h`
- `views_24h_snapshot`
- `ctr_24h`
- `click_metrics_status`

同时支持前端按下面两个字段排序：

- `clicks_24h`
- `ctr_24h`

### 5. 手动同步入口

统计页原本就有“同步数据”按钮。

这次改造后：

- 原有 metrics 同步逻辑保留
- 同步按钮后台任务执行完 metrics 后，会顺手触发一次“已到期的 24h 点击快照同步”

这样有两个好处：

- 本地联调和补历史数据更方便
- 线上某些视频即使错过自动触发，也可以通过页面手动补数

## 前端改造

文件：

- `frontend/src/views/PublicationStatsView.vue`

### 表格新增列

- `24h点击`
- `24h点击率`

### 详情抽屉新增汇总卡片

- `24h 点击次数`
- `24h 点击率`

### 顶部已勾选聚合卡片接入真实数据

原来页面上已有占位：

- 转化数（搜索次数）
- 转化率
- 平均转化数
- 平均转化率

现在统一映射为：

- 转化数 -> 已勾选视频 `clicks_24h` 总和
- 转化率 -> 已勾选视频 `clicks_24h / views_24h_snapshot` 的加权结果
- 平均转化数 -> 已勾选视频平均 `clicks_24h`
- 平均转化率 -> 已勾选视频逐条 CTR 的平均值

## 配置变更

文件：

- `backend/app/core/config.py`
- `backend/.env.example`

新增配置：

- `BIGQUERY_PROJECT_ID`
- `PUBLICATION_CLICK_METRICS_POLL_INTERVAL_SEC`

默认值：

- `BIGQUERY_PROJECT_ID=my-project-8584-jetonai`
- `PUBLICATION_CLICK_METRICS_POLL_INTERVAL_SEC=600`

## 依赖变更

文件：

- `backend/pyproject.toml`
- `backend/uv.lock`

新增依赖：

- `google-cloud-bigquery`

本地 SQLite 启动时还需要 `aiosqlite`；如果是通过 `uv` 装完整依赖，应该会一起解决。

## 这次没有改动的部分

为了避免影响既有逻辑，这次没有动：

- 原有播放量/点赞/评论/分享的采集结构
- 原有每日 account `performance_snapshot` 聚合逻辑
- 发布流程本身
- 已有 metrics_snapshot 的字段格式

也就是说，这次是新增一条独立的“24h 点击归因”链路，而不是重写原有统计链路。

## 上线前注意事项

### 1. 先跑 migration

需要先执行：

- Alembic upgrade 到包含 `0059` 的版本

否则后端会缺字段。

### 2. 确认 BigQuery 凭证

运行环境需要能访问：

- `my-project-8584-jetonai.decom.dwd_event_log`

如果本地 / 服务器使用 ADC 凭证，并带有 `quota_project_id` 导致 `USER_PROJECT_DENIED`，当前实现会沿用已有处理方式，优先在进程内移除该字段再构造 BigQuery client。

### 3. CTR 为空是正常情况

以下情况 CTR 会显示为空：

- 视频还没满 24 小时
- 24 小时快照还未跑完
- 24 小时时刻播放量是 `0`
- 24 小时时刻播放量缺失

### 4. 链接变更带来的归因限制

当前实现读取的是“任务执行时账号当前绑定的平台链接”。

这意味着：

- 如果账号在视频发布后、24h 快照触发前发生换绑
- 理论上可能会把点击归到新链接

这是当前版本的已知边界。

更严格的后续方案可以是：

- 在 publication 创建或发布完成时，就把当时的 `kol_short_link / kol_long_link` 冗余快照到 `video_publications`
- 24h 任务只使用 publication 自己保存的链接，不再回看账号当前绑定

如果后面要进一步提高归因稳定性，建议优先做这一步。

## 本次提交涉及的关键文件

- `backend/app/models/video_publication.py`
- `backend/app/schemas/video_publication.py`
- `backend/app/services/publication_click_metrics_service.py`
- `backend/app/services/publication_click_metrics_scheduler.py`
- `backend/app/services/video_publication_service.py`
- `backend/app/api/v1/video_publications.py`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/alembic/versions/0059_add_publication_click_metrics_snapshot.py`
- `frontend/src/views/PublicationStatsView.vue`
- `backend/pyproject.toml`
- `backend/uv.lock`
