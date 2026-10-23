# =============================================================
# database.py — MongoDB connection and collection access
#
# WHAT THIS FILE DOES:
#   - Connects to MongoDB using the URI from config.py
#   - Provides helper functions to get collections
#   - Creates indexes (including a unique index on news URLs)
#   - Handles connection errors gracefully
#
# HOW OTHER FILES USE IT:
#   from database import get_news_collection, get_briefings_collection
#   news_col = get_news_collection()
#   news_col.insert_one(article)
# =============================================================

from pymongo import MongoClient, ASCENDING   # PyMongo: official MongoDB driver
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from config import config   # Our central config dictionary

# =============================================================
# Module-level variables
#
# These are set once when connect_to_mongodb() runs.
# Using module-level variables means we create only ONE
# connection for the entire application (connection pooling).
#
# "Private" by convention — the underscore prefix means
# "don't use this directly from outside this file"
# =============================================================
_client = None    # The MongoClient object (the connection itself)
_db = None        # The database object (tech_news)


def connect_to_mongodb():
    """
    Establish a connection to MongoDB.

    Returns the database object if successful, None if it fails.

    This function is called once when the application starts.
    After that, get_db() reuses the same connection.
    """
    # We use 'global' because we want to modify the module-level
    # variables _client and _db, not create new local variables
    global _client, _db

    try:
        # MongoClient creates the connection to MongoDB
        # serverSelectionTimeoutMS=5000 means: if MongoDB doesn't
        # respond within 5 seconds, give up and raise an error
        # (default is 30 seconds — too long to wait for a startup error)
        _client = MongoClient(
            config["MONGO_URI"],
            serverSelectionTimeoutMS=5000
        )

        # The ping command forces an actual connection attempt.
        # Without this, MongoClient appears to succeed even if
        # MongoDB isn't running (it connects lazily).
        _client.admin.command("ping")

        # Access (or create) the database by name
        # MongoDB creates the database automatically on first use
        _db = _client[config["MONGO_DB_NAME"]]

        print(f"[DB] Connected to MongoDB successfully")
        print(f"[DB] Database: {config['MONGO_DB_NAME']}")

        # Set up indexes after connecting
        create_indexes()

        return _db

    except ServerSelectionTimeoutError:
        # MongoDB is not running or the URI is wrong
        print("[DB ERROR] Cannot connect to MongoDB.")
        print("[DB ERROR] Make sure MongoDB is running on your machine.")
        print(f"[DB ERROR] Tried to connect to: {config['MONGO_URI']}")
        return None

    except ConnectionFailure as e:
        # Connected but then lost the connection
        print(f"[DB ERROR] MongoDB connection failed: {e}")
        return None

    except Exception as e:
        # Catch-all for unexpected errors
        print(f"[DB ERROR] Unexpected error connecting to MongoDB: {e}")
        return None


def get_db():
    """
    Return the database object.

    If not yet connected, connect first.
    This is called by get_news_collection() and get_briefings_collection().
    """
    global _db

    # If _db is None, we haven't connected yet — connect now
    if _db is None:
        connect_to_mongodb()

    return _db


def get_news_collection():
    """
    Return the 'news' collection.

    Used by:
      - news_service.py  (to insert articles)
      - main.py          (to query articles via REST API)
    """
    db = get_db()

    if db is None:
        # This will be caught by the calling code
        raise ConnectionError("MongoDB is not connected. Cannot access 'news' collection.")

    return db[config["NEWS_COLLECTION"]]


def get_briefings_collection():
    """
    Return the 'daily_briefings' collection.

    Used by:
      - briefing_service.py  (to store generated briefings)
      - main.py              (to query briefings via REST API)
    """
    db = get_db()

    if db is None:
        raise ConnectionError("MongoDB is not connected. Cannot access 'daily_briefings' collection.")

    return db[config["BRIEFINGS_COLLECTION"]]


def create_indexes():
    """
    Create MongoDB indexes for better performance and data integrity.

    UNIQUE INDEX on news.url:
      - Prevents storing the same article twice
      - MongoDB will automatically reject any insert with a duplicate URL
      - This is more reliable than checking manually before every insert
    
    INDEX on news.published_at:
      - Makes date-range queries fast (e.g., "all news from today")
    
    INDEX on news.category:
      - Makes category filter queries fast
    
    INDEX on daily_briefings.briefing_date:
      - Makes looking up a specific day's briefing fast
    """
    try:
        db = get_db()
        if db is None:
            return

        news_col = db[config["NEWS_COLLECTION"]]
        briefings_col = db[config["BRIEFINGS_COLLECTION"]]

        # --- Unique index on URL ---
        # unique=True means MongoDB raises DuplicateKeyError on duplicate URLs
        # This is our duplicate-prevention mechanism
        news_col.create_index(
            [("url", ASCENDING)],
            unique=True,
            name="url_unique"
        )

        # --- Index on published date ---
        # ASCENDING = oldest first. Used when filtering today's news.
        news_col.create_index(
            [("published_at", ASCENDING)],
            name="published_at_index"
        )

        # --- Index on category ---
        # Used when querying: GET /news/category/AI
        news_col.create_index(
            [("category", ASCENDING)],
            name="category_index"
        )

        # --- Unique index on briefing date ---
        # Only one briefing per day should exist
        briefings_col.create_index(
            [("briefing_date", ASCENDING)],
            unique=True,
            name="briefing_date_unique"
        )

        print("[DB] Indexes created (or already exist)")

    except Exception as e:
        # Indexes may already exist from a previous run — that is fine
        print(f"[DB] Index setup note: {e}")


def save_news_article(article):
    """
    Insert one news article into the 'news' collection.

    Returns a result dict with:
      - "saved": True if inserted, False if duplicate or error
      - "reason": explanation string
      - "id": the new document's ObjectId (as string) if saved

    WHY WE HANDLE DuplicateKeyError HERE:
      MongoDB's unique index on 'url' will raise DuplicateKeyError
      if we try to insert an article that already exists.
      This is expected behaviour — not a bug. We catch it and
      return saved=False so the calling code knows to skip this article.
    """
    # Import here to avoid circular imports at module load time
    from pymongo.errors import DuplicateKeyError

    try:
        col = get_news_collection()
        result = col.insert_one(article)

        return {
            "saved": True,
            "reason": "inserted",
            "id": str(result.inserted_id)
        }

    except DuplicateKeyError:
        # This article URL already exists in the database — skip it
        return {
            "saved": False,
            "reason": "duplicate"
        }

    except ConnectionError as e:
        return {
            "saved": False,
            "reason": f"db_not_connected: {e}"
        }

    except Exception as e:
        return {
            "saved": False,
            "reason": f"error: {e}"
        }


def test_connection():
    """
    Simple function to test and display the current connection status.
    Useful for debugging and for the GET /health API endpoint.
    """
    try:
        db = get_db()
        if db is None:
            return {"status": "disconnected", "message": "MongoDB is not running"}

        # List collection names to confirm the database is accessible
        collections = db.list_collection_names()

        return {
            "status": "connected",
            "database": config["MONGO_DB_NAME"],
            "collections": collections
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def get_scheduler_settings_collection():
    """
    Return the 'scheduler_settings' collection.
    Stores the user's custom scheduler configuration.
    Used by scheduler.py to persist and restore settings.
    """
    db = get_db()
    if db is None:
        raise ConnectionError("MongoDB not connected. Cannot access 'scheduler_settings'.")
    return db["scheduler_settings"]
