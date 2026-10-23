# =============================================================
# models.py — Data structure templates for MongoDB documents
#
# WHAT THIS FILE DOES:
#   Provides functions that take raw, messy API data and return
#   clean, consistent Python dictionaries ready for MongoDB.
#
# WHY THIS MATTERS:
#   News APIs return inconsistent data — some fields may be
#   None, null, empty, or missing entirely. These functions
#   ensure every document stored in MongoDB has the same
#   fields and sensible default values.
#
# HOW OTHER FILES USE IT:
#   from models import create_news_article, create_daily_briefing
#   article = create_news_article(title="GPT-5 released", ...)
# =============================================================

from datetime import datetime, timezone   # Built-in Python module for dates/times
from config import config                 # For DEFAULT_CATEGORY


# =============================================================
# HELPER FUNCTION
# =============================================================

def clean_text(value, default=""):
    """
    Clean a text value from an API response.

    API responses often return:
      - None           (Python null)
      - "null"         (the string "null")
      - "  spaces  "  (extra whitespace)
      - ""             (empty string)

    This function handles all those cases and returns a clean
    string, or the default value if nothing useful is present.

    Parameters:
      value   - the raw value from the API
      default - what to return if value is empty/None (default: "")

    Returns:
      A clean string
    """
    # Check if the value is None (Python null)
    if value is None:
        return default

    # Make sure it's actually a string before calling string methods
    # isinstance() checks if a variable is a certain type
    if not isinstance(value, str):
        # Try to convert to string (e.g., if a number was passed)
        value = str(value)

    # .strip() removes leading and trailing whitespace
    value = value.strip()

    # Check for the literal string "null" or "None" — some APIs send these
    if value.lower() in ("null", "none", ""):
        return default

    return value


def get_current_utc_time():
    """
    Return the current date and time in UTC timezone.

    UTC (Coordinated Universal Time) is the standard for storing
    timestamps in databases — it avoids timezone confusion.
    We always store in UTC and convert to local time when displaying.

    Returns:
      datetime object with timezone info set to UTC
    """
    # timezone.utc ensures the datetime is timezone-aware
    # Without it, datetime.now() returns a "naive" datetime
    # that has no timezone info — which causes comparison bugs
    return datetime.now(timezone.utc)


# =============================================================
# NEWS ARTICLE MODEL
# =============================================================

def create_news_article(
    title,
    url,
    description=None,
    source=None,
    author=None,
    published_at=None,
    category=None
):
    """
    Create a clean, consistent news article dictionary for MongoDB.

    This is the template for every document in the 'news' collection.
    It accepts raw values from the API and returns a clean dictionary.

    Parameters:
      title        - Article headline (required)
      url          - Article URL (required — used as unique identifier)
      description  - Short summary of the article
      source       - News outlet name (e.g., "TechCrunch")
      author       - Author name if available
      published_at - When the article was published (datetime or string)
      category     - Technology category (set by categorization logic)

    Returns:
      A Python dictionary ready to be inserted into MongoDB

    Example:
      article = create_news_article(
          title="OpenAI releases GPT-5",
          url="https://techcrunch.com/gpt5",
          source="TechCrunch",
          category="AI"
      )
    """

    # --- Clean all incoming values ---
    # We use our clean_text() helper to handle None, whitespace, etc.
    clean_title = clean_text(title, default="No Title")
    clean_url = clean_text(url, default="")
    clean_description = clean_text(description, default="")
    clean_source = clean_text(source, default="Unknown Source")
    clean_author = clean_text(author, default="Unknown")
    clean_category = clean_text(category, default=config["DEFAULT_CATEGORY"])

    # --- Handle the published_at timestamp ---
    # The API sends published_at as a string like "2026-10-18T06:00:00Z"
    # We need to store it as a Python datetime object for MongoDB
    if published_at is None:
        # If no publish date, use the current time as a fallback
        clean_published_at = get_current_utc_time()

    elif isinstance(published_at, datetime):
        # Already a datetime object — use it directly
        clean_published_at = published_at

    elif isinstance(published_at, str):
        # It's a string — try to parse it into a datetime object
        try:
            # NewsAPI/GNews sends: "2026-10-18T06:00:00Z"
            # NewsData.io sends:   "2026-10-18 06:00:00"
            # We handle both formats below

            if "T" in published_at:
                # ISO 8601 format with T separator
                date_string = published_at.replace("Z", "+00:00")
                clean_published_at = datetime.fromisoformat(date_string)
            else:
                # NewsData.io format: "2026-10-18 06:00:00"
                clean_published_at = datetime.strptime(
                    published_at, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            # If parsing fails, use current time as fallback
            clean_published_at = get_current_utc_time()
    else:
        clean_published_at = get_current_utc_time()

    # --- Build and return the document dictionary ---
    # This is exactly what will be stored in MongoDB
    return {
        # title: The article headline
        "title": clean_title,

        # description: Short summary (may be empty for some sources)
        "description": clean_description,

        # source: Name of the news outlet
        "source": clean_source,

        # author: Writer's name ("Unknown" if not provided)
        "author": clean_author,

        # url: Unique identifier — the unique index in MongoDB is on this field
        "url": clean_url,

        # category: Which of our 10 tech categories this belongs to
        "category": clean_category,

        # published_at: When the article was originally published
        "published_at": clean_published_at,

        # collected_at: When OUR app fetched and stored this article
        # This is always "now" — useful for debugging and auditing
        "collected_at": get_current_utc_time(),
    }


# =============================================================
# DAILY BRIEFING MODEL
# =============================================================

def create_daily_briefing(
    briefing_date,
    top_news,
    total_news,
    categories_count,
    learning_of_the_day="",
    career_opportunity=""
):
    """
    Create a clean daily briefing dictionary for MongoDB.

    This is the template for every document in the
    'daily_briefings' collection. One document per day.

    Parameters:
      briefing_date       - The date this briefing is for (datetime.date or string)
      top_news            - List of top article dicts (one per category)
      total_news          - Total number of articles collected today (integer)
      categories_count    - Dict of {category: article_count} for today
      learning_of_the_day - Suggested learning topic (string)
      career_opportunity  - Career insight based on today's news (string)

    Returns:
      A Python dictionary ready to be inserted into MongoDB

    Example:
      briefing = create_daily_briefing(
          briefing_date="2026-10-18",
          top_news=[...],
          total_news=47,
          categories_count={"AI": 12, "Cybersecurity": 5}
      )
    """

    # --- Handle the briefing_date ---
    # Store it as a string in "YYYY-MM-DD" format for easy lookup
    if isinstance(briefing_date, str):
        clean_date = briefing_date
    else:
        # If it's a date/datetime object, convert to string
        clean_date = briefing_date.strftime("%Y-%m-%d")

    # --- Validate top_news ---
    # Must be a list — default to empty list if something wrong was passed
    if not isinstance(top_news, list):
        top_news = []

    # --- Validate categories_count ---
    # Must be a dict — default to empty dict
    if not isinstance(categories_count, dict):
        categories_count = {}

    # --- Validate total_news ---
    # Must be an integer
    if not isinstance(total_news, int):
        try:
            total_news = int(total_news)
        except (ValueError, TypeError):
            total_news = 0

    # --- Build and return the briefing document ---
    return {
        # briefing_date: "YYYY-MM-DD" — the unique index is on this field
        # Only one briefing can exist per date
        "briefing_date": clean_date,

        # generated_at: When the briefing was created (UTC timestamp)
        "generated_at": get_current_utc_time(),

        # total_news: How many articles were collected today
        "total_news": total_news,

        # categories: How many articles per category today
        # e.g., {"AI": 12, "Quantum Computing": 3, "Cybersecurity": 8}
        "categories": categories_count,

        # top_news: List of featured articles (one per category)
        # Each item is a dict with: category, title, summary, why_it_matters, source, url
        "top_news": top_news,

        # learning_of_the_day: One practical topic suggested for students
        "learning_of_the_day": clean_text(learning_of_the_day),

        # career_opportunity: Skills/roles spotted in today's news
        "career_opportunity": clean_text(career_opportunity),

        # created_at: Identical to generated_at — kept for clarity in Compass
        "created_at": get_current_utc_time(),
    }


# =============================================================
# TOP NEWS ITEM MODEL (used inside daily briefing)
# =============================================================

def create_top_news_item(category, title, summary, why_it_matters, source, url):
    """
    Create one featured news item for the daily briefing.

    This becomes one entry in the top_news list inside the
    daily_briefings document.

    Parameters:
      category       - Technology category (e.g., "AI")
      title          - Article headline
      summary        - 2-3 sentence summary of the article
      why_it_matters - One sentence explaining the significance
      source         - News outlet name
      url            - Original article URL

    Returns:
      A dictionary representing one featured story
    """
    return {
        "category": clean_text(category),
        "title": clean_text(title),
        "summary": clean_text(summary),
        "why_it_matters": clean_text(why_it_matters),
        "source": clean_text(source),
        "url": clean_text(url),
    }
