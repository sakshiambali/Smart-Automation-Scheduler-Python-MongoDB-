# Daily Global Tech News Scheduler

> A Python + MongoDB application that automatically collects, categorizes,
> and delivers a daily technology news briefing.
> Built as a **learning project for BCA freshers** — every concept explained from scratch.

---

## Quick Start

```powershell
# IMPORTANT — always cd into the project folder first
cd "F:\Smart-Automation-Scheduler-Python-MongoDB-\daily-tech-news"
python main.py
```

Then open your browser at **http://localhost:5000**

---

## Table of Contents

1. [Complete Project Flow](#1-complete-project-flow)
2. [Project Flowchart](#2-project-flowchart)
3. [Every File and Its Job](#3-every-file-and-its-job)
4. [Where We Call Each Function and Why](#4-where-we-call-each-function-and-why)
5. [Why We Need a Scheduler and How It Triggers Python Functions](#5-why-we-need-a-scheduler-and-how-it-triggers-python-functions)
6. [What Happens When the App Stops at 5 AM and the Job is at 6 AM](#6-what-happens-when-the-app-stops-at-5-am-and-the-job-is-at-6-am)
7. [How MongoDB Prevents Duplicate News](#7-how-mongodb-prevents-duplicate-news)
8. [How News Travels: External API → Python → MongoDB → REST API → Postman](#8-how-news-travels-external-api--python--mongodb--rest-api--postman)
9. [Technologies Used](#9-technologies-used)
10. [Installation](#10-installation)
11. [All REST API Endpoints](#11-all-rest-api-endpoints)
12. [MongoDB Collections](#12-mongodb-collections)
13. [Common Errors and Fixes](#13-common-errors-and-fixes)
14. [Interview Questions](#14-interview-questions)

---

## 1. Complete Project Flow

The application does five things, in this order, every time it runs:

```
STEP 1  START
        python main.py
        │
        ├── Connect to MongoDB
        ├── Start APScheduler (background thread)
        └── Start Flask (main thread — serves HTTP requests)

STEP 2  COLLECT NEWS  (triggered by scheduler OR manually)
        APScheduler fires at 6:00 AM
        │
        └── collect_all_news()
              │
              ├── For each topic in config (AI, quantum, cloud...):
              │     fetch_news_from_api(topic)
              │         → HTTP GET to NewsData.io
              │         → Get JSON response
              │         → Return list of raw articles
              │
              └── For each raw article:
                    categorize_article(title, description)
                        → match keywords → assign category
                    create_news_article(...)
                        → clean + normalize all fields
                    save_news_article(article)
                        → insert into MongoDB
                        → skip if URL already exists (duplicate)

STEP 3  GENERATE BRIEFING  (runs after collection)
        run_daily_briefing()
        │
        ├── get_todays_news()
        │       → fetch last 24h articles from MongoDB
        │
        ├── select_top_news(articles)
        │       → score each article (0-10 points)
        │       → pick highest scorer per category
        │
        ├── format_briefing_text(top_news, date)
        │       → build formatted text
        │
        └── save_briefing(briefing_doc)
                → store in daily_briefings collection

STEP 4  SERVE REST APIS  (Flask runs 24/7)
        Any time someone calls:
        GET  /news              → return articles from MongoDB
        GET  /news/search       → search by keyword
        GET  /briefings/<date>  → return a day's briefing
        POST /scheduler/start   → start the interval job
        ... etc.

STEP 5  UI DASHBOARD  (browser auto-polls every 15 seconds)
        Browser opens http://localhost:5000
        │
        ├── Loads index.html (served by Flask)
        ├── JavaScript calls GET /news → renders news cards
        ├── JavaScript calls GET /scheduler/status every 15s
        │       → updates countdown timer
        │       → updates Running/Stopped badge
        │       → refreshes news if new articles arrived
        └── User can Start / Stop / Change interval via buttons
```

---

## 2. Project Flowchart

### A. Application Startup Flow

```
┌─────────────────────────────────┐
│        python main.py           │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│     create_app()  in main.py    │
└────────────────┬────────────────┘
                 │
       ┌─────────┴──────────┐
       │                    │
       ▼                    ▼
┌─────────────┐    ┌────────────────┐
│  connect_   │    │ start_         │
│  to_mongodb │    │ scheduler()    │
│  database.py│    │ scheduler.py   │
└──────┬──────┘    └───────┬────────┘
       │                   │
       ▼                   ▼
┌─────────────┐    ┌────────────────┐
│  MongoDB    │    │ BackgroundSched│
│  Connected  │    │ uler starts in │
│  Indexes    │    │ daemon thread  │
│  Created    │    └───────┬────────┘
└─────────────┘            │
                           ▼
                  ┌────────────────┐
                  │restore_settings│
                  │_from_db()      │
                  │ — reload saved │
                  │   interval     │
                  └───────┬────────┘
                          │
                          ▼
               ┌──────────────────────┐
               │  Flask app.run()     │
               │  Listening on :5000  │
               │  Serving APIs + HTML │
               └──────────────────────┘
```

### B. Daily News Collection Flow (called by Scheduler at 6 AM)

```
APScheduler fires at 6:00 AM
         │
         ▼
┌──────────────────┐
│  run_daily_job() │  ← scheduler.py
└────────┬─────────┘
         │
         ├────────────────────────────────────┐
         │                                    │
         ▼                                    ▼
┌──────────────────────┐            ┌──────────────────────┐
│  collect_all_news()  │            │  run_daily_briefing()│
│  news_service.py     │            │  briefing_service.py │
└──────────┬───────────┘            └──────────┬───────────┘
           │                                   │
           │  For each topic (9 topics)        │
           ▼                                   ▼
┌──────────────────────┐            ┌──────────────────────┐
│fetch_news_from_api() │            │  get_todays_news()   │
│  HTTP GET            │            │  MongoDB query       │
│  → NewsData.io       │            │  last 24 hours       │
└──────────┬───────────┘            └──────────┬───────────┘
           │                                   │
           │  For each article                 ▼
           ▼                        ┌──────────────────────┐
┌──────────────────────┐            │  select_top_news()   │
│categorize_article()  │            │  score each article  │
│  keyword matching    │            │  0–10 points         │
│  → assign category   │            │  pick best per cat.  │
└──────────┬───────────┘            └──────────┬───────────┘
           │                                   │
           ▼                                   ▼
┌──────────────────────┐            ┌──────────────────────┐
│create_news_article() │            │format_briefing_text()│
│  models.py           │            │  build formatted     │
│  clean all fields    │            │  text string         │
│  parse dates         │            └──────────┬───────────┘
└──────────┬───────────┘                       │
           │                                   ▼
           ▼                        ┌──────────────────────┐
┌──────────────────────┐            │  save_briefing()     │
│save_news_article()   │            │  upsert into MongoDB │
│  database.py         │            │  daily_briefings     │
│  insert_one()        │            └──────────────────────┘
│  → duplicate? skip   │
└──────────────────────┘
```

### C. REST API Request Flow (when Postman calls GET /news)

```
Postman / Browser
       │
       │  GET http://localhost:5000/news
       ▼
┌──────────────────────────────────────┐
│  Flask routes the request to         │
│  get_news() function in main.py      │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  get_news_collection()               │
│  database.py                         │
│  → returns MongoDB collection object │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  collection.find({})                 │
│  .sort("collected_at", -1)           │
│  .limit(20)                          │
│  → returns cursor (lazy list)        │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  serialize_doc(article)              │
│  main.py                             │
│  ObjectId  → string                  │
│  datetime  → ISO string              │
│  (JSON cannot handle these natively) │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  jsonify(response)                   │
│  Python dict → JSON string           │
└──────────────────┬───────────────────┘
                   │
                   ▼
       Postman receives:
       HTTP 200 OK
       {"success": true, "data": {"articles": [...]}}
```

### D. UI Dashboard Auto-Refresh Flow

```
Browser loads http://localhost:5000
        │
        ▼
app.js runs in browser
        │
        ├── Every 15 seconds:
        │   GET /scheduler/status
        │       └── updateStatusPanel()
        │           └── tickCountdown() every 1 second
        │
        ├── When countdown hits 00:00:00:
        │   └── Wait 35 seconds (job finishes)
        │       └── GET /news → renderCards()
        │
        └── When user clicks "Start":
            POST /scheduler/start {"interval": "5min"}
                └── start_custom_job() in scheduler.py
                    └── APScheduler adds IntervalTrigger
                        └── Fires every 5 minutes
                            └── run_custom_job()
                                └── collect_all_news()
```

---

## 3. Every File and Its Job

| File | Responsibility | Imported By |
|---|---|---|
| `config.py` | Reads `.env`, provides all settings as a dict | Every other file |
| `database.py` | MongoDB connection, collections, indexes, save helpers | news_service, briefing_service, scheduler, main |
| `models.py` | Data structure templates — cleans raw API data | news_service, briefing_service |
| `news_service.py` | Fetch from API, categorize, save, search | scheduler, main |
| `briefing_service.py` | Score articles, generate briefing, save | scheduler, main |
| `scheduler.py` | APScheduler — two jobs, start/stop/configure | main |
| `main.py` | Flask REST API, startup sequence, HTML dashboard | Entry point |
| `templates/index.html` | Dashboard HTML structure | Served by Flask |
| `static/style.css` | Dashboard visual styles | Loaded by HTML |
| `static/app.js` | Dashboard JavaScript — polling, rendering, controls | Loaded by HTML |

---

## 4. Where We Call Each Function and Why

### `collect_all_news()` — news_service.py

| Called From | When | Why |
|---|---|---|
| `scheduler.py → run_daily_job()` | Every day 6:00 AM (CronTrigger) | Automated daily collection |
| `scheduler.py → run_custom_job()` | Every N minutes (IntervalTrigger from UI) | User-configured interval refresh |
| `main.py → trigger_collection()` | POST /collect from Postman | Manual test trigger |
| `main.py → fetch_news_now()` | POST /news/fetch-now from dashboard | Immediate fetch button |

```python
# In scheduler.py — run_daily_job()
from news_service import collect_all_news
news_summary = collect_all_news()
# We import INSIDE the function to avoid circular imports.
# scheduler.py imports from news_service.py, and if news_service.py
# imported scheduler.py at the top, Python would get confused.
```

---

### `fetch_news_from_api(topic)` — news_service.py

| Called From | When | Why |
|---|---|---|
| `news_service.py → collect_all_news()` | Inside the topics loop | One API call per topic |

```python
# In news_service.py — collect_all_news()
for topic in config["NEWS_TOPICS"]:          # loop 9 topics
    raw_articles = fetch_news_from_api(topic) # HTTP GET per topic
    if not raw_articles:
        continue                               # skip if API fails
    counts = process_and_save_articles(raw_articles)
    time.sleep(1)                              # rate limit protection
```

We call it inside a loop because NewsData.io searches one topic at a time.
We pass each topic as a parameter so the function is reusable.

---

### `categorize_article(title, description)` — news_service.py

| Called From | When | Why |
|---|---|---|
| `news_service.py → process_and_save_articles()` | For every raw article | Assign a category before saving |

```python
# In news_service.py — process_and_save_articles()
category = categorize_article(title or "", description or "")
# We call this BEFORE create_news_article() because
# the category field must be set in the document we store.
# Without this call, every article would be "Other Technology".
```

---

### `create_news_article(...)` — models.py

| Called From | When | Why |
|---|---|---|
| `news_service.py → process_and_save_articles()` | After categorization | Clean raw data before saving |

```python
# In news_service.py
article = create_news_article(
    title=title,
    url=url,
    description=description,
    source=source,
    author=author,
    published_at=published_at,
    category=category
)
# We call this BEFORE save_news_article() because
# MongoDB should receive clean, consistent data.
# Raw API data has None values, wrong types, extra whitespace.
```

---

### `save_news_article(article)` — database.py

| Called From | When | Why |
|---|---|---|
| `news_service.py → process_and_save_articles()` | After cleaning | Persist to MongoDB |

```python
# In database.py — save_news_article()
result = collection.insert_one(article)
# If URL already exists → DuplicateKeyError → return {"saved": False}
# We handle the error here so the caller never crashes.
```

---

### `score_article(article)` — briefing_service.py

| Called From | When | Why |
|---|---|---|
| `briefing_service.py → select_top_news()` | For every article in every category | Rank articles by importance |

```python
# In briefing_service.py — select_top_news()
scored = sorted(
    category_articles,
    key=score_article,   # ← called once per article
    reverse=True
)
best_article = scored[0]  # highest score wins
# We pass score_article as a KEY FUNCTION to sorted().
# Python calls it automatically for every item being sorted.
# We don't call it manually in a loop.
```

---

### `run_daily_briefing()` — briefing_service.py

| Called From | When | Why |
|---|---|---|
| `scheduler.py → run_daily_job()` | After collection at 6:00 AM | Generate + store the briefing |
| `briefing_service.py` (manual run) | `python briefing_service.py` | Test without waiting for 6 AM |

---

### `serialize_doc(doc)` — main.py

| Called From | When | Why |
|---|---|---|
| Every GET endpoint in `main.py` | Before `jsonify()` | Convert MongoDB types to JSON-safe types |

```python
# In main.py — get_news()
serialized = [serialize_doc(a) for a in articles]
return success_response({"articles": serialized, ...})

# WHY: MongoDB returns ObjectId and datetime objects.
# JSON standard does not support these types.
# Without serialize_doc(), jsonify() would crash with:
#   "Object of type ObjectId is not JSON serializable"
```

---

### `start_scheduler()` — scheduler.py

| Called From | When | Why |
|---|---|---|
| `main.py → create_app()` | Once, at application startup | Create and launch the APScheduler engine |

```python
# In main.py — create_app()
db = connect_to_mongodb()   # Step 1: DB must be ready first
scheduler = start_scheduler()  # Step 2: Scheduler needs DB ready
restore_settings_from_db()     # Step 3: Reload saved interval settings
app.run(...)                    # Step 4: Flask starts last
```

Order matters here. If we started Flask before MongoDB connected,
the first API request would fail because the DB isn't ready yet.

---

## 5. Why We Need a Scheduler and How It Triggers Python Functions

### The Problem Without a Scheduler

Without a scheduler, to get news every morning at 6 AM you would:
1. Wake up at 5:59 AM
2. Open your terminal
3. Type `python news_service.py`
4. Do this every single day, including weekends

That is not automation. That is just a reminder to do manual work.

### What APScheduler Does

APScheduler is a Python library that acts like an alarm clock inside your code.
You tell it: **"Call this function at this time."**
Then it waits — silently — and calls your function when the time arrives.

```python
# The full scheduler setup — 4 lines of code
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler(timezone="UTC")

scheduler.add_job(
    func=run_daily_job,                  # ← YOUR Python function
    trigger=CronTrigger(hour=6, minute=0), # ← WHEN to call it
    id="daily_news_job"
)

scheduler.start()  # starts a background thread — non-blocking
```

### How APScheduler Physically Triggers Your Function

APScheduler creates a **background thread** — a second worker running inside
the same Python process, alongside Flask.

```
Your Python Process (one process, two threads)
│
├── THREAD 1: Flask (Main Thread)
│   Runs all the time
│   Waits for HTTP requests
│   GET /news → responds instantly
│   Never sleeps, never stops
│
└── THREAD 2: APScheduler (Background Daemon Thread)
    Sleeps most of the time
    Checks its job list every second internally
    
    At 5:59:59 → still sleeping
    At 6:00:00 → WAKE UP
                 Check trigger: CronTrigger(hour=6, minute=0)
                 Current time: 06:00 UTC ✅ matches!
                 Call run_daily_job()  ← YOUR function executes here
                 Job finished
                 Calculate next run: tomorrow 06:00 UTC
                 Go back to sleep until tomorrow
```

These two threads run **at the same time**.
Flask keeps serving API requests while the scheduler is fetching news.

### Two Types of Triggers Used in This Project

**CronTrigger** — for the daily briefing job:
```python
# Fires at exactly 6:00 AM every day
# Like a cron job: "0 6 * * *"
trigger = CronTrigger(hour=6, minute=0)
```

**IntervalTrigger** — for the UI custom scheduler:
```python
# Fires every 5 minutes, continuously
# Used when you select "Every 5 Minutes" in the dashboard
trigger = IntervalTrigger(minutes=5)

# Other intervals:
IntervalTrigger(minutes=1)   # every 1 minute
IntervalTrigger(hours=1)     # every 1 hour
IntervalTrigger(hours=24)    # every 24 hours
```

### Why `use_reloader=False` in Flask

```python
app.run(use_reloader=False)  # ← this is important
```

Flask's development server has an auto-reload feature.
When it detects a file change, it **restarts the entire Python process**.
This would create a **second APScheduler** — two schedulers running,
both calling `run_daily_job()` at the same time, causing duplicate jobs.

Setting `use_reloader=False` disables the reloader and prevents this.

---

## 6. What Happens When the App Stops at 5 AM and the Job is at 6 AM

### Scenario A — App crashes at 5:00 AM, never restarted

```
Timeline
────────────────────────────────────────────────────────────
4:00 AM   App is running, APScheduler sleeping
5:00 AM   App crashes (power failure, Ctrl+C, exception)
          │
          ├── Python process dies
          ├── Both Flask thread and APScheduler thread die
          └── MongoDB keeps running (it is a separate process)

6:00 AM   ❌ Nothing happens
          APScheduler is dead — no one calls run_daily_job()
          No news collected, no briefing generated

Next day  App is still stopped, same result every day
────────────────────────────────────────────────────────────
```

**Key insight:** APScheduler lives INSIDE Python.
If Python is not running, APScheduler does not exist.

MongoDB keeps your existing data safe — it is a separate OS process
that keeps running even after Python stops.

---

### Scenario B — App stops at 5:00 AM, restarts at 7:00 AM

```
Timeline
────────────────────────────────────────────────────────────
5:00 AM   App stops
6:00 AM   Job was supposed to fire — app was dead → ❌ MISSED

7:00 AM   App restarts
          │
          └── APScheduler starts fresh
              Calculates NEXT run time:
              CronTrigger(hour=6, minute=0) → tomorrow 6:00 AM

              Does APScheduler retry the missed 6:00 AM job?
              
              Depends on misfire_grace_time setting:
              
              misfire_grace_time = 30 seconds  (our setting)
              
              If missed by ≤ 30 seconds → retry immediately
              If missed by > 30 seconds → skip, wait for next trigger
              
              We missed by 1 hour (3600 seconds) > 30 seconds
              → Missed job is SKIPPED
              → Next run: tomorrow 6:00 AM

7:00 AM   ❌ No news collected for today
────────────────────────────────────────────────────────────
```

**What to do if you miss the daily job:**
```bash
# Run collection manually
python news_service.py

# Or call the API
POST http://localhost:5000/collect
```

---

### Scenario C — UI custom job was running (5min interval), app restarts

```
Timeline
────────────────────────────────────────────────────────────
5:00 AM   App stops
          Custom job state is LOST from memory
          BUT: MongoDB has saved the settings:
               {interval: "5min", running: true}

7:00 AM   App restarts
          │
          └── restore_settings_from_db() runs
              Reads: {interval: "5min", running: true}
              was_running = True
              → Automatically calls start_custom_job("5min")
              → Custom job is RESTORED
              → Starts fetching news every 5 minutes again

✅ Custom job resumes automatically — no manual action needed
────────────────────────────────────────────────────────────
```

This is why we have `_save_settings_to_db()` — called every time
you start, stop, or change the interval in the UI.

---

### Summary Table

| Situation | Daily Job (6 AM) | Custom UI Job |
|---|---|---|
| App running normally | ✅ Fires at 6:00 AM | ✅ Fires at interval |
| App stopped before trigger | ❌ Does not fire | ❌ Does not fire |
| App restarted after missed time | ⏭ Skipped, waits for tomorrow | ✅ Auto-restored from MongoDB |
| misfire within 30 seconds | ✅ Retried immediately | ✅ Retried |
| misfire after 30 seconds | ⏭ Skipped | ✅ Auto-restored |

---

## 7. How MongoDB Prevents Duplicate News

### The Problem

News APIs return overlapping results.

If you fetch "artificial intelligence" at 6:00 AM and again at 6:05 AM,
many of the same articles appear in both responses.

Without protection, your database fills with thousands of copies:

```
Article: "OpenAI releases GPT-5"  (inserted at 6:00 AM)
Article: "OpenAI releases GPT-5"  (inserted at 6:05 AM — DUPLICATE)
Article: "OpenAI releases GPT-5"  (inserted at 6:10 AM — DUPLICATE)
```

### Solution — Unique Index on URL Field

Every news article has a URL. URLs are globally unique identifiers.
No two different articles share the same URL.

We create a **Unique Index** on the `url` field when the app starts:

```python
# In database.py — create_indexes()
news_collection.create_index(
    [("url", ASCENDING)],
    unique=True,          # ← THIS is what prevents duplicates
    name="url_unique"
)
```

### What a Unique Index Does — Step by Step

Think of a unique index as a **bouncer at a club checking ID**.

```
New article arrives at save_news_article()
              │
              ▼
    MongoDB checks its URL index:
    "Have I seen this URL before?"
              │
    ┌─────────┴──────────┐
    │                    │
    ▼                    ▼
URL is NEW           URL EXISTS
    │                    │
    ▼                    ▼
INSERT document      RAISE DuplicateKeyError
Return success       (rejected before writing)
{"saved": True}      {"saved": False,
                      "reason": "duplicate"}
```

### The Exact Code That Handles This

```python
# database.py — save_news_article()

def save_news_article(article):
    try:
        col = get_news_collection()
        result = col.insert_one(article)          # attempt to insert
        return {"saved": True, "reason": "inserted"}

    except DuplicateKeyError:
        # MongoDB AUTOMATICALLY raises this when the URL already exists
        # This is EXPECTED behaviour — not a crash
        # We catch it quietly and tell the caller to skip this article
        return {"saved": False, "reason": "duplicate"}
```

```python
# news_service.py — process_and_save_articles()

result = save_news_article(article)

if result["saved"]:
    counts["saved"] += 1           # ✅ new article stored
elif result["reason"] == "duplicate":
    counts["duplicates"] += 1      # ⏭ silently skipped
```

### Why Not Check Before Inserting?

You might think this approach is simpler:

```python
# WRONG WAY — do not do this
if collection.find_one({"url": article["url"]}):
    skip()
else:
    insert()
```

**Problem:** This is two separate operations.
If two processes run this simultaneously:
- Process A checks: "URL not found" → about to insert
- Process B checks: "URL not found" → about to insert
- Process A inserts → success
- Process B inserts → DUPLICATE (check was already stale)

The **unique index** check happens inside MongoDB as a **single atomic operation**.
It is physically impossible for two duplicates to get through,
even if the code runs 1000 times per second.

### Proof From Real Output

```
[TOPIC] 'agentic AI':        saved=3, duplicates=7, skipped=0
[TOPIC] 'quantum computing': saved=1, duplicates=9, skipped=0
[TOPIC] 'programming language': saved=0, duplicates=10, skipped=0
```

7 out of 10 "agentic AI" articles were already in the database.
All 10 "programming language" articles were duplicates.
MongoDB rejected every one automatically. Zero duplicates in the database.

---

## 8. How News Travels: External API → Python → MongoDB → REST API → Postman

### The Complete Journey of One Article

```
STAGE 1: THE REQUEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Python sends an HTTP GET request to NewsData.io:

  GET https://newsdata.io/api/1/news
      ?q=artificial+intelligence
      &language=en
      &apikey=pub_abc123...

  This is identical to what your browser does when you visit a website.
  The difference: Python does it in code using the requests library.

  Code in news_service.py:
  ┌──────────────────────────────────────────────────────────┐
  │  response = requests.get(url, params=params, timeout=15) │
  └──────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 2: THE RESPONSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  NewsData.io sends back a JSON string:

  {
    "status": "success",
    "totalResults": 4521,
    "results": [
      {
        "title":       "OpenAI releases GPT-5 with advanced reasoning",
        "description": "OpenAI has announced its most powerful model...",
        "link":        "https://techcrunch.com/2026/10/18/openai-gpt5",
        "pubDate":     "2026-10-18 06:00:00",
        "source_name": "TechCrunch",
        "creator":     ["Jane Smith"],
        "category":    ["technology"]
      },
      { ... next article ... }
    ]
  }

  Python reads this with:
  ┌──────────────────────────┐
  │  data = response.json()  │  ← JSON string → Python dictionary
  └──────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 3: EXTRACTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Python extracts individual fields from each raw article:

  ┌──────────────────────────────────────────────────────────┐
  │  title       = raw.get("title")                         │
  │  url         = raw.get("link")      # ← NOTE: "link"    │
  │  description = raw.get("description")                   │
  │  published_at = raw.get("pubDate")  # ← "2026-10-18..." │
  │  source      = raw.get("source_name")                   │
  │  creator_list = raw.get("creator")  # ← list ["Jane"]   │
  │  author      = creator_list[0] if creator_list else None│
  └──────────────────────────────────────────────────────────┘

  Code in news_service.py — process_and_save_articles()

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 4: CATEGORIZATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Python calls categorize_article(title, description):

  combined_text = "openai releases gpt-5 with advanced reasoning
                   openai has announced its most powerful model..."
                   (lowercased)

  Loop through CATEGORY_KEYWORDS in config.py:

  "Agentic AI" keywords: ["agentic ai", "ai agent", ...] → no match
  "AI" keywords: ["openai", "llm", "gpt", ...] → "openai" FOUND ✅

  Returns: "AI"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 5: CLEANING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Python calls create_news_article() in models.py:
  This cleans every field and returns a consistent document.

  Input (raw, messy):                 Output (clean, consistent):
  ┌──────────────────────────────┐    ┌──────────────────────────────┐
  │ title: "OpenAI releases..."  │    │ title: "OpenAI releases..."  │
  │ link: "https://..."          │ →  │ url: "https://..."           │
  │ pubDate: "2026-10-18 06:..."  │    │ published_at: datetime(UTC)  │
  │ source_name: "TechCrunch"    │    │ source: "TechCrunch"         │
  │ creator: ["Jane Smith"]      │    │ author: "Jane Smith"         │
  │ description: None            │    │ description: ""              │
  │                              │    │ category: "AI"               │
  │                              │    │ collected_at: datetime(now)  │
  └──────────────────────────────┘    └──────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 6: STORAGE IN MONGODB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Python calls save_news_article(article) in database.py:

  collection.insert_one(article)

  MongoDB stores the document on disk:

  {
    "_id":          ObjectId("6713a8c2f1b2c3d4e5f60001"),  ← auto-created
    "title":        "OpenAI releases GPT-5 with advanced reasoning",
    "description":  "",
    "source":       "TechCrunch",
    "author":       "Jane Smith",
    "url":          "https://techcrunch.com/2026/10/18/openai-gpt5",
    "category":     "AI",
    "published_at": ISODate("2026-10-18T06:00:00Z"),
    "collected_at": ISODate("2026-10-18T06:05:12Z")
  }

  Unique index checked:
  URL not seen before → INSERT succeeds
  URL already exists  → DuplicateKeyError → skip

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 7: REST API REQUEST (Postman calls GET /news)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Postman sends: GET http://localhost:5000/news

  Flask receives request → routes to get_news() in main.py

  collection.find({}).sort("collected_at", -1).limit(20)
  → MongoDB reads from disk
  → Returns list of documents with ObjectId and datetime types

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 8: SERIALIZATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  MongoDB types → JSON-safe Python types:

  ObjectId("6713a8c2...")      → "6713a8c2..."          (string)
  ISODate("2026-10-18T06:...") → "2026-10-18T06:00:00"  (string)

  Code: serialize_doc(article) in main.py

  WHY: The JSON standard does not support ObjectId or datetime.
  jsonify() would crash without this step.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STAGE 9: RESPONSE TO POSTMAN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Flask sends HTTP response:

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "success": true,
    "message": "Retrieved 20 articles",
    "data": {
      "articles": [
        {
          "_id":          "6713a8c2f1b2c3d4e5f60001",
          "title":        "OpenAI releases GPT-5 with advanced reasoning",
          "description":  "",
          "source":       "TechCrunch",
          "author":       "Jane Smith",
          "url":          "https://techcrunch.com/2026/10/18/openai-gpt5",
          "category":     "AI",
          "published_at": "2026-10-18T06:00:00",
          "collected_at": "2026-10-18T06:05:12"
        }
      ],
      "count": 20,
      "limit": 20
    },
    "timestamp": "2026-10-18T09:31:16"
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Data Format at Each Stage

| Stage | Format | Example Value |
|---|---|---|
| NewsData.io HTTP response | JSON text over HTTP | `{"results": [...]}` |
| After `response.json()` | Python dictionary | `{"title": "...", "link": "..."}` |
| After field extraction | Python variables | `title = "OpenAI..."` |
| After categorization | Python string | `"AI"` |
| After `create_news_article()` | Clean Python dict | `{"title": "...", "url": "...", "category": "AI"}` |
| Inside MongoDB | BSON document | `{_id: ObjectId, published_at: ISODate}` |
| After `serialize_doc()` | JSON-safe Python dict | `{_id: "6713...", published_at: "2026-..."}` |
| In Postman | JSON text | `{"_id": "6713...", "title": "..."}` |

---

## 9. Technologies Used

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Core programming language |
| MongoDB | 8.0 | Database for news and briefings |
| PyMongo | 4.8.0 | Python ↔ MongoDB driver |
| Flask | 3.0.3 | REST API framework + HTML serving |
| APScheduler | 3.10.4 | Automated scheduling (CronTrigger + IntervalTrigger) |
| Requests | 2.32.3 | HTTP calls to news APIs |
| python-dotenv | 1.0.1 | Load `.env` into environment variables |
| NewsData.io | — | Free news API (200 requests/day) |
| HTML + CSS + JS | — | Dashboard UI (no frameworks) |

---

## 10. Installation

### Prerequisites

| Tool | Download |
|---|---|
| Python 3.10+ | https://python.org |
| MongoDB Community 8.0 | https://mongodb.com/try/download/community |
| MongoDB Compass | Included with MongoDB installer |
| VS Code | https://code.visualstudio.com |
| Postman | https://postman.com |

### Step 1 — Navigate to the project folder

```powershell
cd "F:\Smart-Automation-Scheduler-Python-MongoDB-\daily-tech-news"
```

### Step 2 — Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 3 — Start MongoDB

```powershell
Start-Service -Name "MongoDB"
Get-Service -Name "MongoDB"   # should show: Running
```

### Step 4 — Get a free API key

1. Go to **https://newsdata.io**
2. Click **Get API Key** → register → key appears instantly
3. Format: `pub_XXXXXXXXXXXXXXXXXXXXXXXX`

### Step 5 — Configure `.env`

```env
NEWS_API_KEY=pub_your_key_here
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=tech_news
FLASK_PORT=5000
NEWS_SCHEDULE_HOUR=6
NEWS_SCHEDULE_MINUTE=0
```

### Step 6 — Run

```powershell
python main.py
```

Open browser: **http://localhost:5000**

---

## 11. All REST API Endpoints

Base URL: `http://localhost:5000`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Dashboard HTML page |
| GET | `/health` | App, DB, and scheduler status |
| GET | `/news` | Latest articles (`?limit=20&category=AI`) |
| GET | `/news/search?keyword=AI` | Search by keyword |
| GET | `/news/category/AI` | Filter by category |
| GET | `/news/<id>` | One article by MongoDB ObjectId |
| GET | `/briefings` | All stored daily briefings |
| GET | `/briefings/2026-10-18` | One day's full briefing |
| POST | `/collect` | Manually trigger collection |
| GET | `/scheduler/status` | Custom job status + next run time |
| POST | `/scheduler/start` | Start interval job `{"interval":"5min"}` |
| POST | `/scheduler/stop` | Stop interval job |
| POST | `/scheduler/configure` | Change interval `{"interval":"1hour"}` |
| POST | `/news/fetch-now` | Immediate background fetch |

### Valid Interval Keys

| Key | Meaning |
|---|---|
| `1min` | Every 1 minute |
| `5min` | Every 5 minutes |
| `1hour` | Every 1 hour |
| `1day` | Every 24 hours |

---

## 12. MongoDB Collections

### `tech_news.news` — stores all articles

```json
{
  "_id":          "auto-generated ObjectId",
  "title":        "OpenAI releases GPT-5",
  "description":  "OpenAI has announced...",
  "source":       "TechCrunch",
  "author":       "Jane Smith",
  "url":          "https://techcrunch.com/...",
  "category":     "AI",
  "published_at": "2026-10-18T06:00:00Z",
  "collected_at": "2026-10-18T06:05:12Z"
}
```

Indexes: `url` (unique), `published_at`, `category`

### `tech_news.daily_briefings` — one document per day

```json
{
  "briefing_date":     "2026-10-18",
  "total_news":        114,
  "categories":        {"AI": 14, "Cybersecurity": 4},
  "top_news":          [...],
  "learning_of_the_day": "...",
  "career_opportunity":  "...",
  "briefing_text":      "=== DAILY GLOBAL TECH BRIEFING ===..."
}
```

Index: `briefing_date` (unique)

### `tech_news.scheduler_settings` — UI scheduler preferences

```json
{
  "settings_key": "main",
  "interval":     "5min",
  "running":      true,
  "last_run":     "2026-10-18T09:31:16",
  "saved_at":     "2026-10-18T09:30:00"
}
```

---

## 13. Common Errors and Fixes

| Error | Cause | Fix |
|---|---|---|
| `can't open file 'main.py'` | Wrong directory | `cd daily-tech-news` first |
| `Cannot connect to MongoDB` | MongoDB not running | `Start-Service MongoDB` |
| `NEWS_API_KEY is not set` | Missing key in `.env` | Add real key from newsdata.io |
| `403 Forbidden` from API | Key not activated | Verify email on newsdata.io |
| `ModuleNotFoundError` | Packages missing | `pip install -r requirements.txt` |
| `Address already in use` | Port 5000 taken | Change `FLASK_PORT=5001` in `.env` |
| `0 articles collected` | Rate limit hit | Wait 24 hours for reset |
| `DuplicateKeyError` | Expected behavior | Already handled — not a crash |

---

## 14. Interview Questions

**Python:**
1. What is the difference between a thread and a process?
2. What does `daemon=True` mean for a background thread?
3. Why do we use `if __name__ == "__main__"`?
4. What is the difference between `os.getenv()` and hardcoding?
5. Why do we import `collect_all_news` inside `run_daily_job()` instead of at the top?

**APScheduler:**
1. What is the difference between `CronTrigger` and `IntervalTrigger`?
2. What is `misfire_grace_time` and when does it matter?
3. What happens if we do not set `use_reloader=False` in Flask?
4. Can APScheduler fire a job if Python is not running?
5. How do we prevent two copies of the same job from running at once?

**MongoDB:**
1. What is a unique index and how does it prevent duplicates?
2. What is the difference between `insert_one()` and `update_one(upsert=True)`?
3. What does `DuplicateKeyError` mean and should we treat it as a crash?
4. Why do we convert `ObjectId` to string before returning JSON?
5. What is a BSON document?

**REST API / Flask:**
1. What is the difference between GET and POST HTTP methods?
2. What does HTTP status 404 mean? 409? 503?
3. Why must `/news/search` be registered before `/news/<id>` in Flask?
4. Why do we never expose API keys or stack traces in error responses?
5. What does `jsonify()` do in Flask?

---

*Daily Global Tech News Scheduler — BCA Learning Project*
*Every concept explained. Every line understood.*
