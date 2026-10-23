# =============================================================
# config.py — Central configuration for the entire application
#
# WHAT THIS FILE DOES:
#   - Reads all settings from the .env file
#   - Makes them available to every other file via simple imports
#
# HOW TO USE IN OTHER FILES:
#   from config import config
#   print(config["MONGO_URI"])
#
# WHY THIS APPROACH:
#   - API keys and secrets stay OUT of the code
#   - Change a setting in .env — it updates everywhere
#   - Safe to share code publicly (GitHub) without exposing secrets
# =============================================================

import os           # Built-in Python module to read environment variables
from dotenv import load_dotenv  # Third-party: reads .env file into os.environ

# load_dotenv() finds the .env file in the current folder
# and loads each KEY=VALUE pair into the environment
load_dotenv()

# =============================================================
# The config dictionary — one place for all settings
#
# os.getenv("KEY") reads a variable from the environment
# os.getenv("KEY", "default") uses "default" if KEY is missing
# int(...) converts the string value to an integer (for port/hour/minute)
# =============================================================

config = {

    # --- News API ---
    "NEWS_API_KEY": os.getenv("NEWS_API_KEY"),

    # --- MongoDB ---
    "MONGO_URI": os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
    "MONGO_DB_NAME": os.getenv("MONGO_DB_NAME", "tech_news"),

    # --- Collection names ---
    # Defined here so they are never misspelled elsewhere
    "NEWS_COLLECTION": "news",
    "BRIEFINGS_COLLECTION": "daily_briefings",

    # --- Flask ---
    "FLASK_PORT": int(os.getenv("FLASK_PORT", "5000")),
    "FLASK_DEBUG": os.getenv("FLASK_DEBUG", "True") == "True",

    # --- Scheduler ---
    "NEWS_SCHEDULE_HOUR": int(os.getenv("NEWS_SCHEDULE_HOUR", "6")),
    "NEWS_SCHEDULE_MINUTE": int(os.getenv("NEWS_SCHEDULE_MINUTE", "0")),

    # --- News API settings ---
    # Topics to search for. Each string becomes a separate API query.
    "NEWS_TOPICS": [
        "artificial intelligence",
        "agentic AI",
        "quantum computing",
        "cloud computing",
        "cybersecurity",
        "programming language",
        "developer tools",
        "tech startup",
        "technology companies",
    ],

    # How many articles to fetch per topic (NewsAPI max is 100 on free tier)
    "NEWS_PAGE_SIZE": 10,

    # Language filter — English articles only
    "NEWS_LANGUAGE": "en",

    # --- Keyword-based category rules ---
    # Format: "Category Name" → [list of keywords to match]
    # Keywords are checked against the article title + description (lowercase)
    # Order matters: more specific categories should come first
    "CATEGORY_KEYWORDS": {
        "Agentic AI": [
            "agentic ai", "ai agent", "autonomous agent", "multi-agent",
            "ai assistant", "autonomous ai", "agent framework"
        ],
        "AI": [
            "artificial intelligence", "machine learning", "deep learning",
            "large language model", "llm", "neural network", "gpt", "chatgpt",
            "gemini", "claude", "openai", "generative ai", "ai model"
        ],
        "Quantum Computing": [
            "quantum", "qubit", "quantum computing", "quantum supremacy",
            "quantum processor", "quantum chip"
        ],
        "Cloud Computing": [
            "aws", "azure", "google cloud", "cloud computing", "serverless",
            "cloud storage", "cloud platform", "cloud service"
        ],
        "Cybersecurity": [
            "cybersecurity", "hacking", "data breach", "ransomware",
            "malware", "vulnerability", "cve", "cyber attack",
            "security flaw", "phishing"
        ],
        "Developer Tools": [
            "vs code", "github", "gitlab", "docker", "devops", "ci/cd",
            "ide", "developer tool", " api ", "sdk", "framework"
        ],
        "Programming": [
            "python", "javascript", "typescript", "rust", "go", "java",
            "programming language", "open source", "compiler", "library"
        ],
        "Startups": [
            "startup", "funding", "series a", "series b", "venture capital",
            "vc funding", "ipo", "unicorn", "seed round", "tech company raises"
        ],
        "Technology Companies": [
            "google", "microsoft", "apple", "meta", "amazon", "nvidia",
            "openai", "anthropic", "tesla", "samsung", "intel"
        ],
    },

    # Default category if no keyword matches
    "DEFAULT_CATEGORY": "Other Technology",

    # --- Trusted news sources (used in article scoring) ---
    "TRUSTED_SOURCES": [
        "techcrunch", "wired", "the verge", "ars technica",
        "bbc technology", "reuters", "bloomberg", "mit technology review",
        "zdnet", "cnet", "engadget", "hacker news"
    ],
}


# =============================================================
# Validation — warn the developer if critical settings are missing
# This runs when config.py is imported anywhere in the project
# =============================================================

def validate_config():
    """
    Check that required settings are present.
    Print a warning (not a crash) so the app can still run in debug mode.
    """
    required_keys = ["NEWS_API_KEY", "MONGO_URI", "MONGO_DB_NAME"]

    for key in required_keys:
        # If the value is None or an empty string, warn the developer
        if not config.get(key):
            print(f"[CONFIG WARNING] Missing required setting: {key}")
            print(f"  → Add {key}=your_value to your .env file")


# Run validation every time this module is loaded
validate_config()
