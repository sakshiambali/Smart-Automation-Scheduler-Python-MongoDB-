# =============================================================
# main.py — Flask REST API server + application entry point
#
# ORIGINAL ENDPOINTS (unchanged):
#   GET  /health
#   GET  /news
#   GET  /news/search?keyword=python
#   GET  /news/category/<category>
#   GET  /news/<id>
#   GET  /briefings
#   GET  /briefings/<date>
#   POST /collect
#
# NEW ENDPOINTS (for UI dashboard):
#   GET  /                       — serve the dashboard HTML
#   POST /scheduler/start        — start custom interval job
#   POST /scheduler/stop         — stop custom interval job
#   POST /scheduler/configure    — change interval
#   GET  /scheduler/status       — rich status for dashboard
#   POST /news/fetch-now         — immediate non-blocking fetch
# =============================================================

from flask import Flask, jsonify, request, render_template
from bson import ObjectId
from bson.errors import InvalidId
import json
import threading
from datetime import datetime, timezone

from config import config
from database import connect_to_mongodb, test_connection
from scheduler import (
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    start_custom_job,
    stop_custom_job,
    configure_custom_job,
    get_custom_job_status,
    restore_settings_from_db,
)
from news_service import (
    get_todays_news,
    get_news_by_category,
    search_news,
    collect_all_news,
    get_news_collection
)
from briefing_service import get_all_briefings, get_briefing_by_date


# =============================================================
# FLASK APP SETUP
# =============================================================

# Flask(__name__) creates the application
# __name__ tells Flask where to find templates and static files
app = Flask(__name__)

# Ensure Flask returns JSON with proper Unicode characters
# Without this, non-ASCII characters (like é, ü, 中) get escaped to \u00e9
app.config["JSON_ENSURE_ASCII"] = False


# =============================================================
# HELPER FUNCTIONS
# =============================================================

def serialize_doc(doc):
    """
    Convert a MongoDB document to a JSON-serializable dictionary.

    THE PROBLEM:
      MongoDB documents contain ObjectId and datetime objects.
      Python's json module doesn't know how to serialize these.
      jsonify() would crash with: "Object of type ObjectId is not
      JSON serializable"

    THE SOLUTION:
      Convert ObjectId → string, datetime → ISO format string
      before passing to jsonify().

    Parameters:
      doc - A MongoDB document (Python dictionary)

    Returns:
      A new dictionary with all values JSON-serializable
    """
    if doc is None:
        return None

    result = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            # ObjectId → string: "6713a8c2f1b2c3d4e5f60001"
            result[key] = str(value)

        elif isinstance(value, datetime):
            # datetime → ISO 8601 string: "2026-10-18T06:00:00"
            result[key] = value.isoformat()

        elif isinstance(value, list):
            # Recursively serialize items in a list
            # (e.g., top_news list in briefings)
            result[key] = [
                serialize_doc(item) if isinstance(item, dict) else item
                for item in value
            ]

        elif isinstance(value, dict):
            # Recursively serialize nested dicts
            result[key] = serialize_doc(value)

        else:
            # String, int, float, bool, None — already serializable
            result[key] = value

    return result


def success_response(data, message="Success", status_code=200):
    """
    Build a consistent successful API response.

    All our endpoints return the same structure:
    {
        "success": true,
        "message": "...",
        "data": { ... } or [ ... ],
        "timestamp": "..."
    }

    This consistency makes the API easier to use from Postman
    or any frontend — you always know where to find your data.
    """
    response = {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return jsonify(response), status_code


def error_response(message, status_code=400):
    """
    Build a consistent error API response.

    {
        "success": false,
        "message": "Error description",
        "data": null,
        "timestamp": "..."
    }

    We NEVER include internal details (stack traces, MongoDB errors,
    connection strings) in error responses — they would leak
    sensitive information to API callers.
    """
    response = {
        "success": False,
        "message": message,
        "data": None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return jsonify(response), status_code


# =============================================================
# ENDPOINT 1: HEALTH CHECK
# GET /health
# =============================================================

@app.route("/health", methods=["GET"])
def health_check():
    """
    Check if the application is running correctly.

    Returns the status of:
      - The Flask application itself
      - MongoDB connection
      - The scheduler

    USE IN POSTMAN:
      GET http://localhost:5000/health

    This is always the first endpoint to test when debugging.
    """
    db_status    = test_connection()
    sched_status = get_scheduler_status()

    health_data = {
        "app":       "Daily Global Tech News Scheduler",
        "status":    "running",
        "database":  db_status,
        "scheduler": sched_status,
    }

    # If database is not connected, return 503 (Service Unavailable)
    # 503 tells the caller: app is running but a dependency is down
    if db_status.get("status") != "connected":
        return error_response(
            "Application running but database is disconnected",
            status_code=503
        )

    return success_response(health_data, "Application is healthy")


# =============================================================
# ENDPOINT 2: GET LATEST NEWS
# GET /news
# GET /news?limit=10
# =============================================================

@app.route("/news", methods=["GET"])
def get_news():
    """
    Return the latest collected news articles.

    Query parameters (optional):
      limit    - max number of articles to return (default: 20, max: 100)
      category - filter by category (optional)

    USE IN POSTMAN:
      GET http://localhost:5000/news
      GET http://localhost:5000/news?limit=5
      GET http://localhost:5000/news?category=AI
    """
    try:
        # request.args is a dictionary of query string parameters
        # ?limit=10 → request.args.get("limit") = "10" (always a string)
        # int(...) converts it to an integer
        limit = int(request.args.get("limit", 20))

        # Clamp limit to a safe range — prevent someone requesting 999999 articles
        limit = max(1, min(limit, 100))

        category_filter = request.args.get("category")

        col = get_news_collection()

        if category_filter:
            # Filter by category if provided
            query = {"category": category_filter}
        else:
            query = {}

        articles = list(
            col.find(query)
               .sort("collected_at", -1)   # newest collected first
               .limit(limit)
        )

        # Serialize all MongoDB documents
        serialized = [serialize_doc(a) for a in articles]

        return success_response(
            {
                "articles": serialized,
                "count": len(serialized),
                "limit": limit,
                "filter": category_filter or "none"
            },
            f"Retrieved {len(serialized)} articles"
        )

    except ValueError:
        return error_response("Invalid 'limit' parameter. Must be a number.")

    except Exception as e:
        print(f"[API ERROR] GET /news: {e}")
        return error_response("Could not retrieve news", status_code=500)


# =============================================================
# ENDPOINT 3: SEARCH NEWS
# GET /news/search?keyword=python
# IMPORTANT: This must be registered BEFORE /news/<id>
# =============================================================

@app.route("/news/search", methods=["GET"])
def search_news_endpoint():
    """
    Search articles by keyword in title, description, or category.

    Query parameters:
      keyword  - search term (required)
      limit    - max results (default: 20)

    USE IN POSTMAN:
      GET http://localhost:5000/news/search?keyword=python
      GET http://localhost:5000/news/search?keyword=quantum&limit=5

    WHAT IT SEARCHES:
      - article title
      - article description
      - category name
    """
    keyword = request.args.get("keyword", "").strip()

    if not keyword:
        return error_response(
            "Missing 'keyword' parameter. Use: /news/search?keyword=python"
        )

    if len(keyword) < 2:
        return error_response("Keyword must be at least 2 characters long.")

    try:
        limit = int(request.args.get("limit", 20))
        limit = max(1, min(limit, 100))

        articles = search_news(keyword)

        # Apply limit (search_news already limits to 20 internally)
        articles = articles[:limit]

        serialized = [serialize_doc(a) for a in articles]

        return success_response(
            {
                "articles": serialized,
                "count": len(serialized),
                "keyword": keyword
            },
            f"Found {len(serialized)} articles matching '{keyword}'"
        )

    except Exception as e:
        print(f"[API ERROR] GET /news/search: {e}")
        return error_response("Search failed", status_code=500)


# =============================================================
# ENDPOINT 4: GET NEWS BY CATEGORY
# GET /news/category/<category>
# =============================================================

@app.route("/news/category/<string:category>", methods=["GET"])
def get_news_by_category_endpoint(category):
    """
    Return articles for a specific technology category.

    URL parameter:
      category - the category name (case-sensitive)

    USE IN POSTMAN:
      GET http://localhost:5000/news/category/AI
      GET http://localhost:5000/news/category/Cybersecurity
      GET http://localhost:5000/news/category/Quantum%20Computing

    VALID CATEGORIES:
      AI, Agentic AI, Quantum Computing, Cloud Computing,
      Cybersecurity, Programming, Developer Tools,
      Startups, Technology Companies, Other Technology
    """
    # Build valid category list from config + default
    valid_categories = list(config["CATEGORY_KEYWORDS"].keys())
    valid_categories.append(config["DEFAULT_CATEGORY"])

    # Case-insensitive match — allow "ai" to match "AI"
    # Find the properly-cased version of the requested category
    matched_category = None
    for valid in valid_categories:
        if valid.lower() == category.lower():
            matched_category = valid
            break

    if not matched_category:
        return error_response(
            f"Unknown category: '{category}'. "
            f"Valid categories: {', '.join(valid_categories)}",
            status_code=404
        )

    try:
        articles = get_news_by_category(matched_category)
        serialized = [serialize_doc(a) for a in articles]

        return success_response(
            {
                "articles": serialized,
                "count": len(serialized),
                "category": matched_category
            },
            f"Retrieved {len(serialized)} articles for category '{matched_category}'"
        )

    except Exception as e:
        print(f"[API ERROR] GET /news/category/{category}: {e}")
        return error_response("Could not retrieve category news", status_code=500)


# =============================================================
# ENDPOINT 5: GET ONE ARTICLE BY ID
# GET /news/<id>
# IMPORTANT: This must come AFTER /news/search
# =============================================================

@app.route("/news/<string:article_id>", methods=["GET"])
def get_single_article(article_id):
    """
    Return one specific article by its MongoDB ObjectId.

    URL parameter:
      article_id - the 24-character MongoDB ObjectId string

    USE IN POSTMAN:
      GET http://localhost:5000/news/6713a8c2f1b2c3d4e5f60001

    HOW TO GET AN ID:
      First call GET /news to get a list, then copy the "_id"
      value from any article and use it here.
    """
    try:
        # Convert the string ID to a MongoDB ObjectId object
        # This will raise InvalidId if the string is not a valid ObjectId
        obj_id = ObjectId(article_id)

    except InvalidId:
        return error_response(
            f"Invalid article ID format: '{article_id}'. "
            "Must be a 24-character hex string.",
            status_code=400
        )

    try:
        col = get_news_collection()
        article = col.find_one({"_id": obj_id})

        if article is None:
            return error_response(
                f"No article found with ID: {article_id}",
                status_code=404
            )

        return success_response(
            serialize_doc(article),
            "Article retrieved successfully"
        )

    except Exception as e:
        print(f"[API ERROR] GET /news/{article_id}: {e}")
        return error_response("Could not retrieve article", status_code=500)


# =============================================================
# ENDPOINT 6: GET ALL BRIEFINGS
# GET /briefings
# =============================================================

@app.route("/briefings", methods=["GET"])
def get_briefings():
    """
    Return all stored daily briefings (summary, without full text).

    USE IN POSTMAN:
      GET http://localhost:5000/briefings
    """
    try:
        briefings = get_all_briefings()
        serialized = [serialize_doc(b) for b in briefings]

        return success_response(
            {
                "briefings": serialized,
                "count": len(serialized)
            },
            f"Retrieved {len(serialized)} briefings"
        )

    except Exception as e:
        print(f"[API ERROR] GET /briefings: {e}")
        return error_response("Could not retrieve briefings", status_code=500)


# =============================================================
# ENDPOINT 7: GET BRIEFING BY DATE
# GET /briefings/<date>
# =============================================================

@app.route("/briefings/<string:date>", methods=["GET"])
def get_briefing_by_date_endpoint(date):
    """
    Return the daily briefing for a specific date.

    URL parameter:
      date - format YYYY-MM-DD (e.g., 2026-10-18)

    USE IN POSTMAN:
      GET http://localhost:5000/briefings/2026-10-18

    RETURNS:
      The full briefing including briefing_text (the formatted string)
    """
    # Validate the date format before querying MongoDB
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return error_response(
            f"Invalid date format: '{date}'. Use YYYY-MM-DD (e.g., 2026-10-18)",
            status_code=400
        )

    try:
        briefing = get_briefing_by_date(date)

        if briefing is None:
            return error_response(
                f"No briefing found for date: {date}",
                status_code=404
            )

        return success_response(
            serialize_doc(briefing),
            f"Briefing for {date} retrieved successfully"
        )

    except Exception as e:
        print(f"[API ERROR] GET /briefings/{date}: {e}")
        return error_response("Could not retrieve briefing", status_code=500)


# =============================================================
# ENDPOINT 8: TRIGGER NEWS COLLECTION MANUALLY
# POST /collect
# =============================================================

@app.route("/collect", methods=["POST"])
def trigger_collection():
    """
    Manually trigger the news collection pipeline.

    Useful for testing without waiting for the 6 AM schedule.

    USE IN POSTMAN:
      POST http://localhost:5000/collect
      (No body needed)

    NOTE: This runs synchronously — the response will take
    ~30 seconds while collection happens. In a production app
    you would run this as a background task. For this learning
    project, synchronous is fine and easier to understand.
    """
    print("[API] Manual collection triggered via POST /collect")

    try:
        summary = collect_all_news()

        return success_response(
            summary,
            f"Collection complete. {summary['total_saved']} new articles saved."
        )

    except Exception as e:
        print(f"[API ERROR] POST /collect: {e}")
        return error_response("News collection failed", status_code=500)


# =============================================================
# 404 AND 500 ERROR HANDLERS
# =============================================================

# =============================================================
# DASHBOARD — serve the HTML UI
# GET /
# =============================================================

@app.route("/", methods=["GET"])
def dashboard():
    """Serve the news dashboard HTML page."""
    return render_template("index.html")


# =============================================================
# ENDPOINT: START CUSTOM SCHEDULER
# POST /scheduler/start
# Body (optional JSON): {"interval": "5min"}
# =============================================================

@app.route("/scheduler/start", methods=["POST"])
def scheduler_start():
    """
    Start the custom interval news-fetch scheduler.

    Optional JSON body:
      {"interval": "1min" | "5min" | "1hour" | "1day"}

    If no interval is provided, uses the last configured interval.
    """
    body = request.get_json(silent=True) or {}
    interval = body.get("interval")   # may be None — start_custom_job handles that

    result = start_custom_job(interval)

    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


# =============================================================
# ENDPOINT: STOP CUSTOM SCHEDULER
# POST /scheduler/stop
# =============================================================

@app.route("/scheduler/stop", methods=["POST"])
def scheduler_stop():
    """Stop the custom interval news-fetch scheduler."""
    result = stop_custom_job()
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


# =============================================================
# ENDPOINT: CONFIGURE INTERVAL
# POST /scheduler/configure
# Body: {"interval": "5min"}
# =============================================================

@app.route("/scheduler/configure", methods=["POST"])
def scheduler_configure():
    """
    Change the scheduler interval.
    If the scheduler is currently running, it restarts with the new interval.
    If stopped, the new interval is saved for next start.

    Required JSON body:
      {"interval": "1min" | "5min" | "1hour" | "1day"}
    """
    body = request.get_json(silent=True) or {}
    interval = body.get("interval")

    if not interval:
        return error_response(
            "Missing 'interval'. Send: {\"interval\": \"5min\"}",
            status_code=400
        )

    result = configure_custom_job(interval)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


# =============================================================
# ENDPOINT: GET SCHEDULER STATUS
# GET /scheduler/status
# =============================================================

@app.route("/scheduler/status", methods=["GET"])
def scheduler_status():
    """
    Return full scheduler status for the dashboard.

    The frontend polls this every 15 seconds to:
    - Update the countdown timer
    - Refresh the Running/Stopped badge
    - Show last run time and article counts
    """
    status = get_custom_job_status()
    return success_response(status, "Scheduler status retrieved")


# =============================================================
# ENDPOINT: FETCH NEWS NOW (non-blocking)
# POST /news/fetch-now
# =============================================================

# Flag to prevent two simultaneous manual fetches
_fetch_now_in_progress = False

@app.route("/news/fetch-now", methods=["POST"])
def fetch_news_now():
    """
    Trigger an immediate news fetch without waiting for the schedule.

    Runs in a background thread so the HTTP response returns
    immediately (< 1 second). The UI polls GET /scheduler/status
    to see when it finishes.

    Returns 409 Conflict if a fetch is already in progress.
    """
    global _fetch_now_in_progress

    if _fetch_now_in_progress:
        return error_response(
            "A fetch is already in progress. Please wait.",
            status_code=409
        )

    def _run_fetch():
        global _fetch_now_in_progress
        try:
            from news_service import collect_all_news
            collect_all_news()
        except Exception as e:
            print(f"[FETCH-NOW ERROR] {e}")
        finally:
            _fetch_now_in_progress = False

    _fetch_now_in_progress = True
    thread = threading.Thread(target=_run_fetch, daemon=True)
    thread.start()

    return success_response(
        {"message": "Fetch started in background"},
        "News fetch started. Refresh in ~30 seconds."
    )



    """Handle requests to endpoints that don't exist."""
    return error_response(
        f"Endpoint not found. Check the URL and HTTP method.",
        status_code=404
    )


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle wrong HTTP method (e.g., POST to a GET-only endpoint)."""
    return error_response(
        "Method not allowed. Check if you're using GET or POST correctly.",
        status_code=405
    )


@app.errorhandler(500)
def internal_error(error):
    """Handle unexpected server errors."""
    return error_response(
        "Internal server error. Check the server logs.",
        status_code=500
    )


# =============================================================
# APPLICATION STARTUP
# =============================================================

def create_app():
    """
    Initialize all application components.

    Called once when main.py runs.
    Order matters:
      1. Connect to MongoDB first (other components need the DB)
      2. Start the scheduler (needs DB to be ready)
      3. Flask starts last (everything must be ready before serving requests)
    """
    print()
    print("=" * 62)
    print("  DAILY GLOBAL TECH NEWS SCHEDULER")
    print("  Starting up...")
    print("=" * 62)

    # Step 1: Connect to MongoDB
    db = connect_to_mongodb()
    if db is None:
        print("[STARTUP ERROR] MongoDB connection failed.")
        print("[STARTUP ERROR] Make sure MongoDB is running.")
        print("[STARTUP ERROR] Start it with: Start-Service MongoDB")
        return False

    # Step 2: Start the scheduler
    scheduler = start_scheduler()
    if scheduler is None:
        print("[STARTUP WARNING] Scheduler failed to start.")
        print("[STARTUP WARNING] The app will run but won't auto-collect news.")
        # Not a fatal error — app can still serve existing data

    # Step 3: Restore saved custom job settings from MongoDB
    restore_settings_from_db()

    print()
    print("=" * 62)
    print("  APPLICATION READY")
    print(f"  API server: http://localhost:{config['FLASK_PORT']}")
    print()
    print("  Endpoints:")
    print(f"    GET  http://localhost:{config['FLASK_PORT']}/health")
    print(f"    GET  http://localhost:{config['FLASK_PORT']}/news")
    print(f"    GET  http://localhost:{config['FLASK_PORT']}/news/search?keyword=AI")
    print(f"    GET  http://localhost:{config['FLASK_PORT']}/news/category/AI")
    print(f"    GET  http://localhost:{config['FLASK_PORT']}/briefings")
    print(f"    POST http://localhost:{config['FLASK_PORT']}/collect")
    print("=" * 62)
    print()

    return True


# =============================================================
# ENTRY POINT
# =============================================================

# This block runs when you execute: python main.py
# It does NOT run when main.py is imported by another file

if __name__ == "__main__":
    # Initialize all components
    ready = create_app()

    if not ready:
        print("Startup failed. Fix the errors above and try again.")
        exit(1)

    try:
        # Start Flask development server
        # host="0.0.0.0"  — accept connections from any IP on your network
        # port=5000        — listen on port 5000
        # debug=False      — don't use Flask debug mode (conflicts with APScheduler)
        #                    We control debug output ourselves
        # use_reloader=False — prevent Flask from starting twice (would duplicate scheduler)
        app.run(
            host="0.0.0.0",
            port=config["FLASK_PORT"],
            debug=False,
            use_reloader=False   # IMPORTANT: reloader would start scheduler twice
        )

    except KeyboardInterrupt:
        # User pressed Ctrl+C
        print()
        print("[SHUTDOWN] Stopping application...")
        stop_scheduler()
        print("[SHUTDOWN] Goodbye.")
