"""
KOL analytics queries against the external project's BigQuery dataset.
"""

from datetime import date

from google.cloud import bigquery

from .client import get_client


def get_kol_thirdapp_open_count(
    kol_user_id: str,
    start_date: date,
    end_date: date,
) -> int:
    """
    Count v_thirdapp_open events for a given KOL within [start_date, end_date].
    Returns the event count, or 0 if no data found.
    """
    sql = """
        SELECT
            REGEXP_EXTRACT(prop_params, r'kolUserId=(\\d+)') AS kol_user_id,
            COUNT(*) AS cnt
        FROM decom.dwd_event_log
        WHERE DATE(logAt_timestamp) BETWEEN @start_date AND @end_date
          AND event_name = 'v_thirdapp_open'
          AND JSON_VALUE(args, '$.sf') != ''
          AND REGEXP_EXTRACT(prop_params, r'kolUserId=(\\d+)') = @kol_user_id
        GROUP BY kol_user_id
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date.isoformat()),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date.isoformat()),
            bigquery.ScalarQueryParameter("kol_user_id", "STRING", kol_user_id),
        ]
    )

    client = get_client()
    rows = list(client.query(sql, job_config=job_config).result())

    if not rows:
        return 0
    return rows[0]["cnt"]


def get_channel_daily_views(
    channel_id: str,
    channel: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Query daily view increments for a given channel within [start_date, end_date].

    Returns a list of dicts with keys: dt (str), daily_view_increment (int), day_end_views (int).
    Rows are ordered by dt asc. Missing dates will not appear in the result.
    """
    sql = """
        WITH social_video_daily AS (
            SELECT
                dt,
                channel,
                creator_id,
                video_key,
                day_end_views,
                day_end_views - LAG(day_end_views, 1, 0) OVER (
                    PARTITION BY video_key
                    ORDER BY dt
                ) AS daily_view_increment
            FROM decom.dws_social_video_state_daily
            WHERE creator_id = @channel_id
              AND channel = @channel
              AND dt BETWEEN @start_date AND @end_date
        )
        SELECT
            dt,
            channel,
            creator_id AS channel_id,
            COUNT(DISTINCT video_key) AS video_count,
            SUM(day_end_views) AS day_end_views,
            SUM(daily_view_increment) AS daily_view_increment
        FROM social_video_daily
        GROUP BY dt, channel_id, channel
        ORDER BY dt ASC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("channel_id", "STRING", channel_id),
            bigquery.ScalarQueryParameter("channel", "STRING", channel),
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date.isoformat()),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date.isoformat()),
        ]
    )

    client = get_client()
    rows = list(client.query(sql, job_config=job_config).result())
    return [
        {
            "dt": str(row["dt"]),
            "daily_view_increment": int(row["daily_view_increment"] or 0),
            "day_end_views": int(row["day_end_views"] or 0),
            "video_count": int(row["video_count"] or 0),
        }
        for row in rows
    ]


def get_kol_clicks_in_window(
    kol_user_id: str,
    window_start: date,
    window_end: date,
) -> int:
    """
    Count v_thirdapp_open events for a given KOL within [window_start, window_end].
    Used to collect the 24-hour post-publish click count for a single publication.
    Returns the event count, or 0 if no data found.
    """
    sql = """
        SELECT COUNT(*) AS cnt
        FROM decom.dwd_event_log
        WHERE DATE(logAt_timestamp) BETWEEN @start_date AND @end_date
          AND event_name = 'v_thirdapp_open'
          AND JSON_VALUE(args, '$.sf') != ''
          AND REGEXP_EXTRACT(prop_params, r'kolUserId=(\\d+)') = @kol_user_id
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", window_start.isoformat()),
            bigquery.ScalarQueryParameter("end_date", "DATE", window_end.isoformat()),
            bigquery.ScalarQueryParameter("kol_user_id", "STRING", kol_user_id),
        ]
    )

    client = get_client()
    rows = list(client.query(sql, job_config=job_config).result())
    if not rows:
        return 0
    return int(rows[0]["cnt"] or 0)


def get_kol_clicks_on_eastern_day(
    kol_user_id: str,
    eastern_day: date,
) -> int:
    """
    Count v_thirdapp_open events for a given KOL on a US/Eastern natural day.

    A video published at 23:59 America/New_York should be counted against that
    same Eastern calendar day, not a rolling 24-hour window or UTC day.
    """
    sql = """
        SELECT COUNT(*) AS cnt
        FROM decom.dwd_event_log
        WHERE DATE(logAt_timestamp, "America/New_York") = @eastern_day
          AND event_name = 'v_thirdapp_open'
          AND JSON_VALUE(args, '$.sf') != ''
          AND REGEXP_EXTRACT(prop_params, r'kolUserId=(\\d+)') = @kol_user_id
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("eastern_day", "DATE", eastern_day.isoformat()),
            bigquery.ScalarQueryParameter("kol_user_id", "STRING", kol_user_id),
        ]
    )

    client = get_client()
    rows = list(client.query(sql, job_config=job_config).result())
    if not rows:
        return 0
    return int(rows[0]["cnt"] or 0)


def get_kol_daily_clicks(
    kol_user_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Query daily Link click counts for a given KOL within [start_date, end_date].

    Returns a list of dicts with keys: dt (str), daily_clicks (int).
    Rows are ordered by dt asc. Missing dates will not appear in the result.
    """
    sql = """
        SELECT
            DATE(logAt_timestamp) AS dt,
            COUNT(*) AS daily_clicks
        FROM decom.dwd_event_log
        WHERE DATE(logAt_timestamp) BETWEEN @start_date AND @end_date
          AND event_name = 'v_thirdapp_open'
          AND JSON_VALUE(args, '$.sf') != ''
          AND REGEXP_EXTRACT(prop_params, r'kolUserId=(\\d+)') = @kol_user_id
        GROUP BY dt
        ORDER BY dt ASC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date.isoformat()),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date.isoformat()),
            bigquery.ScalarQueryParameter("kol_user_id", "STRING", kol_user_id),
        ]
    )

    client = get_client()
    rows = list(client.query(sql, job_config=job_config).result())
    return [
        {
            "dt": str(row["dt"]),
            "daily_clicks": int(row["daily_clicks"] or 0),
        }
        for row in rows
    ]
