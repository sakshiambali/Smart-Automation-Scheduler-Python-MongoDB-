# =============================================================
# scheduler.py — Automated news collection and briefing
#
# TWO JOBS MANAGED HERE:
#
#   1. daily_news_job  — original, CronTrigger at 6:00 AM every day
#                        fetches news AND generates daily briefing
#                        always runs regardless of UI settings
#
#   2. custom_news_job — new, controlled by the UI dashboard
#                        IntervalTrigger (1min / 5min / 1h / 1day)
#                        fetches news ONLY (no briefing)
#                        can be started / stopped / reconfigured live
#
# VALID INTERVAL KEYS (used by the UI API):
#   "1min"  → every 1 minute
#   "5min"  → every 5 minutes
#   "1hour" → every 1 hour
#   "1day"  → every 24 hours
# =============================================================

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
from config import config

# ── Module-level state ─────────────────────────────────────
_scheduler = None          # single BackgroundScheduler instance

# Runtime state for the custom (UI-controlled) job
_custom_job_running  = False   # True while custom_news_job is active
_custom_interval_key = "5min"  # currently configured interval
_last_run_time       = None    # UTC datetime of last successful run
_last_run_summary    = {}      # result dict from collect_all_news()
_job_in_progress     = False   # True while a fetch is actively executing
_last_error          = None    # last error message string (or None)

# ── Valid intervals ─────────────────────────────────────────
VALID_INTERVALS = {
    "1min":  {"label": "Every 1 Minute",  "minutes": 1},
    "5min":  {"label": "Every 5 Minutes", "minutes": 5},
    "1hour": {"label": "Every 1 Hour",    "hours":   1},
    "1day":  {"label": "Every 1 Day",     "hours":  24},
}


# =============================================================
# HELPER — build an IntervalTrigger from an interval key
# =============================================================

def _build_interval_trigger(interval_key):
    """
    Convert an interval key string into an APScheduler IntervalTrigger.

    Parameters:
      interval_key — one of "1min", "5min", "1hour", "1day"

    Returns:
      IntervalTrigger object

    Raises:
      ValueError if the key is not in VALID_INTERVALS
    """
    if interval_key not in VALID_INTERVALS:
        raise ValueError(
            f"Invalid interval '{interval_key}'. "
            f"Valid options: {list(VALID_INTERVALS.keys())}"
        )

    params = {k: v for k, v in VALID_INTERVALS[interval_key].items()
              if k != "label"}
    return IntervalTrigger(**params, timezone="UTC")


# =============================================================
# JOB 1 — THE ORIGINAL DAILY JOB (unchanged)
# Runs every morning at 6:00 AM — fetches news + generates briefing
# =============================================================

def run_daily_job():
    """
    Original daily job — runs at 6:00 AM every day.
    Collects news AND generates the daily briefing.
    This is never affected by the UI scheduler settings.
    """
    start_time = datetime.now(timezone.utc)

    print()
    print("=" * 62)
    print("  DAILY JOB STARTED (6:00 AM)")
    print(f"  Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 62)

    try:
        from news_service import collect_all_news
        news_summary = collect_all_news()
        print(f"[DAILY JOB] News collected: {news_summary['total_saved']} new articles")
    except Exception as e:
        print(f"[DAILY JOB ERROR] News collection failed: {e}")

    try:
        from briefing_service import run_daily_briefing
        briefing = run_daily_briefing()
        if briefing:
            print("[DAILY JOB] Daily briefing generated.")
    except Exception as e:
        print(f"[DAILY JOB ERROR] Briefing generation failed: {e}")

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    print(f"[DAILY JOB] Finished in {duration:.1f} seconds")
    print()


# =============================================================
# JOB 2 — THE CUSTOM UI JOB (new)
# Runs at the interval set by the user in the dashboard
# Fetches news only — no briefing generation
# =============================================================

def run_custom_job():
    """
    Custom UI-controlled job.
    Called automatically by APScheduler at the user-selected interval.

    - Checks _job_in_progress to prevent overlapping runs
    - Updates _last_run_time, _last_run_summary, _last_error
    - Safe to run at 1-minute intervals without issues
    """
    global _job_in_progress, _last_run_time, _last_run_summary, _last_error

    # Prevent overlapping executions
    # If the previous run is still happening, skip this one
    if _job_in_progress:
        print("[CUSTOM JOB] Previous run still in progress — skipping this trigger")
        return

    _job_in_progress = True
    start_time = datetime.now(timezone.utc)

    print(f"[CUSTOM JOB] Starting at {start_time.strftime('%H:%M:%S')} UTC "
          f"(interval: {_custom_interval_key})")

    try:
        from news_service import collect_all_news
        summary = collect_all_news()

        _last_run_time    = datetime.now(timezone.utc)
        _last_run_summary = summary
        _last_error       = None

        print(f"[CUSTOM JOB] Done — "
              f"saved={summary['total_saved']}, "
              f"duplicates={summary['total_duplicates']}")

    except Exception as e:
        _last_error = str(e)
        print(f"[CUSTOM JOB ERROR] {e}")

    finally:
        # Always release the lock, even if an exception occurred
        _job_in_progress = False


# =============================================================
# SCHEDULER LIFECYCLE
# =============================================================

def start_scheduler():
    """
    Create the single BackgroundScheduler and add the original daily job.
    Called once by main.py on startup.

    The custom UI job is NOT added here — it is added when the user
    clicks "Start Scheduler" in the dashboard.

    Returns the scheduler object, or None if startup fails.
    """
    global _scheduler

    try:
        _scheduler = BackgroundScheduler(timezone="UTC")

        # Original daily briefing job — always present
        _scheduler.add_job(
            func=run_daily_job,
            trigger=CronTrigger(
                hour=config["NEWS_SCHEDULE_HOUR"],
                minute=config["NEWS_SCHEDULE_MINUTE"]
            ),
            id="daily_news_job",
            name="Daily Briefing (6:00 AM)",
            replace_existing=True
        )

        _scheduler.start()

        job = _scheduler.get_job("daily_news_job")
        print(f"[SCHEDULER] Started — daily briefing at "
              f"{config['NEWS_SCHEDULE_HOUR']:02d}:{config['NEWS_SCHEDULE_MINUTE']:02d} UTC")
        print(f"[SCHEDULER] Next daily run: {job.next_run_time if job else 'Unknown'}")

        return _scheduler

    except Exception as e:
        print(f"[SCHEDULER ERROR] Failed to start: {e}")
        return None


def stop_scheduler():
    """
    Gracefully shut down the entire APScheduler (called on app exit).
    This stops BOTH the daily job and the custom job.
    """
    global _scheduler, _custom_job_running

    if _scheduler and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
            _custom_job_running = False
            print("[SCHEDULER] Shut down successfully")
        except Exception as e:
            print(f"[SCHEDULER ERROR] Shutdown error: {e}")


# =============================================================
# CUSTOM JOB CONTROLS (called by the UI API endpoints)
# =============================================================

def start_custom_job(interval_key=None):
    """
    Start (or restart) the custom UI-controlled news fetch job.

    Parameters:
      interval_key — "1min", "5min", "1hour", "1day"
                     If None, uses the current _custom_interval_key

    Returns:
      dict with status info
    """
    global _scheduler, _custom_job_running, _custom_interval_key

    if _scheduler is None or not _scheduler.running:
        return {"success": False, "message": "Scheduler engine not running. Restart the app."}

    # Use provided interval or fall back to current setting
    if interval_key:
        if interval_key not in VALID_INTERVALS:
            return {
                "success": False,
                "message": f"Invalid interval '{interval_key}'. "
                           f"Use one of: {list(VALID_INTERVALS.keys())}"
            }
        _custom_interval_key = interval_key

    try:
        trigger = _build_interval_trigger(_custom_interval_key)

        # add_job with replace_existing=True acts as add-or-replace
        # So calling start_custom_job() again just reschedules it
        _scheduler.add_job(
            func=run_custom_job,
            trigger=trigger,
            id="custom_news_job",
            name=f"Custom News Fetch ({VALID_INTERVALS[_custom_interval_key]['label']})",
            replace_existing=True,
            max_instances=1,         # never run more than one copy at once
            misfire_grace_time=30    # if a run is missed, ignore it after 30s
        )

        _custom_job_running = True

        job = _scheduler.get_job("custom_news_job")
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

        label = VALID_INTERVALS[_custom_interval_key]["label"]
        print(f"[CUSTOM JOB] Started — {label}, next run: {next_run}")

        # Persist to MongoDB
        _save_settings_to_db()

        return {
            "success":      True,
            "message":      f"Scheduler started — {label}",
            "interval":     _custom_interval_key,
            "interval_label": label,
            "next_run":     next_run,
            "running":      True,
        }

    except Exception as e:
        return {"success": False, "message": f"Failed to start custom job: {e}"}


def stop_custom_job():
    """
    Stop the custom UI-controlled job.
    The original daily briefing job continues running.

    Returns:
      dict with status info
    """
    global _scheduler, _custom_job_running

    if _scheduler is None:
        return {"success": False, "message": "Scheduler engine not initialised."}

    try:
        job = _scheduler.get_job("custom_news_job")
        if job:
            _scheduler.remove_job("custom_news_job")
            print("[CUSTOM JOB] Stopped and removed")
        else:
            print("[CUSTOM JOB] Was not running")

        _custom_job_running = False

        # Persist stopped state to MongoDB
        _save_settings_to_db()

        return {
            "success": True,
            "message": "Scheduler stopped",
            "running": False,
        }

    except Exception as e:
        return {"success": False, "message": f"Failed to stop custom job: {e}"}


def configure_custom_job(interval_key):
    """
    Change the interval of the custom job.
    If the job is currently running, reschedule it immediately.
    If it is stopped, just update the saved setting.

    Parameters:
      interval_key — "1min", "5min", "1hour", "1day"

    Returns:
      dict with status info
    """
    global _custom_interval_key, _custom_job_running

    if interval_key not in VALID_INTERVALS:
        return {
            "success": False,
            "message": f"Invalid interval. Use: {list(VALID_INTERVALS.keys())}"
        }

    _custom_interval_key = interval_key

    # If running, reschedule immediately with the new interval
    if _custom_job_running and _scheduler and _scheduler.running:
        return start_custom_job(interval_key)

    # Not running — just save the preference
    _save_settings_to_db()
    label = VALID_INTERVALS[interval_key]["label"]

    return {
        "success":        True,
        "message":        f"Interval updated to: {label}",
        "interval":       interval_key,
        "interval_label": label,
        "running":        False,
    }


# =============================================================
# STATUS (called by GET /scheduler/status)
# =============================================================

def get_custom_job_status():
    """
    Return the full status of the custom UI job.
    This is what the dashboard polls to update its display.

    Returns a dict with all information the frontend needs.
    """
    global _scheduler, _custom_job_running, _custom_interval_key
    global _last_run_time, _last_run_summary, _last_error, _job_in_progress

    job = None
    next_run = None

    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("custom_news_job")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    label = VALID_INTERVALS.get(_custom_interval_key, {}).get("label", _custom_interval_key)

    return {
        "running":          _custom_job_running,
        "interval":         _custom_interval_key,
        "interval_label":   label,
        "next_run":         next_run,
        "last_run":         _last_run_time.isoformat() if _last_run_time else None,
        "job_in_progress":  _job_in_progress,
        "last_error":       _last_error,
        "last_summary": {
            "total_saved":      _last_run_summary.get("total_saved", 0),
            "total_duplicates": _last_run_summary.get("total_duplicates", 0),
            "total_errors":     _last_run_summary.get("total_errors", 0),
        },
        "valid_intervals":  {k: v["label"] for k, v in VALID_INTERVALS.items()},
    }


def get_scheduler_status():
    """
    Kept for backward compatibility with /health endpoint.
    Returns basic status of the original daily job.
    """
    global _scheduler

    if _scheduler is None or not _scheduler.running:
        return {"running": False, "message": "Scheduler not running"}

    job = _scheduler.get_job("daily_news_job")
    next_run = str(job.next_run_time) if job and job.next_run_time else "Unknown"

    return {
        "running":  True,
        "schedule": f"Daily at {config['NEWS_SCHEDULE_HOUR']:02d}:{config['NEWS_SCHEDULE_MINUTE']:02d} UTC",
        "next_run": next_run,
        "job_name": job.name if job else "Unknown"
    }


# =============================================================
# PERSISTENCE — save/load settings from MongoDB
# =============================================================

def _save_settings_to_db():
    """
    Persist the current custom job settings to MongoDB.
    Called every time the job is started, stopped, or reconfigured.
    Uses upsert so it always writes to the same single document.
    """
    try:
        from database import get_db
        db = get_db()
        if db is None:
            return

        col = db["scheduler_settings"]

        # Create index on first use
        col.create_index("settings_key", unique=True, name="settings_key_unique")

        col.update_one(
            {"settings_key": "main"},
            {"$set": {
                "settings_key":   "main",
                "interval":       _custom_interval_key,
                "running":        _custom_job_running,
                "last_run":       _last_run_time.isoformat() if _last_run_time else None,
                "saved_at":       datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True
        )
    except Exception as e:
        # Non-fatal — just log it
        print(f"[SCHEDULER] Could not save settings to DB: {e}")


def restore_settings_from_db():
    """
    Load saved scheduler settings from MongoDB and restore the custom job.
    Called once by main.py during startup (after start_scheduler()).

    If the saved state shows running=True, the custom job is restarted
    automatically with the saved interval.
    """
    global _custom_interval_key

    try:
        from database import get_db
        db = get_db()
        if db is None:
            return

        col = db["scheduler_settings"]
        settings = col.find_one({"settings_key": "main"})

        if settings:
            saved_interval = settings.get("interval", "5min")
            was_running    = settings.get("running", False)

            # Validate the saved interval is still valid
            if saved_interval in VALID_INTERVALS:
                _custom_interval_key = saved_interval

            print(f"[SCHEDULER] Restored settings — interval={_custom_interval_key}, "
                  f"was_running={was_running}")

            # If it was running before app restart, restart it automatically
            if was_running:
                result = start_custom_job(_custom_interval_key)
                print(f"[SCHEDULER] Auto-restarted custom job: {result.get('message')}")
        else:
            print("[SCHEDULER] No saved settings found — using defaults")

    except Exception as e:
        print(f"[SCHEDULER] Could not restore settings: {e}")
