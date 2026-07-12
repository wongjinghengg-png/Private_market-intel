"""
Email builder — renders the HTML brief and sends via SMTP.
"""

import smtplib
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import (
    CATEGORIES,
    EMAIL_PASSWORD,
    EMAIL_RECIPIENTS,
    EMAIL_SENDER,
    MIN_RELEVANCE,
    NEWS_API_KEY,
    SMTP_PORT,
    SMTP_SERVER,
    ARCHIVE_PATH,
)

TEMPLATE_PATH = Path(__file__).parent / "templates" / "daily_brief.html"


def build_email_html(all_items: list[dict], watchlist: list[dict]) -> str:
    """Render the daily brief HTML from classified items."""
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("daily_brief.html")

    # Group items by company, then by category (filtered by relevance)
    company_items = defaultdict(list)
    for item in all_items:
        if (item.get("category") not in ("Irrelevant", "Unknown")
                and item.get("relevance", 0) >= MIN_RELEVANCE):
            company_items[item["company"]].append(item)

    # Build structured data for template
    companies_data = []
    for co in watchlist:
        name = co["name"]
        items = company_items.get(name, [])

        # Group by category, preserving CATEGORIES order
        cat_groups = []
        items_by_cat = defaultdict(list)
        for it in items:
            items_by_cat[it["category"]].append(it)

        for cat in CATEGORIES:
            if cat in items_by_cat:
                # Sort by relevance desc within category
                sorted_items = sorted(items_by_cat[cat], key=lambda x: x.get("relevance", 1), reverse=True)
                cat_groups.append({"category": cat, "entries": sorted_items})

        companies_data.append({
            "name": name,
            "sector": co.get("sector", ""),
            "item_count": len(items),
            "category_groups": cat_groups,
        })

    # Sort companies: those with items first, then by priority
    companies_data.sort(key=lambda c: (-c["item_count"], 0))

    # Top signals: relevance >= 4 across all companies
    top_signals = [
        item for item in all_items
        if item.get("relevance", 0) >= 4 and item.get("category") not in ("Irrelevant", "Unknown")
    ]
    top_signals.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    top_signals = top_signals[:5]

    total_items = sum(c["item_count"] for c in companies_data)
    companies_with_items = sum(1 for c in companies_data if c["item_count"] > 0)

    html = template.render(
        date=datetime.now().strftime("%B %d, %Y"),
        total_items=total_items,
        company_count=companies_with_items,
        top_signals=top_signals,
        companies=companies_data,
        newsapi_active=bool(NEWS_API_KEY),
        archive_path=ARCHIVE_PATH,
    )

    return html


def send_email(html_body: str, date_str: str = "") -> bool:
    """Send the daily brief email via SMTP."""
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS]):
        print("[WARN] Email credentials not configured. Skipping send.")
        print("       Set EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS in .env")
        return False

    if not date_str:
        date_str = datetime.now().strftime("%b %d, %Y")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Market Intel Brief — {date_str}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(EMAIL_RECIPIENTS)

    # Plain text fallback
    plain = f"Market Intelligence Brief for {date_str}. View this email in an HTML-capable client."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENTS, msg.as_string())
        print(f"[OK] Email sent to {', '.join(EMAIL_RECIPIENTS)}")
        return True
    except Exception as e:
        print(f"[ERROR] Email send failed: {e}")
        return False
