import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from app.schemas.video_ai_template import TagRead
from app.schemas.video_ai_template import VideoSourceSummary


class VideoTaskCreate(BaseModel):
    account_id: uuid.UUID
    template_id: uuid.UUID
    final_prompt: str
    duration: str
    shots: list | None = None


class VideoSubTaskRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    sub_index: int
    status: str
    result_video_url: str | None = None
    selected: bool
    manual_note: str | None = None
    operator: str | None = None
    has_ng: bool | None = None
    ng_timestamps: list | None = None   # [{"second": 10, "frame": 5}, ...]
    dimension_scores: dict | None = None
    weighted_total_score: float | None = None
    queue_order: int | None = None
    publish_meta: dict | None = None   # {"status": "pending"|"generating"|"done"|"failed", "title": "...", "description": "...", "hashtags": [...]}
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class VideoTaskRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    account_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    target_date: date
    status: str
    prompt: str
    is_prompt_updated: bool = False
    duration: str
    shots: list | None = None
    has_face: bool = True
    cta: bool = False  # 创建任务时按 account.product_code_mode 推算（with_code → True）
    is_reused_template: bool = False
    template_reuse_reason: str | None = None
    template_usage_index: int | None = None
    template_used_at: datetime | None = None
    template_usage_source: str | None = None
    template_usage_source_step: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class VideoTaskDetailRead(VideoTaskRead):
    sub_tasks: list[VideoSubTaskRead] = []
    account_name: str | None = None
    template_title: str | None = None
    tags: list[TagRead] = []
    original_video: VideoSourceSummary | None = None


class VideoTaskListItem(VideoTaskDetailRead):
    """Enriched list item with denormalized account/template names and sub-task progress."""
    sub_tasks_done: int = 0  # number of sub-tasks with result_video_url set


class VideoTaskListPage(BaseModel):
    items: list[VideoTaskListItem]
    total: int
    page: int
    page_size: int


class VideoSubTaskListPage(BaseModel):
    items: list[VideoSubTaskRead]
    total: int
    page: int
    page_size: int


class TaskSummaryForSub(BaseModel):
    id: uuid.UUID
    target_date: date
    prompt: str
    template_title: str | None = None
    is_reused_template: bool = False
    template_reuse_reason: str | None = None
    template_usage_index: int | None = None
    template_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class VideoSubTaskWithTaskRead(VideoSubTaskRead):
    """Sub-task enriched with parent task info, for AccountDetailView per-tab pagination."""
    task: TaskSummaryForSub


class VideoSubTaskWithTaskPage(BaseModel):
    items: list[VideoSubTaskWithTaskRead]
    total: int
    page: int
    page_size: int


class VideoSubTaskStatusUpdate(BaseModel):
    status: str
    result_video_url: str | None = None
    # When selecting a video: set selected=True to trigger stashed transition and abandon siblings
    selected: bool | None = None


class VideoSubTaskNoteUpdate(BaseModel):
    operator: str | None = None  # 无 token 时必须传；有 token 时忽略（取登录用户名）
    status: str = "stashed"      # 目标状态：stashed（通过）或 decision_rejected（决策未通过）
    manual_note: str | None = None
    has_ng: bool | None = None
    ng_timestamps: list | None = None   # [{"second": 10, "frame": 5}, ...]
    dimension_scores: dict | None = None


class VideoSubTaskStateRead(BaseModel):
    id: uuid.UUID
    status: str
    result_video_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class VideoTaskStateRead(BaseModel):
    id: uuid.UUID
    status: str
    sub_tasks: list[VideoSubTaskStateRead] = []

    model_config = ConfigDict(from_attributes=True)


class OperatorSubTaskItem(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    sub_index: int
    status: str
    result_video_url: str | None = None
    has_ng: bool | None = None
    weighted_total_score: float | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OperatorStatItem(BaseModel):
    operator: str
    count: int
    sub_tasks: list[OperatorSubTaskItem]


class TaskNavItem(BaseModel):
    id: uuid.UUID
    status: str
    account_id: uuid.UUID | None = None
    account_name: str | None = None


class VideoTaskNavRead(BaseModel):
    position: int        # 0-based index in account task list (DESC by created_at)
    total: int           # total tasks for this account
    selected_count: int  # tasks with stashed/queued/publishing/published status
    prev_task: TaskNavItem | None = None
    next_task: TaskNavItem | None = None
    prev_blogger_task: TaskNavItem | None = None
    next_blogger_task: TaskNavItem | None = None
