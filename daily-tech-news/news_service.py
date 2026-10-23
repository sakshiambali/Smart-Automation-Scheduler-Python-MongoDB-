# =============================================================
# news_service.py — Fetch, categorize, and save news articles
#
# WHAT THIS FILE DOES:
#   1. Sends HTTP GET requests to NewsAPI
#   2. Reads the JSON response
#   3. Categorizes each article using keyword matching
#   4. Saves clean articles to MongoDB (skips duplicates)
#
# MAIN FUNCTION (called by scheduler and manually):
#   collect_all_news() — runs the full pipeline
#
# HOW TO TEST MANUALLY:
#   python news_service.py
# =============================================================

import requests          # Third-party: makes HTTP requests
import time              # Built-in: used for sleep between API calls
from datetime import datetime, timezone

from config import config          # All settings and keywords
from models import create_news_article   # Data structure template
from database import save_news_article, get_news_collection   # MongoDB helpers


# =============================================================
# STEP 1: CATEGORIZE AN ARTICLE
# =============================================================

def categorize_article(title, description):
    """
    Determine which technology category an article belongs to.

    Logic:
      1. Combine title + description into one lowercase string
      2. Loop through CATEGORY_KEYWORDS from config.py
      3. Check if any keyword appears in the combined text
      4. Return the FIRST matching category
      5. If no keyword matches, return the default category

    WHY FIRST MATCH MATTERS:
      "Agentic AI" is checked before "AI" in config.py.
      An article about "AI agents" should be categorized as
      "Agentic AI", not just "AI". Order in config controls this.

    Parameters:
      title       - Article headline (string)
      description - Article summary (string, may be empty)

    Returns:
      A category string (e.g., "AI", "Cybersecurity")
    """
    # Combine title and description for keyword searching
    # .lower() makes the search case-insensitive
    # "GPT-5" and "gpt-5" and "Gpt-5" all become "gpt-5"
    combined_text = f"{title} {description}".lower()

    # Loop through the category keywords dictionary from config
    # .items() gives us both the key (category name) and value (keyword list)
    for category, keywords in config["CATEGORY_KEYWORDS"].items():
        # Loop through each keyword for this category
        for keyword in keywords:
            # 'in' operator checks if keyword is a substring of combined_text
            if keyword in combined_text:
                # Found a match — return this category immediately
                # No need to check the remaining categories
                return category

    # No keyword matched — return the default
    return config["DEFAULT_CATEGORY"]


# =============================================================
# STEP 2: FETCH NEWS FROM NEWSDATA.IO API
# =============================================================

def fetch_news_from_api(topic):
    """
    Fetch news articles from NewsData.io for a given topic.

    NewsData.io endpoint used:
      GET https://newsdata.io/api/1/news
      Parameters:
        q        = search query (e.g., "artificial intelligence")
        language = "en" (English only)
        apikey   = your NewsData.io API key (format: pub_XXXX...)

    NewsData.io response structure:
      {
        "status": "success",
        "totalResults": 1234,
        "results": [
          {
            "title":          "...",
            "description":    "...",
            "link":           "https://...",      <- NOTE: "link" not "url"
            "pubDate":        "2026-10-18 06:00:00",  <- NOTE: different format
            "source_id":      "techcrunch",
            "source_name":    "TechCrunch",       <- source name is a direct field
            "creator":        ["John Smith"],     <- list, not a string
            "category":       ["technology"],
            "image_url":      "https://..."
          }
        ],
        "nextPage": "token..."
      }

    KEY DIFFERENCES from GNews/NewsAPI:
      - Articles are in "results" not "articles"
      - URL field is "link" not "url"
      - Date field is "pubDate" not "publishedAt"
      - Source name is "source_name" (direct field, not nested)
      - Author is "creator" — a list (e.g., ["John Smith"])
      - Date format: "2026-10-18 06:00:00" (no T, no Z)

    Parameters:
      topic - A search term string (e.g., "quantum computing")

    Returns:
      A list of raw article dictionaries from NewsData.io
      Empty list [] if request fails or no results found
    """
    url = "https://newsdata.io/api/1/news"

    params = {
        "q":        topic,
        "language": config["NEWS_LANGUAGE"],   # "en"
        "apikey":   config["NEWS_API_KEY"],     # NewsData.io key: pub_XXXX...
    }

    try:
        print(f"  [FETCH] Searching NewsData.io: '{topic}'...")

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()

        # NewsData.io returns {"status": "error", "message": "..."} on failure
        if data.get("status") != "success":
            error_msg = data.get("message", data.get("results", "Unknown error"))
            print(f"  [FETCH ERROR] NewsData.io error: {error_msg}")
            return []

        # NewsData.io uses "results" (not "articles")
        articles = data.get("results", [])

        print(f"  [FETCH] Found {len(articles)} articles for '{topic}'")
        return articles

    except requests.exceptions.Timeout:
        print(f"  [FETCH ERROR] Request timed out for topic: '{topic}'")
        return []

    except requests.exceptions.ConnectionError:
        print(f"  [FETCH ERROR] No internet connection. Cannot fetch: '{topic}'")
        return []

    except requests.exceptions.HTTPError as e:
        status_code = response.status_code
        if status_code in (401, 403):
            print(f"  [FETCH ERROR] Invalid API key.")
            print(f"  [FETCH ERROR] Get a free key at https://newsdata.io")
        elif status_code == 429:
            print(f"  [FETCH ERROR] Rate limit reached. Too many requests.")
        else:
            print(f"  [FETCH ERROR] HTTP {status_code} for topic '{topic}': {e}")
        return []

    except ValueError:
        print(f"  [FETCH ERROR] Invalid JSON response for topic: '{topic}'")
        return []

    except Exception as e:
        print(f"  [FETCH ERROR] Unexpected error for topic '{topic}': {e}")
        return []


# =============================================================
# STEP 3: PROCESS AND SAVE ARTICLES
# =============================================================

def process_and_save_articles(raw_articles):
    """
    Process a list of raw API articles and save them to MongoDB.

    For each raw article:
      1. Extract fields using .get() (safe — no KeyError if field missing)
      2. Categorize using categorize_article()
      3. Create a clean document using create_news_article() from models.py
      4. Save to MongoDB using save_news_article() from database.py

    Parameters:
      raw_articles - List of raw article dicts from NewsAPI

    Returns:
      A dictionary with counts:
        {"saved": N, "duplicates": N, "skipped": N, "errors": N}
    """
    # Counters to track what happened to each article
    counts = {
        "saved": 0,        # successfully inserted into MongoDB
        "duplicates": 0,   # already existed (URL matched)
        "skipped": 0,      # missing required fields (no title or URL)
        "errors": 0        # unexpected errors
    }

    for raw in raw_articles:
        try:
            # --- Extract fields from the raw NewsData.io article dict ---
            # IMPORTANT: NewsData.io uses different field names than NewsAPI/GNews:
            #   "link"        instead of "url"
            #   "pubDate"     instead of "publishedAt"
            #   "source_name" instead of source.name
            #   "creator"     is a LIST like ["John Smith"] or None

            title = raw.get("title")
            url   = raw.get("link")    # NewsData.io uses "link" for the URL

            # Skip articles with no title or no URL
            if not title or not url:
                counts["skipped"] += 1
                continue

            # Skip removed/invalid articles
            if title == "[Removed]":
                counts["skipped"] += 1
                continue

            description  = raw.get("description")
            published_at = raw.get("pubDate")       # "2026-10-18 06:00:00"
            source       = raw.get("source_name")   # direct string field

            # "creator" is a list in NewsData.io: ["John Smith"] or None
            creator_list = raw.get("creator")
            if isinstance(creator_list, list) and len(creator_list) > 0:
                author = creator_list[0]   # take the first author name
            else:
                author = None

            # --- Categorize the article ---
            category = categorize_article(
                title or "",
                description or ""
            )

            # --- Create a clean article document using models.py ---
            article = create_news_article(
                title=title,
                url=url,
                description=description,
                source=source,
                author=author,
                published_at=published_at,
                category=category
            )

            # --- Save to MongoDB ---
            # save_news_article() returns {"saved": True/False, "reason": "..."}
            result = save_news_article(article)

            if result["saved"]:
                counts["saved"] += 1
            elif result["reason"] == "duplicate":
                counts["duplicates"] += 1
            else:
                counts["errors"] += 1

        except Exception as e:
            # If one article fails, log it and continue with the rest
            counts["errors"] += 1
            print(f"  [PROCESS ERROR] Failed to process article: {e}")
            continue

    return counts


# =============================================================
# STEP 4: COLLECT ALL NEWS (main pipeline function)
# =============================================================

def collect_all_news():
    """
    Run the complete news collection pipeline.

    This is the main function called by:
      - scheduler.py  (every morning at 6:00 AM)
      - manually      (python news_service.py)
      - briefing_service.py (if needed)

    Steps:
      1. Loop through all NEWS_TOPICS from config
      2. Fetch articles for each topic
      3. Process and save articles
      4. Wait 1 second between topics (API rate limiting)
      5. Return a summary of what was collected

    Returns:
      A summary dictionary:
        {
          "total_saved": N,
          "total_duplicates": N,
          "total_skipped": N,
          "total_errors": N,
          "topics_processed": N,
          "timestamp": "2026-10-18T06:05:00"
        }
    """
    print()
    print("=" * 60)
    print("  STARTING NEWS COLLECTION")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 60)

    # Check API key before starting — fail early with a clear message
    if not config["NEWS_API_KEY"] or config["NEWS_API_KEY"] == "your_newsapi_key_here":
        print()
        print("  [ERROR] NEWS_API_KEY is not set in your .env file.")
        print("  Get a free key instantly from https://newsdata.io")
        print("  Then add it to .env: NEWS_API_KEY=pub_your_key_here")
        print()
        return {
            "total_saved": 0, "total_duplicates": 0,
            "total_skipped": 0, "total_errors": 1,
            "topics_processed": 0,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        }

    # Overall totals across all topics
    total_saved = 0
    total_duplicates = 0
    total_skipped = 0
    total_errors = 0
    topics_processed = 0

    # Loop through each search topic defined in config.py
    for topic in config["NEWS_TOPICS"]:

        # Fetch raw articles from NewsAPI for this topic
        raw_articles = fetch_news_from_api(topic)

        if not raw_articles:
            # fetch_news_from_api() already printed the error
            continue

        # Process and save the articles
        counts = process_and_save_articles(raw_articles)

        # Add to overall totals
        total_saved += counts["saved"]
        total_duplicates += counts["duplicates"]
        total_skipped += counts["skipped"]
        total_errors += counts["errors"]
        topics_processed += 1

        # Print per-topic summary
        print(
            f"  [TOPIC] '{topic}': "
            f"saved={counts['saved']}, "
            f"duplicates={counts['duplicates']}, "
            f"skipped={counts['skipped']}"
        )

        # Wait 1 second between API calls
        # Free tier APIs have rate limits (requests per minute)
        # This prevents hitting the limit when we have many topics
        time.sleep(1)

    # Print final summary
    print()
    print("=" * 60)
    print("  NEWS COLLECTION COMPLETE")
    print(f"  New articles saved : {total_saved}")
    print(f"  Duplicates skipped : {total_duplicates}")
    print(f"  Invalid skipped    : {total_skipped}")
    print(f"  Errors             : {total_errors}")
    print(f"  Topics processed   : {topics_processed}/{len(config['NEWS_TOPICS'])}")
    print("=" * 60)
    print()

    return {
        "total_saved": total_saved,
        "total_duplicates": total_duplicates,
        "total_skipped": total_skipped,
        "total_errors": total_errors,
        "topics_processed": topics_processed,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    }


# =============================================================
# GET TODAY'S NEWS FROM MONGODB
# =============================================================

def get_todays_news():
    """
    Retrieve all articles collected today from MongoDB.

    Used by briefing_service.py to generate the daily briefing.

    Returns:
      A list of article dictionaries from the 'news' collection
      collected within the last 24 hours.
    """
    from datetime import timedelta

    try:
        col = get_news_collection()

        # Calculate "24 hours ago" as a datetime
        twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)

        # MongoDB query: find all documents where collected_at >= 24 hours ago
        # This uses a comparison operator: $gte means "greater than or equal to"
        query = {
            "collected_at": {"$gte": twenty_four_hours_ago}
        }

        # .find() returns a cursor (like a lazy list)
        # We convert to a regular list with list()
        # .sort() orders by published_at newest first
        articles = list(
            col.find(query).sort("published_at", -1)
        )

        print(f"[NEWS] Found {len(articles)} articles from the last 24 hours")
        return articles

    except Exception as e:
        print(f"[NEWS ERROR] Could not retrieve today's news: {e}")
        return []


def get_news_by_category(category):
    """
    Retrieve articles for a specific category from MongoDB.
    Used by the REST API: GET /news/category/<category>

    Parameters:
      category - Category name string (e.g., "AI")

    Returns:
      List of article dicts, newest first, max 20
    """
    try:
        col = get_news_collection()

        # Query: find documents where category field matches exactly
        articles = list(
            col.find({"category": category})
               .sort("published_at", -1)
               .limit(20)
        )

        return articles

    except Exception as e:
        print(f"[NEWS ERROR] Could not get news for category '{category}': {e}")
        return []


def search_news(keyword):
    """
    Search articles by keyword in title, description, or category.
    Used by the REST API: GET /news/search?keyword=python

    Parameters:
      keyword - Search term string

    Returns:
      List of matching article dicts, newest first, max 20
    """
    try:
        col = get_news_collection()

        # MongoDB $regex operator for pattern matching
        # "i" option makes it case-insensitive
        # This searches across three fields using $or
        query = {
            "$or": [
                {"title":       {"$regex": keyword, "$options": "i"}},
                {"description": {"$regex": keyword, "$options": "i"}},
                {"category":    {"$regex": keyword, "$options": "i"}},
            ]
        }

        articles = list(
            col.find(query)
               .sort("published_at", -1)
               .limit(20)
        )

        return articles

    except Exception as e:
        print(f"[NEWS ERROR] Search failed for keyword '{keyword}': {e}")
        return []


# =============================================================
# MANUAL RUN — test this file directly
# =============================================================

# This block only runs when you execute: python news_service.py
# It does NOT run when news_service.py is imported by another file
# This is what "if __name__ == '__main__'" means in Python

if __name__ == "__main__":
    print("Running news_service.py manually...")
    print("This will fetch real news and store it in MongoDB.")
    print()

    # Run the full pipeline
    summary = collect_all_news()

    print()
    print("Summary:", summary)

    # Show how many articles are now in MongoDB
    print()
    articles = get_todays_news()
    print(f"Total articles in MongoDB from last 24h: {len(articles)}")

    if articles:
        print()
        print("Sample article stored:")
        sample = articles[0]
        print(f"  Title    : {sample.get('title')}")
        print(f"  Category : {sample.get('category')}")
        print(f"  Source   : {sample.get('source')}")
        print(f"  URL      : {sample.get('url')}")
