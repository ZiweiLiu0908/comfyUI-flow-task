"""
外部 AI 博主公开查询接口测试脚本。

用法：
1. 手动填写下面的 BASE_URL / API_KEY。
2. 按需要修改 ACTION 和参数。
3. 执行：
   cd backend
   uv run python scripts/test_external_account_query_openapi.py

说明：
- 不传 owner_id；服务端从 .env 的 ACCOUNT_CHANNEL_OWNER_ID 读取。
- ACTION="accounts" 只测试账号分页接口。
- ACTION="videos" 测试指定 account_id + platform 的视频分页接口。
- ACTION="auto" 先查账号列表，再自动用第一条账号的第一个平台查视频。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


BASE_URL = "http://34.55.116.212:8000/api/v1"
API_KEY = ""  # 可手动填写；为空时自动读取 backend/.env 的 ACCOUNT_CHANNEL_API_KEY

# accounts 接口参数
ACCOUNTS_PAGE = 1
ACCOUNTS_PAGE_SIZE = 20
ACCOUNTS_GENDER = ""  # male / female / unisex；空字符串表示不传
ACCOUNTS_PLATFORM = ""  # youtube / tiktok / instagram；空字符串表示不传

# videos 接口参数：ACTION="videos" 时必填
VIDEOS_ACCOUNT_ID = ""
VIDEOS_PLATFORM = "youtube"  # youtube / tiktok / instagram
VIDEOS_PAGE = 1
VIDEOS_PAGE_SIZE = 20

# accounts / videos / auto
ACTION = "auto"


def _load_env_value(key: str) -> str:
    """读取当前环境变量；没有则从 backend/.env 解析简单 KEY=VALUE。"""
    value = os.getenv(key, "")
    if value:
        return value

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        if name.strip() != key:
            continue
        return raw_value.strip().strip('"').strip("'")
    return ""


def _api_key() -> str:
    return API_KEY or _load_env_value("ACCOUNT_CHANNEL_API_KEY")


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any] | str:
    url = f"{BASE_URL.rstrip('/')}{path}"
    api_key = _api_key()
    if not api_key:
        raise SystemExit("API_KEY 为空，且未能从 backend/.env 读取 ACCOUNT_CHANNEL_API_KEY")
    headers = {"X-API-Key": api_key}
    clean_params = {k: v for k, v in (params or {}).items() if v not in (None, "")}

    print(f"\nGET {url}")
    if clean_params:
        print("Query:")
        _print_json(clean_params)

    with httpx.Client(timeout=60.0, trust_env=False) as client:
        resp = client.get(url, params=clean_params, headers=headers)

    print(f"HTTP {resp.status_code}")
    try:
        body = resp.json()
        _print_json(body)
    except ValueError:
        body = resp.text
        print(body)

    if resp.status_code >= 400:
        raise SystemExit(resp.status_code)
    return body


def test_accounts() -> dict[str, Any]:
    body = _get(
        "/open-api/accounts",
        {
            "page": ACCOUNTS_PAGE,
            "page_size": ACCOUNTS_PAGE_SIZE,
            "gender": ACCOUNTS_GENDER,
            "platform": ACCOUNTS_PLATFORM,
        },
    )
    if not isinstance(body, dict):
        raise SystemExit("accounts response is not a JSON object")
    items = body.get("items") or []
    print(f"\naccounts summary: total={body.get('total')} returned={len(items)}")
    return body


def test_videos(account_id: str, platform: str) -> dict[str, Any]:
    if not account_id:
        raise SystemExit("VIDEOS_ACCOUNT_ID 不能为空")
    if platform not in {"youtube", "tiktok", "instagram"}:
        raise SystemExit("VIDEOS_PLATFORM 必须是 youtube / tiktok / instagram")

    body = _get(
        f"/open-api/accounts/{account_id}/platforms/{platform}/videos",
        {
            "page": VIDEOS_PAGE,
            "page_size": VIDEOS_PAGE_SIZE,
        },
    )
    if not isinstance(body, dict):
        raise SystemExit("videos response is not a JSON object")
    items = body.get("items") or []
    print(f"\nvideos summary: account_id={account_id} platform={platform} total={body.get('total')} returned={len(items)}")
    return body


def test_auto() -> None:
    accounts_body = test_accounts()
    items = accounts_body.get("items") or []
    if not items:
        print("\nauto: 账号列表为空，无法继续测试视频接口")
        return

    account = items[0]
    platforms = account.get("platforms") or []
    if not platforms:
        print("\nauto: 第一条账号没有 platforms，无法继续测试视频接口")
        return

    account_id = account.get("account_id")
    platform = platforms[0].get("platform")
    print(f"\nauto: 使用第一条账号测试视频接口 account_id={account_id} platform={platform}")
    test_videos(account_id, platform)


if __name__ == "__main__":
    if ACTION == "accounts":
        test_accounts()
    elif ACTION == "videos":
        test_videos(VIDEOS_ACCOUNT_ID, VIDEOS_PLATFORM)
    elif ACTION == "auto":
        test_auto()
    else:
        raise SystemExit(f"Unknown ACTION: {ACTION}")
