# AI 博主公开查询 API

本文档面向外部调用团队，用于查询 AI 博主基础信息、绑定平台，以及按需查询某个 AI 博主在某个平台发布的视频。

接口为只读查询接口，不会创建、确认、绑定或释放账号平台占用。

## 服务地址

```text
https://<host>/api/v1
```

实际域名/公网地址以部署环境为准。

## 认证方式

所有请求必须在 Header 中传入 API Key：

```http
X-API-Key: <api_key>
```

服务端通过 `.env` 配置同一个 Key：

```env
ACCOUNT_CHANNEL_API_KEY=<api_key>
```

未传、传错或服务端未配置时，请求会失败。

## owner_id 说明

调用方不需要传 `owner_id`。

服务端从 `.env` 读取默认归属：

```env
ACCOUNT_CHANNEL_OWNER_ID=<uuid>
```

两个接口都只返回该 `owner_id` 下的数据。这样可以避免外部调用方感知或误传内部租户 ID。

---

## 1. 分页查询 AI 博主

分页返回 AI 博主基础信息和已绑定平台，不返回发布视频。

```http
GET /open-api/accounts
```

### Query 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | integer | 否 | `1` | 页码，从 1 开始 |
| `page_size` | integer | 否 | `20` | 分页大小，范围 `1..100` |
| `gender` | string | 否 | 无 | 性别过滤，支持 `male` / `female` / `unisex` |
| `platform` | string | 否 | 无 | 只返回绑定了指定平台的 AI 博主，支持 `youtube` / `tiktok` / `instagram` |

### 默认过滤规则

- 只返回 `.env` 中 `ACCOUNT_CHANNEL_OWNER_ID` 对应的数据。
- 只返回 `hidden = false` 的 AI 博主。
- 只返回至少有一个已绑定平台的 AI 博主。
- 平台绑定只返回 `status = bound` 的记录。

### 请求示例

```bash
curl -X GET 'https://<host>/api/v1/open-api/accounts?page=1&page_size=20&platform=youtube' \
  -H 'X-API-Key: <api_key>'
```

### 响应示例

```json
{
  "items": [
    {
      "account_id": "c673e254-5eae-4b87-a1d3-b247258476b4",
      "account_name": "Sonny Winter Fits",
      "account_handle": "sonny_winter_7days",
      "account_signature": "Daily outfit ideas",
      "gender": "female",
      "account_type": "exclusive",
      "account_tier": "prod",
      "avatar_url": "https://example.com/avatar.jpg",
      "photo_url": "https://example.com/photo.jpg",
      "hashtags": ["outfitideas", "fashioninspo"],
      "created_at": "2026-04-15T07:13:50.401492Z",
      "updated_at": "2026-04-15T07:13:50.401492Z",
      "platforms": [
        {
          "platform": "youtube",
          "channel_status": "active",
          "channel_source": "openapi",
          "channel_id": "UCgBJozWjiE0cqwv7UNalyog",
          "channel_name": "Sonny Winter Fits",
          "username": "@sonny",
          "avatar_url": "https://example.com/channel-avatar.jpg",
          "kol_long_link": "https://www.alvinclub.ai/en-us/m/vibe/...",
          "kol_short_link": "https://alvc.me/abc123",
          "bound_at": "2026-04-20T09:30:00Z"
        }
      ]
    }
  ],
  "total": 120,
  "page": 1,
  "page_size": 20
}
```

### 响应字段说明

#### 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | array | AI 博主列表 |
| `total` | integer | 符合条件的 AI 博主总数 |
| `page` | integer | 当前页码 |
| `page_size` | integer | 当前分页大小 |

#### `items[]`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account_id` | uuid | AI 博主 ID |
| `account_name` | string | AI 博主名称 |
| `account_handle` | string/null | AI 博主 handle |
| `account_signature` | string/null | 个性签名 |
| `gender` | string | 性别：`male` / `female` / `unisex` |
| `account_type` | string | 账号类型 |
| `account_tier` | string | 账号层级 |
| `avatar_url` | string/null | AI 博主头像 |
| `photo_url` | string/null | AI 博主照片 |
| `hashtags` | array/null | 账号 hashtag |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |
| `platforms` | array | 已绑定平台列表 |

#### `items[].platforms[]`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `platform` | string | 平台：`youtube` / `tiktok` / `instagram` |
| `channel_status` | string | 频道状态，例如 `active` / `disabled` |
| `channel_source` | string | 绑定来源，例如 `openapi` / `ext_pub` |
| `channel_id` | string/null | 平台频道 ID |
| `channel_name` | string/null | 平台频道名 |
| `username` | string/null | 平台 username/handle |
| `avatar_url` | string/null | 平台头像 |
| `kol_long_link` | string/null | KOL 长链 |
| `kol_short_link` | string/null | KOL 短链 |
| `bound_at` | datetime/null | 绑定时间 |

---

## 2. 分页查询 AI 博主某个平台的视频

根据 AI 博主 `account_id` 和平台 `platform` 查询该平台已发布的视频。这个接口单独分页返回视频，适合外部团队在用户展开某个 AI 博主的平台详情时再调用。

```http
GET /open-api/accounts/{account_id}/platforms/{platform}/videos
```

### Path 参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account_id` | uuid | 是 | AI 博主 ID，来自第一个接口的 `items[].account_id` |
| `platform` | string | 是 | 平台，支持 `youtube` / `tiktok` / `instagram` |

### Query 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | integer | 否 | `1` | 视频页码，从 1 开始 |
| `page_size` | integer | 否 | `20` | 视频分页大小，范围 `1..100` |

### 默认过滤规则

- 只返回 `.env` 中 `ACCOUNT_CHANNEL_OWNER_ID` 对应的数据。
- `account_id` 必须属于该 `owner_id`。
- `account_id + platform` 必须存在 `status = bound` 的平台绑定记录。
- 只返回发布成功或部分成功的视频，即发布状态 `completed` / `partial`。
- 视频按发布时间倒序排列。

### 请求示例

```bash
curl -X GET 'https://<host>/api/v1/open-api/accounts/c673e254-5eae-4b87-a1d3-b247258476b4/platforms/youtube/videos?page=1&page_size=20' \
  -H 'X-API-Key: <api_key>'
```

### 响应示例

```json
{
  "account_id": "c673e254-5eae-4b87-a1d3-b247258476b4",
  "platform": "youtube",
  "channel": {
    "channel_status": "active",
    "channel_source": "openapi",
    "channel_id": "UCgBJozWjiE0cqwv7UNalyog",
    "channel_name": "Sonny Winter Fits",
    "username": "@sonny",
    "avatar_url": "https://example.com/channel-avatar.jpg",
    "kol_long_link": "https://www.alvinclub.ai/en-us/m/vibe/...",
    "kol_short_link": "https://alvc.me/abc123",
    "bound_at": "2026-04-20T09:30:00Z"
  },
  "items": [
    {
      "publication_id": "43a01d69-5fa8-45f2-a353-3c8cb268c272",
      "task_id": "ede56eb4-c65e-424a-92a2-9cb32871943c",
      "sub_task_id": "d3f8b885-b608-4c72-ae7c-2f50c6f4d1f6",
      "status": "completed",
      "title": "Spring Outfit Ideas",
      "description": "Daily outfit inspiration",
      "video_url": "https://cdn.alvinclub.com/videos/final.mp4",
      "platform_video_id": "Nf4DjLPXaEY",
      "platform_video_url": "https://www.youtube.com/watch?v=Nf4DjLPXaEY",
      "thumbnail_url": "https://example.com/thumb.jpg",
      "published_at": "2026-05-20T08:00:00Z",
      "promotion_code": "27383065",
      "metrics": {
        "views": 1200,
        "likes": 88,
        "comments": 5,
        "shares": 2
      }
    }
  ],
  "total": 24,
  "page": 1,
  "page_size": 20
}
```

### 响应字段说明

#### 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account_id` | uuid | AI 博主 ID |
| `platform` | string | 平台 |
| `channel` | object | 当前平台绑定信息 |
| `items` | array | 视频列表 |
| `total` | integer | 符合条件的视频总数 |
| `page` | integer | 当前页码 |
| `page_size` | integer | 当前分页大小 |

#### `items[]`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `publication_id` | uuid | 发布记录 ID |
| `task_id` | uuid/null | 视频任务 ID |
| `sub_task_id` | uuid | 视频子任务 ID |
| `status` | string | 发布状态 |
| `title` | string/null | 发布标题 |
| `description` | string/null | 发布描述 |
| `video_url` | string/null | 系统内部生成视频 URL，来源于 `video_sub_tasks.result_video_url`；如果是 GCS URL，服务端返回前会检查有效期并自动续签 |
| `platform_video_id` | string/null | 平台视频 ID |
| `platform_video_url` | string/null | 平台公开视频 URL |
| `thumbnail_url` | string/null | 视频封面 |
| `published_at` | datetime/null | 发布时间 |
| `promotion_code` | string/null | 带货口令 |
| `metrics.views` | integer | 播放量 |
| `metrics.likes` | integer | 点赞数 |
| `metrics.comments` | integer | 评论数 |
| `metrics.shares` | integer | 分享数 |

---

## 错误响应

### 401 API Key 错误

```json
{
  "detail": "Invalid api_key"
}
```

### 404 账号或平台绑定不存在

```json
{
  "detail": "账号或平台绑定不存在"
}
```

### 503 服务端未配置 API Key

```json
{
  "detail": "ACCOUNT_CHANNEL_API_KEY 未配置"
}
```

### 500 服务端未配置 owner_id

```json
{
  "detail": "服务端 ACCOUNT_CHANNEL_OWNER_ID 未配置"
}
```

### 422 参数校验失败

FastAPI 会返回标准参数校验错误，例如 `page_size` 超过上限、`platform` 不在支持范围内等。

---

## 服务端实现逻辑

准备按下面逻辑实现。

### 1. 公共鉴权与 owner_id 解析

两个接口都执行相同逻辑：

1. 从请求 Header 读取 `X-API-Key`。
2. 与 `.env` 的 `ACCOUNT_CHANNEL_API_KEY` 做常量时间比较。
3. 鉴权通过后，从 `.env` 的 `ACCOUNT_CHANNEL_OWNER_ID` 读取 `owner_id`。
4. 请求参数中不接收 `owner_id`，避免外部团队切换或猜测内部租户数据。

### 2. AI 博主分页接口逻辑

以 `accounts` 为主表分页查询。

过滤条件：

```text
accounts.owner_id = ACCOUNT_CHANNEL_OWNER_ID
accounts.hidden = false
EXISTS account_channel_reservations(status = 'bound')
```

可选过滤：

```text
gender
platform
```

然后对当前页账号批量查询绑定平台：

```text
account_channel_reservations.account_id IN 当前页账号
account_channel_reservations.status = 'bound'
platform = 请求 platform（如果有）
```

这个接口不查询 `video_publications`，也不触发 GCS 续签。

### 3. 平台视频分页接口逻辑

先校验账号和平台绑定：

```text
accounts.id = account_id
accounts.owner_id = ACCOUNT_CHANNEL_OWNER_ID
accounts.hidden = false
account_channel_reservations.account_id = account_id
account_channel_reservations.platform = platform
account_channel_reservations.status = 'bound'
```

不存在则返回 `404`。

然后按视频维度分页查询发布记录：

```text
video_tasks.account_id = account_id
video_publications.status IN ('completed', 'partial')
```

关联链路：

```text
video_tasks.id
  -> video_sub_tasks.task_id
video_sub_tasks.id
  -> video_publications.sub_task_id
```

排序：

```text
video_publications.completed_at DESC NULLS LAST,
video_publications.created_at DESC
```

### 4. 平台视频匹配逻辑

一次发布可能发到多个平台，所以接口只返回与 path 中 `platform` 匹配的视频。

平台级视频信息优先从发布记录 JSON 中提取：

1. 优先读 `video_publications.metrics_snapshot.channels[]`。
2. 如果没有，再读 `video_publications.channels_status[]`。
3. 用 `platform + channel_id` 匹配当前账号的平台绑定。
4. 提取平台视频 URL、平台视频 ID、封面和指标。

匹配不到平台级记录时，不返回该发布记录，避免错误归属到当前平台。

### 5. GCS 视频 URL 续签逻辑

`video_url` 来源于 `video_sub_tasks.result_video_url`。

视频接口返回前必须处理当前页命中的 `VideoSubTask`：

1. 使用现有工具 `app.utils.gcs_signing.ensure_sub_tasks_signed_urls()` 批量处理。
2. 非 GCS URL，例如旧 CDN URL，原样返回。
3. GCS V4 签名 URL 如果剩余有效期大于 1 天，原样返回。
4. GCS URL 如果未签名或剩余有效期小于等于 1 天，重新签一个 7 天有效的 V4 URL。
5. 新签名 URL 会回写到 `video_sub_tasks.result_video_url`，接口响应使用续签后的 URL。

如果续签失败，接口不阻塞，退化返回原 URL，并记录服务端错误日志。

### 6. 返回结构

最终形成渐进式查询：

```text
GET /open-api/accounts
  -> 返回 AI 博主基础信息 + 绑定平台

GET /open-api/accounts/{account_id}/platforms/{platform}/videos
  -> 返回指定 AI 博主指定平台的视频分页
```

这种方式避免账号列表接口返回大量视频，也避免列表查询触发大量 GCS 续签。
