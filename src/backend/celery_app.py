import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery("feedwire", broker=REDIS_URL, backend=REDIS_URL)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Los_Angeles",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Queue split: the high-volume feed fetches get their own "feeds" queue,
    # everything else (fetch_all_feeds, digest, alerts, relevance, cleanup) lands
    # on "control". Before this, all tasks shared one FIFO "celery" queue, so a
    # fetch_single_feed backlog (it snowballed to ~383k in Jul 2026) buried the
    # once-a-day digest behind it for weeks — beat kept dispatching it but the
    # worker never reached it. Isolating control tasks on their own queue + worker
    # guarantees the digest/alerts always have a free consumer regardless of the
    # fetch backlog. See docs/handover.md §4.13.
    task_default_queue="control",
    task_routes={
        "tasks.fetch_single_feed": {"queue": "feeds"},
    },
)

celery.conf.beat_schedule = {
    "fetch-all-feeds": {
        "task": "tasks.fetch_all_feeds",
        "schedule": 300.0,  # every 5 minutes, respects per-feed intervals
    },
    "cleanup-old-items": {
        "task": "tasks.cleanup_old_items",
        "schedule": crontab(hour=2, minute=0),  # daily at 2am LA time (before 3am backup)
    },
    "update-relevance-scores": {
        "task": "tasks.update_relevance_scores",
        "schedule": 900.0,  # every 15 minutes
    },
    "daily-digest": {
        "task": "tasks.send_daily_digest",
        "schedule": crontab(hour=8, minute=0),  # daily at 8am LA time, DST-aware
    },
    "score-alerts": {
        "task": "tasks.send_score_alerts",
        "schedule": 600.0,  # every 10 minutes; throttled internally per alerts_max_per_hour
    },
}

import tasks  # noqa: F401 - register tasks with celery
