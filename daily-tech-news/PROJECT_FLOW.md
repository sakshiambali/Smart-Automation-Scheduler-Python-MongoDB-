# Daily Global Tech News Scheduler — Complete Project Flow

> Written for BCA freshers.
> Every concept explained from scratch. No assumptions.

---

## PART 1 — How to Run the Project Correctly

### The Problem You Faced

```
python main.py
→ can't open file 'F:\Smart-Automation-Scheduler-Python-MongoDB-\main.py'
```

**Why this happened:**
Your terminal was sitting in the root folder `Smart-Automation-Scheduler-Python-MongoDB-\`.
But `main.py` lives one level deeper inside `daily-tech-news\`.
Python looked for the file in the wrong place.

### The Fix — Always `cd` into the project folder first

```powershell
cd "F:\Smart-Automation-Scheduler-Python-MongoDB-\daily-tech-news"
python main.py
```

Then open your browser at:
```
http://localhost:5000
```

### Rule to Remember

```
Your Terminal Location    →   What Python Sees
─────────────────────────────────────────────────────────────
F:\Smart-Automation-...\          →   No main.py here ❌
F:\Smart-Automation-...\daily-tech-news\  →   main.py found ✅
```

---

## PART 2 — Complete Project Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  YOUR COMPUTER (localhost)                   │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  NewsData.io │    │   MongoDB    │    │   Browser /  │  │
│  │  (Internet)  │    │  (Database)  │    │   Postman    │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘  │
│         │                   │                   │          │
│         ▼                   ▼                   ▼          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │               Python Application (main.py)           │  │
│  │                                                      │  │
│  │   ┌─────────────┐   ┌─────────────┐   ┌──────────┐  │  │
│  │   │  Scheduler  │   │  news_      │   │  Flask   │  │  │
│  │   │  (APSched.) │──▶│  service   │──▶│  REST    │  │  │
│  │   └─────────────┘   └─────────────┘   │  API     │  │  │
│  │                                        └──────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Three things run at the same time inside one Python process:**

| Component | What It Does | Runs In |
|---|---|---|
| Flask | Serves REST APIs + HTML dashboard | Main thread |
| APScheduler | Fires jobs at set times | Background daemon thread |
| MongoDB | Stores and retrieves all data | Separate process on your machine |

---

## PART 3 — What Is a Scheduler and Why Do We Need It?

### The Problem Without a Scheduler

Imagine you want news every morning at 6:00 AM.

Without a scheduler, you would have to:
1. Wake up at 6:00 AM yourself
2. Open your terminal
3. Run `python news_service.py` manually
4. Do this every single day

That is not automation. That is manual work.

### What a Scheduler Does

A scheduler is a timer that runs inside Python.
You tell it: **"Run this function every day at 6:00 AM."**
Then you forget about it. The scheduler handles the rest.

```python
# This is the core idea — in plain English:

"Every day at 6:00 AM → call the function run_daily_job()"
```

### How APScheduler Works Inside Python

APScheduler creates a **background thread** inside your Python program.

```
Your Python Program (main.py)
│
├── Main Thread ─────────────────────────────► Flask runs here
│   Handles HTTP requests from browser/Postman
│   Never stops, always listening
│
└── Background Thread ───────────────────────► APScheduler runs here
    Sleeping most of the time
    Wakes up at the scheduled time
    Calls your function
    Goes back to sleep
```

These two threads run **at the same time** (concurrently).
Flask does not know the scheduler exists. The scheduler does not know Flask exists.
They share the same MongoDB connection but nothing else.

### How APScheduler Exactly Triggers Your Python Function

Here is the exact code in `scheduler.py`:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Step 1: Create the scheduler object
_scheduler = BackgroundScheduler(timezone="UTC")

# Step 2: Tell it WHAT to run and WHEN to run it
_scheduler.add_job(
    func=run_daily_job,          # ← the Python function to call
    trigger=CronTrigger(         # ← the schedule definition
        hour=6,
        minute=0
    ),
    id="daily_news_job"          # ← unique name for this job
)

# Step 3: Start the background thread
_scheduler.start()
```

**What happens at 5:59:59 AM:**
```
APScheduler background thread is sleeping...
Internal clock ticks...
5:59:59 → still sleeping
6:00:00 → WAKE UP
         → Look at job list
         → Find "daily_news_job"
         → Check trigger: CronTrigger(hour=6, minute=0)
         → Current time matches ✅
         → Call run_daily_job()  ← your Python function runs
         → Job finished
         → Update next_run_time to tomorrow 6:00:00
         → Go back to sleep
```

### The Two Trigger Types in This Project

| Trigger | Code | When it fires |
|---|---|---|
| `CronTrigger` | `CronTrigger(hour=6, minute=0)` | Every day at exactly 6:00 AM |
| `IntervalTrigger` | `IntervalTrigger(minutes=5)` | Every 5 minutes continuously |

The **daily briefing** uses `CronTrigger` — runs once per day at 6 AM.
The **UI custom scheduler** uses `IntervalTrigger` — runs every N minutes/hours.

---

## PART 4 — What Happens If the App Is Stopped?

### Scenario: App stops at 5:00 AM, Scheduler was set for 6:00 AM

```
Timeline:
─────────────────────────────────────────────────────────────
5:00 AM  ── App crashes or user presses Ctrl+C
           └── Python process dies
           └── APScheduler background thread dies with it
           └── Flask stops serving
           └── MongoDB keeps running (it's a separate process)

6:00 AM  ── Nothing happens
           └── APScheduler is dead — no one fires the job
           └── No news is collected
           └── No briefing is generated
─────────────────────────────────────────────────────────────
```

**The job simply does not run.** APScheduler lives inside Python. If Python is not running, APScheduler is not running.

### Scenario: App stops at 5:00 AM, Restarts at 7:00 AM

```
Timeline:
─────────────────────────────────────────────────────────────
5:00 AM  ── App stops
6:00 AM  ── Job was supposed to fire — didn't (app was dead)
7:00 AM  ── App restarts
           └── APScheduler starts fresh
           └── Calculates next_run_time = tomorrow 6:00 AM
           └── Does NOT run the missed 6:00 AM job

           WHY? Because we configured:
           misfire_grace_time = 30 seconds

           A missed job is only retried if it was missed by
           less than 30 seconds. Missing by 1 hour = ignored.
─────────────────────────────────────────────────────────────
```

### Scenario: App stops at 5:00 AM, UI Scheduler was set for "Every 5 Minutes"

```
5:00 AM  ── App stops, custom interval job is lost
7:00 AM  ── App restarts
           └── restore_settings_from_db() reads MongoDB
           └── Finds saved setting: interval=5min, running=True
           └── Automatically restarts the custom job
           └── News starts collecting again
```

This is why we have `_save_settings_to_db()` and `restore_settings_from_db()`.
Settings survive app restarts because they are stored in MongoDB.

### Summary Table

| Situation | Result |
|---|---|
| App running, time matches | Job fires ✅ |
| App stopped | Job does not fire ❌ |
| App restarted after missed CronTrigger | Missed job skipped, waits for next day |
| App restarted after missed IntervalTrigger | Resumes from current time |
| Custom job was running before stop | Auto-restored from MongoDB on restart |

### Important Limitation for Beginners

> APScheduler is **in-process**. It only works while your Python program is running.
>
> For production systems (real companies), you would use an **external task queue**
> like Celery + Redis, or a cloud scheduler like AWS EventBridge.
> For a learning project running on your laptop, APScheduler is perfect.

---

## PART 5 — How MongoDB Prevents Duplicate News

### The Problem

NewsData.io returns the same articles repeatedly.
If you fetch news about "artificial intelligence" at 6 AM and again at 7 AM,
many of the same articles appear in both responses.

Without protection, your database would have hundreds of copies of the same article.

### Solution: Unique Index on URL

Every news article has a URL. URLs are globally unique.
No two different articles share the same URL.

We create a **Unique Index** on the `url` field in MongoDB:

```python
news_collection.create_index(
    [("url", ASCENDING)],
    unique=True,          # ← this is the key part
    name="url_unique"
)
```

### What a Unique Index Does

Think of it like a **bouncer at a nightclub** checking ID.

```
Article arrives → MongoDB checks: "Is this URL already in the collection?"
                       │
           ┌───────────┴───────────┐
           │ NO — URL is new       │ YES — URL exists
           ▼                       ▼
      INSERT document         REJECT with DuplicateKeyError
      Return success          (article discarded silently)
```

### The Exact Code Path

```python
# In database.py — save_news_article()

def save_news_article(article):
    try:
        result = collection.insert_one(article)
        return {"saved": True, "reason": "inserted"}

    except DuplicateKeyError:
        # MongoDB raised this because the URL already exists
        # This is EXPECTED behaviour — not an error
        return {"saved": False, "reason": "duplicate"}
```

```python
# In news_service.py — process_and_save_articles()

result = save_news_article(article)

if result["saved"]:
    counts["saved"] += 1          # new article stored
elif result["reason"] == "duplicate":
    counts["duplicates"] += 1     # silently skipped
```

### Proof It Works

From the scheduler test output you saw earlier:

```
[TOPIC] 'agentic AI':       saved=3, duplicates=7, skipped=0
[TOPIC] 'quantum computing': saved=1, duplicates=9, skipped=0
```

7 out of 10 "agentic AI" articles were already in the database.
MongoDB rejected them automatically via the unique index.
No manual checking. No loops comparing URLs. One index does it all.

### Why Not Just Check Before Inserting?

You might think:
```python
# Why not do this?
if collection.find_one({"url": article["url"]}):
    skip()
else:
    insert()
```

This approach has a problem called a **race condition**.
If two processes check at the same time and both find "not exists",
both will insert — creating a duplicate.

The unique index check happens **inside MongoDB** as a single atomic operation.
It is impossible to insert a duplicate, even under heavy load.

---

## PART 6 — How News Travels: API → Python → MongoDB → REST API → Postman

This is the complete data journey of one news article.

### Visual Map

```
NewsData.io API
      │
      │  HTTP GET Request
      │  URL: https://newsdata.io/api/1/news
      │  Params: q=AI, language=en, apikey=pub_xxx
      │
      ▼
fetch_news_from_api("artificial intelligence")
  [news_service.py]
      │
      │  response.json() → Python dictionary
      │
      ▼
Raw article dictionary:
{
  "title":       "OpenAI releases GPT-5",
  "link":        "https://techcrunch.com/...",
  "description": "OpenAI has announced...",
  "pubDate":     "2026-10-18 06:00:00",
  "source_name": "TechCrunch",
  "creator":     ["Jane Smith"]
}
      │
      ▼
process_and_save_articles(raw_articles)
  [news_service.py]
      │
      ├── categorize_article(title, description)
      │     Loops through CATEGORY_KEYWORDS in config.py
      │     Finds "openai" → matches "AI" category
      │     Returns "AI"
      │
      ├── create_news_article(...)
      │     [models.py]
      │     Cleans all fields (strips whitespace, handles None)
      │     Parses "2026-10-18 06:00:00" → datetime object
      │     Returns clean dictionary:
      │     {
      │       "title":        "OpenAI releases GPT-5",
      │       "description":  "OpenAI has announced...",
      │       "source":       "TechCrunch",
      │       "author":       "Jane Smith",
      │       "url":          "https://techcrunch.com/...",
      │       "category":     "AI",
      │       "published_at": datetime(2026, 10, 18, 6, 0, tzinfo=UTC),
      │       "collected_at": datetime(2026, 10, 18, 6, 5, tzinfo=UTC)
      │     }
      │
      ▼
save_news_article(article)
  [database.py]
      │
      ├── Calls collection.insert_one(article)
      ├── MongoDB checks unique index on "url"
      │     URL is new → INSERT
      │     URL exists → DuplicateKeyError → skip
      │
      ▼
MongoDB stores the document:
{
  "_id":          ObjectId("6713a8c2f1b2c3d4e5f60001"),  ← auto-generated
  "title":        "OpenAI releases GPT-5",
  "description":  "OpenAI has announced...",
  "source":       "TechCrunch",
  "author":       "Jane Smith",
  "url":          "https://techcrunch.com/...",
  "category":     "AI",
  "published_at": ISODate("2026-10-18T06:00:00Z"),
  "collected_at": ISODate("2026-10-18T06:05:12Z")
}

      ▼

Later — Postman calls GET /news
  [main.py]
      │
      ├── collection.find({}).sort("collected_at", -1).limit(20)
      │     MongoDB reads documents from disk
      │     Returns cursor (lazy list)
      │     Python converts to list()
      │
      ├── serialize_doc(article)
      │     ObjectId → "6713a8c2f1b2c3d4e5f60001" (string)
      │     datetime → "2026-10-18T06:00:00" (string)
      │     (JSON cannot serialize ObjectId or datetime directly)
      │
      ├── jsonify(response)
      │     Python dict → JSON string
      │
      ▼
Flask sends HTTP Response to Postman:
HTTP 200 OK
Content-Type: application/json

{
  "success": true,
  "message": "Retrieved 20 articles",
  "data": {
    "articles": [
      {
        "_id":          "6713a8c2f1b2c3d4e5f60001",
        "title":        "OpenAI releases GPT-5",
        "description":  "OpenAI has announced...",
        "source":       "TechCrunch",
        "author":       "Jane Smith",
        "url":          "https://techcrunch.com/...",
        "category":     "AI",
        "published_at": "2026-10-18T06:00:00",
        "collected_at": "2026-10-18T06:05:12"
      }
    ],
    "count": 20
  }
}
```

### Data Transformation at Each Stage

| Stage | Format | Example |
|---|---|---|
| NewsData.io response | JSON string over HTTP | `{"title": "...", "link": "..."}` |
| After `response.json()` | Python dict | `{"title": "...", "link": "..."}` |
| After `create_news_article()` | Clean Python dict | `{"title": "...", "url": "..."}` |
| Inside MongoDB | BSON document | `{_id: ObjectId, published_at: ISODate}` |
| After `serialize_doc()` | JSON-safe Python dict | `{_id: "string", published_at: "ISO string"}` |
| In Postman | JSON text | `{"_id": "6713...", "title": "..."}` |

---

## PART 7 — Complete File-by-File Responsibilities

```
daily-tech-news/
│
├── .env                  ← API keys, MongoDB URL, schedule time
│                           Never committed to GitHub
│
├── config.py             ← Reads .env into a Python dictionary
│                           Every other file imports from here
│                           Single source of truth for all settings
│
├── database.py           ← MongoDB connection management
│                           Creates one connection, shared by all files
│                           Creates indexes (including unique URL index)
│                           save_news_article() with DuplicateKeyError handling
│
├── models.py             ← Data structure templates
│                           create_news_article() cleans and normalises raw data
│                           create_daily_briefing() structures briefing data
│                           Ensures every MongoDB document looks the same
│
├── news_service.py       ← News collection pipeline
│                           fetch_news_from_api() → HTTP GET to NewsData.io
│                           categorize_article()  → keyword matching
│                           process_and_save_articles() → clean + store loop
│                           collect_all_news()    → master pipeline function
│                           search_news()         → MongoDB $regex search
│
├── briefing_service.py   ← Daily briefing generation
│                           score_article()       → 0-10 importance score
│                           select_top_news()     → best article per category
│                           format_briefing_text()→ formatted text output
│                           run_daily_briefing()  → master briefing function
│
├── scheduler.py          ← APScheduler management
│                           BackgroundScheduler with two jobs:
│                             daily_news_job  → CronTrigger at 6:00 AM
│                             custom_news_job → IntervalTrigger from UI
│                           start/stop/configure/status for the UI
│                           Saves settings to MongoDB for persistence
│
├── main.py               ← Application entry point + Flask REST API
│                           Starts MongoDB connection
│                           Starts APScheduler
│                           Restores saved scheduler settings
│                           Serves all REST API endpoints
│                           Serves the HTML dashboard at GET /
│
├── templates/index.html  ← Dashboard HTML page
│                           Interval selector cards
│                           Start / Stop / Save / Fetch Now buttons
│                           Status panel + countdown timer
│                           News cards grid
│
├── static/style.css      ← Dashboard styles
│                           Dark/light theme
│                           Responsive grid layout
│
└── static/app.js         ← Dashboard JavaScript
                            Polls GET /scheduler/status every 15 seconds
                            Countdown timer (ticks every second)
                            Calls POST /scheduler/start|stop|configure
                            Fetches GET /news and renders cards
                            Shows toast when new articles arrive
```

---

## PART 8 — All REST API Endpoints

| Method | Endpoint | Who Calls It | What It Does |
|---|---|---|---|
| GET | `/` | Browser | Returns the dashboard HTML page |
| GET | `/health` | Postman / monitoring | App + DB + scheduler status |
| GET | `/news` | Dashboard JS / Postman | Latest articles, optional limit + category filter |
| GET | `/news/search?keyword=AI` | Dashboard JS / Postman | Regex search across title, description, category |
| GET | `/news/category/AI` | Postman | Articles in one category |
| GET | `/news/<id>` | Postman | Single article by MongoDB ObjectId |
| GET | `/briefings` | Postman | All stored daily briefings |
| GET | `/briefings/2026-10-18` | Postman | One day's full briefing |
| POST | `/collect` | Postman | Trigger collect_all_news() synchronously |
| POST | `/scheduler/start` | Dashboard JS | Start custom interval job |
| POST | `/scheduler/stop` | Dashboard JS | Stop custom interval job |
| POST | `/scheduler/configure` | Dashboard JS | Change interval, reschedule if running |
| GET | `/scheduler/status` | Dashboard JS (every 15s) | Running status, next run, last run, counts |
| POST | `/news/fetch-now` | Dashboard JS | Immediate fetch in background thread |

---

## PART 9 — MongoDB Collections

### tech_news.news

Stores all collected articles. One document per article.
Unique index on `url` — prevents all duplicates.

```
Collection: news
Indexes:
  url          → UNIQUE (no duplicates)
  published_at → ASCENDING (fast date queries)
  category     → ASCENDING (fast category filter)
```

### tech_news.daily_briefings

One document per day. Generated by `briefing_service.py`.
Unique index on `briefing_date` — only one briefing per day.

```
Collection: daily_briefings
Indexes:
  briefing_date → UNIQUE (one per day)
```

### tech_news.scheduler_settings

One document (upserted). Stores the user's scheduler preferences.
Created the first time you click Save in the dashboard.

```
Collection: scheduler_settings
Document:
  settings_key: "main"
  interval:     "5min"
  running:      true
  last_run:     "2026-10-18T09:31:16"
  saved_at:     "2026-10-18T09:31:16"
```

---

## PART 10 — Interview Questions

These are questions an interviewer might ask about this project.

**Python / General:**
1. What is the difference between a thread and a process in Python?
2. What does `daemon=True` mean when creating a thread?
3. What is the `if __name__ == "__main__"` guard and why do we use it?
4. What is the difference between `os.getenv()` and hardcoding a value?
5. Why do we use `try / except / finally` instead of just `try / except`?

**APScheduler:**
1. What is the difference between `CronTrigger` and `IntervalTrigger`?
2. What happens if an APScheduler job is still running when the next trigger fires?
3. What does `misfire_grace_time=30` do?
4. Why do we set `use_reloader=False` when running Flask with APScheduler?
5. How would you persist a scheduler job across Python restarts?

**MongoDB:**
1. What is a unique index and how does it prevent duplicates?
2. What is the difference between `insert_one()` and `update_one(..., upsert=True)`?
3. What does `DuplicateKeyError` mean and when does it occur?
4. What is the difference between a collection and a database in MongoDB?
5. Why do we convert `ObjectId` to string before sending JSON to a client?

**REST APIs:**
1. What is the difference between GET and POST HTTP methods?
2. What does HTTP status code 404 mean? What about 409? 503?
3. Why do we never expose API keys or error stack traces in API responses?
4. What is the purpose of `serialize_doc()` in this project?
5. What would happen if we registered `GET /news/<id>` before `GET /news/search`?

---

*Document generated for the Daily Global Tech News Scheduler project.*
*Last updated: 2026-10-18*
