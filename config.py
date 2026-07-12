"""
Configuration — watchlist, categories, API keys, and settings.
Edit WATCHLIST below to add/remove companies.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ─────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# ── Email Settings ───────────────────────────────────────────────────
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENTS = [
    e.strip() for e in os.getenv("EMAIL_RECIPIENTS", "").split(",") if e.strip()
]
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# ── File Paths ───────────────────────────────────────────────────────
ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "data/archive.xlsx")
BRIEF_OUTPUT_DIR = os.getenv("BRIEF_OUTPUT_DIR", "data/briefs")

# ── Scraping Settings ───────────────────────────────────────────────
MAX_ARTICLES_PER_COMPANY = 1000
FALLBACK_START_DATE = "2026-02-01"  # If no archive exists, scrape from this date
REQUEST_DELAY_SECONDS = 1           # Polite delay between requests
MIN_RELEVANCE = 4                   # Only include items scored 4+ in brief and archive

# ── Source Credibility Tiers ────────────────────────────────────────
# When duplicate signals exist, the source with the highest tier wins.
# Tier 1 = most credible (original reporting), Tier 4 = least (aggregators).
# Sources not listed default to tier 3.
SOURCE_CREDIBILITY = {
    # Tier 1 — Wire services, major financial press, company primary
    1: [
        "Reuters", "Bloomberg", "Associated Press", "AP News",
        "Wall Street Journal", "WSJ", "Financial Times", "FT",
        "SEC Filing", "SEC EDGAR",
        # Company primary sources
        "Anthropic Blog", "OpenAI Blog", "Stripe Blog", "SpaceX",
        "Anduril Blog", "Company Blog", "Company Press Release",
    ],
    # Tier 2 — Quality tech/business journalism
    2: [
        "The Information", "TechCrunch", "CNBC", "Business Insider",
        "Axios", "The Verge", "Wired", "Ars Technica",
        "VentureBeat", "Forbes", "Fortune",
        "Defense One", "SpaceNews", "MIT Technology Review",
        "Semafor", "Politico", "New York Times", "Washington Post",
    ],
    # Tier 3 — Industry / niche (default tier for unlisted sources)
    3: [
        "CoinDesk", "The Block", "Decrypt",
        "Caplight", "PitchBook", "Crunchbase News",
        "GeekWire", "Protocol", "Rest of World",
    ],
    # Tier 4 — Aggregators, blogs, social
    4: [
        "Yahoo Finance", "Google News", "MSN", "Benzinga",
        "Seeking Alpha", "Motley Fool", "MarketWatch",
        "Reddit", "Twitter", "X", "Hacker News",
    ],
}

# Build a flat lookup: source_name -> tier
SOURCE_TIER_LOOKUP = {}
for tier, sources in SOURCE_CREDIBILITY.items():
    for source in sources:
        SOURCE_TIER_LOOKUP[source.lower()] = tier
DEFAULT_SOURCE_TIER = 3

# ── Source tier acceptance toggle ───────────────────────────────────
# Only accept signals whose source tier is at least this credible (tier <= value).
# Lower tier number = more credible. Turn the dial to control what reaches the brief:
#   1 = wire services / major financial press / company primary only
#   2 = + quality tech & business journalism (The Information, TechCrunch, CNBC, …)
#   3 = + niche / unlisted outlets (unknown sources default to tier 3)   [current]
#   4 = accept everything, including aggregators & social (Yahoo, Reddit, X, …)
# Unlisted sources are treated as DEFAULT_SOURCE_TIER (3), so 3 keeps them while
# dropping tier-4 aggregators; set to 4 to accept those too, or 2 to tighten.
MAX_SOURCE_TIER = 3

# ── Classification Categories ───────────────────────────────────────
CATEGORIES = [
    "Fundraise / IPO",
    "Acquisitions / Merger",
    "Valuation Updates",
    "Capital Markets / Financial Milestones",
    "Company Timeline",
    "New Management",
    "High Impact New Partnerships / Contracts",
    "Financial / Infrastructure Metrics / Milestone",
    "Corporate Structuring",
    "Government, Regulatory & Legal Actions",
]

# ── Industry Sectors (for industry news grouping) ───────────────────
INDUSTRY_SECTORS = [
    "AI & Machine Learning",
    "Defense Tech & Aerospace",
    "Fintech & Crypto",
    "Robotics & Hardware",
    "Energy & Nuclear",
    "Social & Gaming",
]

# ── Company Watchlist ───────────────────────────────────────────────
# Each entry: name, aliases (for broader search), sector, priority (1-3).
# All names below are PRIVATE companies. Public names are intentionally excluded;
# public companies surface only via a watchlist name's private->public dealing.
WATCHLIST = [
    # ── AI & Machine Learning ────────────────────────────────────
    {"name": "Anthropic", "aliases": ["Anthropic AI", "Claude AI"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "OpenAI", "aliases": ["Open AI", "ChatGPT"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "xAI", "aliases": ["xAI Corp", "Grok AI"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Databricks", "aliases": ["Databricks Inc"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Anysphere", "aliases": ["Anysphere Inc", "Cursor AI", "Cursor editor"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Perplexity", "aliases": ["Perplexity AI", "Perplexity search"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Mistral AI", "aliases": ["Mistral", "Mistral models"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Groq", "aliases": ["Groq Inc", "Groq LPU"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Lambda", "aliases": ["Lambda Labs", "Lambda GPU cloud"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "World Labs", "aliases": ["World Labs AI", "Fei-Fei Li World Labs"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Manus AI", "aliases": ["Manus", "Manus agent"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Moonshot", "aliases": ["Moonshot AI", "Kimi AI"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "Stargate", "aliases": ["Stargate AI", "Stargate data center", "OpenAI Stargate"], "sector": "AI & Machine Learning", "priority": 1},
    {"name": "AMI Labs", "aliases": ["Advanced Machine Intelligence Labs", "Yann LeCun AMI", "AMI world model"], "sector": "AI & Machine Learning", "priority": 2},
    {"name": "Prometheus", "aliases": ["Project Prometheus", "Prometheus Bezos", "Bezos AI startup"], "sector": "AI & Machine Learning", "priority": 2},

    # ── Defense Tech & Aerospace ─────────────────────────────────
    {"name": "Anduril", "aliases": ["Anduril Industries"], "sector": "Defense Tech & Aerospace", "priority": 1},
    {"name": "Shield AI", "aliases": ["Shield AI Inc", "ShieldAI", "Hivemind autonomy"], "sector": "Defense Tech & Aerospace", "priority": 1},
    {"name": "Saronic", "aliases": ["Saronic Technologies", "Saronic autonomous ships"], "sector": "Defense Tech & Aerospace", "priority": 1},
    {"name": "Skydio", "aliases": ["Skydio", "Skydio drones"], "sector": "Defense Tech & Aerospace", "priority": 1},
    {"name": "Hadrian", "aliases": ["Hadrian Automation", "Hadrian manufacturing"], "sector": "Defense Tech & Aerospace", "priority": 1},
    {"name": "Flock Safety", "aliases": ["Flock Safety", "Flock cameras"], "sector": "Defense Tech & Aerospace", "priority": 1},
    {"name": "Ent AI", "aliases": ["Ent AI", "Ent cybersecurity", "Ent security"], "sector": "Defense Tech & Aerospace", "priority": 2},

    # ── Robotics & Hardware ──────────────────────────────────────
    {"name": "Figure AI", "aliases": ["Figure AI", "Figure robotics", "Figure 02 robot"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "1X Technologies", "aliases": ["1X robotics", "1X NEO robot", "1X Technologies AS"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Apptronik", "aliases": ["Apptronik Inc", "Apollo robot Apptronik"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Agility Robotics", "aliases": ["Agility Robotics", "Digit robot"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Physical Intelligence", "aliases": ["Physical Intelligence", "Physical Intelligence robotics"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Skild AI", "aliases": ["Skild AI", "Skild robot foundation model"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Neuralink", "aliases": ["Neuralink Corp", "Elon Musk Neuralink"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Applied Intuition", "aliases": ["Applied Intuition", "Applied Intuition autonomy"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Wayve", "aliases": ["Wayve", "Wayve autonomous driving"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Einride", "aliases": ["Einride", "Einride autonomous trucks"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Waymo", "aliases": ["Waymo", "Waymo robotaxi"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Tenstorrent", "aliases": ["Tenstorrent", "Tenstorrent AI chips"], "sector": "Robotics & Hardware", "priority": 1},
    {"name": "Tensordyne", "aliases": ["Tensordyne Inc"], "sector": "Robotics & Hardware", "priority": 1},

    # ── Fintech & Crypto ─────────────────────────────────────────
    {"name": "Stripe", "aliases": ["Stripe Inc", "Stripe payments"], "sector": "Fintech & Crypto", "priority": 1},
    {"name": "Tether", "aliases": ["Tether USDT", "Tether stablecoin", "Tether Limited"], "sector": "Fintech & Crypto", "priority": 1},
    {"name": "Kraken", "aliases": ["Kraken crypto", "Kraken exchange", "Payward"], "sector": "Fintech & Crypto", "priority": 1},
    {"name": "Kalshi", "aliases": ["Kalshi Inc", "Kalshi prediction market"], "sector": "Fintech & Crypto", "priority": 1},
    {"name": "Polymarket", "aliases": ["Polymarket", "Polymarket prediction market"], "sector": "Fintech & Crypto", "priority": 1},
    {"name": "Deel", "aliases": ["Deel", "Deel payroll"], "sector": "Fintech & Crypto", "priority": 1},

    # ── Energy & Nuclear ─────────────────────────────────────────
    {"name": "Crusoe Energy", "aliases": ["Crusoe", "Crusoe data centers"], "sector": "Energy & Nuclear", "priority": 1},
    {"name": "Radiant Nuclear", "aliases": ["Radiant Industries", "Radiant Nuclear microreactor"], "sector": "Energy & Nuclear", "priority": 1},

    # ── Social & Gaming ──────────────────────────────────────────
    {"name": "ByteDance", "aliases": ["ByteDance Ltd", "TikTok parent"], "sector": "Social & Gaming", "priority": 1},
    {"name": "Epic Games", "aliases": ["Epic Games Inc", "Unreal Engine", "Fortnite developer"], "sector": "Social & Gaming", "priority": 1},
    {"name": "Discord", "aliases": ["Discord Inc", "Discord app"], "sector": "Social & Gaming", "priority": 1},
]
