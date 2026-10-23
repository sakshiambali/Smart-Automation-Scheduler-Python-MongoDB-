# =============================================================
# briefing_service.py — Generate the daily technology briefing
#
# WHAT THIS FILE DOES:
#   1. Fetches today's articles from MongoDB
#   2. Scores each article by importance (0-10 points)
#   3. Selects the best article per category
#   4. Generates the formatted daily briefing text
#   5. Saves the briefing to MongoDB
#   6. Prints the briefing to the terminal
#
# MAIN FUNCTION:
#   run_daily_briefing() — called by scheduler.py every morning
#
# HOW TO TEST MANUALLY:
#   python briefing_service.py
# =============================================================

from datetime import datetime, timezone
from config import config
from models import create_daily_briefing, create_top_news_item
from database import get_briefings_collection
from news_service import get_todays_news


# =============================================================
# PRIORITY KEYWORDS FOR SCORING
# These keywords boost an article's score when found in the title
# Higher-priority topics get higher scores
# =============================================================

PRIORITY_KEYWORDS = [
    # AI and agents — highest importance for our audience
    "artificial intelligence", "machine learning", "llm", "gpt",
    "chatgpt", "gemini", "openai", "agentic", "ai agent",
    # Quantum
    "quantum", "qubit",
    # Security incidents — always newsworthy
    "ransomware", "data breach", "cyber attack", "vulnerability",
    # Major releases/announcements
    "released", "launched", "announced", "breakthrough",
    # Cloud and infrastructure
    "aws", "azure", "google cloud",
]


# =============================================================
# STEP 1: SCORE ONE ARTICLE
# =============================================================

def score_article(article):
    """
    Calculate an importance score (0-10) for one article.

    Scoring rules:
      +3  title contains a priority keyword
      +2  published within the last 24 hours
      +2  source is a trusted outlet
      +1  description is longer than 100 characters
      +1  author is known (not "Unknown")
      +1  title is longer than 40 characters

    Parameters:
      article - A dictionary from MongoDB (one news document)

    Returns:
      An integer score between 0 and 10
    """
    score = 0

    # --- Get fields, defaulting to empty string if missing ---
    title       = (article.get("title") or "").lower()
    description = (article.get("description") or "")
    source      = (article.get("source") or "").lower()
    author      = (article.get("author") or "Unknown")

    # --- Rule 1: Priority keyword in title (+3) ---
    for keyword in PRIORITY_KEYWORDS:
        if keyword in title:
            score += 3
            break   # only award this bonus once, even if multiple keywords match

    # --- Rule 2: Published within last 24 hours (+2) ---
    published_at = article.get("published_at")
    if published_at:
        now = datetime.now(timezone.utc)

        # Handle both timezone-aware and timezone-naive datetimes
        # MongoDB may return naive datetimes depending on how they were stored
        if hasattr(published_at, "tzinfo") and published_at.tzinfo is None:
            # Naive datetime — assume it's UTC
            from datetime import timedelta
            age = now.replace(tzinfo=None) - published_at
        else:
            try:
                age = now - published_at
            except TypeError:
                age = None

        # If published within 24 hours, award +2
        if age is not None:
            from datetime import timedelta
            if age.total_seconds() < 86400:   # 86400 seconds = 24 hours
                score += 2

    # --- Rule 3: Trusted source (+2) ---
    for trusted in config["TRUSTED_SOURCES"]:
        if trusted in source:
            score += 2
            break

    # --- Rule 4: Description longer than 100 characters (+1) ---
    if len(description) > 100:
        score += 1

    # --- Rule 5: Author is known (+1) ---
    if author and author.lower() not in ("unknown", "", "none"):
        score += 1

    # --- Rule 6: Title longer than 40 characters (+1) ---
    if len(title) > 40:
        score += 1

    return score


# =============================================================
# STEP 2: SELECT BEST ARTICLE PER CATEGORY
# =============================================================

def select_top_news(articles):
    """
    From all articles, select the highest-scoring one per category.

    Algorithm:
      1. Group articles by category into a dictionary
      2. For each category, score every article
      3. Pick the article with the highest score
      4. Return one article per category

    Parameters:
      articles - List of article dicts from MongoDB

    Returns:
      A dictionary: { "AI": best_article, "Cybersecurity": best_article, ... }
    """
    # Step 1: Group articles by category
    # Result: { "AI": [art1, art2, ...], "Cloud": [art3, art4, ...] }
    grouped = {}

    for article in articles:
        category = article.get("category", config["DEFAULT_CATEGORY"])

        # If this category hasn't been seen yet, create a new list for it
        if category not in grouped:
            grouped[category] = []

        grouped[category].append(article)

    print(f"[BRIEFING] Categories found: {list(grouped.keys())}")
    for cat, arts in grouped.items():
        print(f"  {cat}: {len(arts)} articles")

    # Step 2: For each category, find the highest-scoring article
    top_news = {}

    for category, category_articles in grouped.items():

        # Score every article in this category
        # sorted() returns a new list sorted by the key function
        # key=score_article means: sort by the score each article gets
        # reverse=True means: highest score first
        scored = sorted(
            category_articles,
            key=score_article,
            reverse=True
        )

        # The first item after sorting is the highest-scoring article
        best_article = scored[0]
        best_score = score_article(best_article)

        top_news[category] = best_article

        print(
            f"  [SELECTED] {category}: "
            f"'{best_article.get('title', '')[:50]}...' "
            f"(score: {best_score})"
        )

    return top_news


# =============================================================
# STEP 3: BUILD LEARNING AND CAREER SECTIONS
# =============================================================

def get_learning_suggestion(top_news):
    """
    Suggest one learning topic based on today's top news categories.

    This is a simple lookup — if "AI" is in today's news, suggest
    an AI learning topic. We use a dictionary to map categories
    to suggested topics.

    Parameters:
      top_news - dict of {category: article}

    Returns:
      A string with the learning suggestion
    """
    # Map each category to a relevant learning topic
    # We check categories in priority order
    learning_map = {
        "Agentic AI": (
            "Explore how AI agents work using LangChain or AutoGen. "
            "Start with: 'What is an AI agent?' on YouTube."
        ),
        "AI": (
            "Learn how Large Language Models (LLMs) work. "
            "Try building a simple chatbot with the OpenAI Python library."
        ),
        "Quantum Computing": (
            "Read about how qubits differ from classical bits. "
            "IBM Quantum has free beginner courses at learning.quantum.ibm.com"
        ),
        "Cybersecurity": (
            "Learn about OWASP Top 10 — the most critical web security risks. "
            "Free resource: owasp.org/www-project-top-ten"
        ),
        "Cloud Computing": (
            "Understand the difference between IaaS, PaaS, and SaaS. "
            "AWS, Azure, and Google Cloud all offer free tier accounts."
        ),
        "Developer Tools": (
            "Learn Git branching strategies — feature branches, pull requests. "
            "Try 'Learn Git Branching' at learngitbranching.js.org"
        ),
        "Programming": (
            "Practice data structures in Python — lists, dicts, sets. "
            "Try solving problems on LeetCode (Easy level) today."
        ),
        "Startups": (
            "Read about how startups raise funding — Seed, Series A, B, C rounds. "
            "Y Combinator's Startup School (startupschool.org) is free."
        ),
        "Technology Companies": (
            "Study how big tech companies are structured. "
            "Read about product management and engineering org design."
        ),
    }

    # Check which categories are in today's top news (in priority order)
    priority_order = [
        "Agentic AI", "AI", "Quantum Computing", "Cybersecurity",
        "Cloud Computing", "Developer Tools", "Programming",
        "Startups", "Technology Companies"
    ]

    for category in priority_order:
        if category in top_news:
            return learning_map.get(category, "Explore today's top technology topics.")

    return "Review your Python fundamentals — functions, loops, and dictionaries."


def get_career_opportunity(top_news):
    """
    Identify career opportunities based on today's top news.

    Parameters:
      top_news - dict of {category: article}

    Returns:
      A string describing relevant skills and roles
    """
    # Collect the categories present today
    categories_today = list(top_news.keys())

    # Map categories to career insights
    career_map = {
        "Agentic AI":           "AI Engineer, Prompt Engineer, LLM Application Developer",
        "AI":                   "Machine Learning Engineer, AI Product Manager, Data Scientist",
        "Quantum Computing":    "Quantum Software Developer, Quantum Research Scientist",
        "Cybersecurity":        "Security Engineer, Penetration Tester, SOC Analyst",
        "Cloud Computing":      "Cloud Architect, DevOps Engineer, Site Reliability Engineer",
        "Developer Tools":      "DevOps Engineer, Platform Engineer, Developer Advocate",
        "Programming":          "Software Developer, Backend Engineer, Open Source Contributor",
        "Startups":             "Full-Stack Developer, CTO, Technical Co-founder",
        "Technology Companies": "Software Engineer, Technical Program Manager, Product Manager",
    }

    # Build a list of relevant roles based on today's categories
    roles = []
    for cat in categories_today:
        if cat in career_map:
            roles.append(career_map[cat])

    if not roles:
        return "Software Developer, Backend Engineer, Python Developer"

    # Join all role suggestions, remove duplicates
    all_roles = []
    for role_string in roles:
        for role in role_string.split(", "):
            if role not in all_roles:
                all_roles.append(role)

    # Return the top 5 most relevant roles
    return ", ".join(all_roles[:5])


# =============================================================
# STEP 4: FORMAT THE BRIEFING TEXT
# =============================================================

def format_briefing_text(top_news, briefing_date):
    """
    Generate the formatted daily briefing as a printable string.

    This function builds the text that:
      - Gets printed to the terminal
      - Gets stored in MongoDB
      - Can later be sent by email or shown in a web page

    Parameters:
      top_news      - dict of {category: article}
      briefing_date - "YYYY-MM-DD" string

    Returns:
      The complete briefing as a multi-line string
    """
    lines = []   # We build the text as a list of lines, then join at the end

    # --- Header ---
    lines.append("=" * 62)
    lines.append("       DAILY GLOBAL TECH BRIEFING")
    lines.append(f"       Date: {briefing_date}")
    lines.append(f"       Generated: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    lines.append("=" * 62)
    lines.append("")

    # --- Category sections ---
    # Display categories in a consistent order
    display_order = [
        "AI", "Agentic AI", "Quantum Computing", "Cloud Computing",
        "Cybersecurity", "Programming", "Developer Tools",
        "Startups", "Technology Companies", "Other Technology"
    ]

    section_number = 1

    for category in display_order:

        # Skip categories that have no articles today
        if category not in top_news:
            continue

        article = top_news[category]
        title   = article.get("title", "No title available")
        desc    = article.get("description", "")
        source  = article.get("source", "Unknown")
        url     = article.get("url", "")

        # --- Section header ---
        lines.append(f"{section_number}. {category.upper()}")
        lines.append("-" * 40)

        # --- Headline ---
        lines.append(f"   Headline: {title}")
        lines.append("")

        # --- Summary ---
        # Use description if available, otherwise note it's unavailable
        if desc and len(desc) > 20:
            # Wrap long descriptions for readability
            # Split into roughly 55-character chunks
            words = desc.split()
            current_line = "   Summary: "
            for word in words:
                if len(current_line) + len(word) + 1 > 65:
                    lines.append(current_line)
                    current_line = "            " + word + " "
                else:
                    current_line += word + " "
            if current_line.strip():
                lines.append(current_line)
        else:
            lines.append("   Summary: Full article at source link below.")

        lines.append("")

        # --- Why it matters ---
        # A simple, consistent statement per category
        why_map = {
            "AI":                   "AI advances directly affect software development and job markets.",
            "Agentic AI":           "Autonomous AI agents are changing how software tasks are automated.",
            "Quantum Computing":    "Quantum breakthroughs will impact encryption and scientific computing.",
            "Cloud Computing":      "Cloud decisions affect every modern application and startup.",
            "Cybersecurity":        "Security incidents affect businesses and users worldwide.",
            "Programming":          "Language and tool changes affect developer workflows and hiring.",
            "Developer Tools":      "Better tools mean faster, more reliable software development.",
            "Startups":             "Startup activity signals where technology investment is flowing.",
            "Technology Companies": "Decisions by major tech companies shape the entire industry.",
            "Other Technology":     "Emerging technology trends create new opportunities and challenges.",
        }
        why = why_map.get(category, "This development may impact the technology industry.")
        lines.append(f"   Why it matters: {why}")
        lines.append("")

        # --- Source ---
        lines.append(f"   Source: {source}")
        if url:
            lines.append(f"   Link:   {url}")
        lines.append("")

        section_number += 1

    # --- Learning of the Day ---
    lines.append("=" * 62)
    lines.append("   LEARNING OF THE DAY")
    lines.append("-" * 40)
    learning = get_learning_suggestion(top_news)
    # Word-wrap the learning text
    words = learning.split()
    current_line = "   "
    for word in words:
        if len(current_line) + len(word) + 1 > 65:
            lines.append(current_line)
            current_line = "   " + word + " "
        else:
            current_line += word + " "
    if current_line.strip():
        lines.append(current_line)
    lines.append("")

    # --- Career Opportunity ---
    lines.append("   CAREER OPPORTUNITY")
    lines.append("-" * 40)
    careers = get_career_opportunity(top_news)
    lines.append(f"   In-demand roles based on today's news:")
    lines.append(f"   {careers}")
    lines.append("")
    lines.append("=" * 62)

    # Join all lines into one string with newline characters
    return "\n".join(lines)


# =============================================================
# STEP 5: SAVE BRIEFING TO MONGODB
# =============================================================

def save_briefing(briefing_data):
    """
    Save the daily briefing document to MongoDB.

    Uses upsert — if a briefing for today already exists,
    update it instead of inserting a duplicate.

    Parameters:
      briefing_data - dict created by create_daily_briefing()

    Returns:
      True if saved successfully, False if error
    """
    from pymongo import ASCENDING

    try:
        col = get_briefings_collection()

        # upsert = True means:
        #   - If a document matching the filter exists → UPDATE it
        #   - If no document matches → INSERT it
        # This prevents duplicate briefings if run multiple times in a day
        result = col.update_one(
            {"briefing_date": briefing_data["briefing_date"]},  # filter
            {"$set": briefing_data},                             # update
            upsert=True                                          # insert if not found
        )

        if result.upserted_id:
            print(f"[BRIEFING] New briefing saved for {briefing_data['briefing_date']}")
        else:
            print(f"[BRIEFING] Briefing updated for {briefing_data['briefing_date']}")

        return True

    except Exception as e:
        print(f"[BRIEFING ERROR] Could not save briefing: {e}")
        return False


# =============================================================
# MAIN FUNCTION: RUN THE FULL BRIEFING PIPELINE
# =============================================================

def run_daily_briefing():
    """
    Run the complete briefing generation pipeline.

    Called by:
      - scheduler.py  (automatically every morning)
      - manually      (python briefing_service.py)

    Steps:
      1. Get today's date
      2. Fetch today's articles from MongoDB
      3. Score and select best article per category
      4. Format the briefing text
      5. Build structured briefing data
      6. Save to MongoDB
      7. Print to terminal

    Returns:
      The briefing text string, or None if no articles found
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print()
    print("=" * 62)
    print("  GENERATING DAILY BRIEFING")
    print(f"  Date: {today}")
    print("=" * 62)

    # --- Step 1: Get today's articles from MongoDB ---
    articles = get_todays_news()

    if not articles:
        print("[BRIEFING] No articles found for today.")
        print("[BRIEFING] Run 'python news_service.py' first to collect news.")
        return None

    print(f"[BRIEFING] Processing {len(articles)} articles...")

    # --- Step 2: Select best article per category ---
    top_news = select_top_news(articles)

    if not top_news:
        print("[BRIEFING] Could not select top news. No categories found.")
        return None

    print(f"[BRIEFING] Selected {len(top_news)} featured articles")

    # --- Step 3: Format the briefing text ---
    briefing_text = format_briefing_text(top_news, today)

    # --- Step 4: Build structured data for MongoDB ---
    # Count articles per category
    category_counts = {}
    for article in articles:
        cat = article.get("category", config["DEFAULT_CATEGORY"])
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Build the top_news list for the MongoDB document
    top_news_list = []
    for category, article in top_news.items():
        item = create_top_news_item(
            category=category,
            title=article.get("title", ""),
            summary=article.get("description", ""),
            why_it_matters=f"Key development in {category}",
            source=article.get("source", "Unknown"),
            url=article.get("url", "")
        )
        top_news_list.append(item)

    # Create the full briefing document using our model
    briefing_doc = create_daily_briefing(
        briefing_date=today,
        top_news=top_news_list,
        total_news=len(articles),
        categories_count=category_counts,
        learning_of_the_day=get_learning_suggestion(top_news),
        career_opportunity=get_career_opportunity(top_news)
    )

    # Add the formatted text to the document
    briefing_doc["briefing_text"] = briefing_text

    # --- Step 5: Save to MongoDB ---
    save_briefing(briefing_doc)

    # --- Step 6: Print to terminal ---
    print()
    print(briefing_text)

    return briefing_text


# =============================================================
# QUERY FUNCTIONS — used by REST API (main.py)
# =============================================================

def get_all_briefings():
    """
    Get all stored daily briefings from MongoDB.
    Used by: GET /briefings
    """
    try:
        col = get_briefings_collection()
        # Return all briefings, newest first, without the full text (too large)
        briefings = list(
            col.find({}, {"briefing_text": 0})
               .sort("briefing_date", -1)
               .limit(30)
        )
        return briefings
    except Exception as e:
        print(f"[BRIEFING ERROR] {e}")
        return []


def get_briefing_by_date(date_string):
    """
    Get a specific day's briefing from MongoDB.
    Used by: GET /briefings/<date>

    Parameters:
      date_string - "YYYY-MM-DD" format string
    """
    try:
        col = get_briefings_collection()
        briefing = col.find_one({"briefing_date": date_string})
        return briefing
    except Exception as e:
        print(f"[BRIEFING ERROR] {e}")
        return None


# =============================================================
# MANUAL RUN
# =============================================================

if __name__ == "__main__":
    print("Running briefing_service.py manually...")
    result = run_daily_briefing()
    if result is None:
        print("\nNo briefing generated. Make sure news has been collected first.")
        print("Run: python news_service.py")
