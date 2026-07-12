#!/usr/bin/env python3
"""
Market Intelligence Engine — Daily Runner + Weekly Recap

Usage:
    python main.py                                   # Full daily run: scrape + classify + email + archive
    python main.py --no-email                        # Skip email, just scrape + archive
    python main.py --dry-run                         # Scrape + classify only, print results
    python main.py --company Stripe                  # Run for a single company only
    python main.py --dedup --dry-run                 # Preview what duplicates would be removed
    python main.py --dedup                           # Remove duplicates from archive (creates backup)
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from config import WATCHLIST, BRIEF_OUTPUT_DIR
from scraper import scrape_company
from classifier import classify_articles
from email_builder import build_email_html, send_email
from archiver import archive_items, get_last_run_dates


def run_daily(args, targets):
    """Standard daily pipeline: scrape → classify → email → archive."""
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"\nMarket Intelligence Engine — {today}")
    print(f"  Scanning {len(targets)} companies")
    print("=" * 60)

    # Get per-company last-scraped dates from archive
    print("Checking archive for last scraped dates...")
    last_dates = get_last_run_dates(targets)

    all_classified = []
    total_raw = 0

    for i, company in enumerate(targets, 1):
        name = company["name"]
        from_date = last_dates.get(name, "2026-04-01")
        print(f"\n[{i}/{len(targets)}] {name} ({company.get('sector', '')})")
        print(f"  Scraping news from {from_date} → {today}...")

        # Scrape
        raw_articles = scrape_company(company, from_date)
        total_raw += len(raw_articles)
        print(f"  Found {len(raw_articles)} articles")

        if not raw_articles:
            continue

        # Classify
        print(f"  Classifying with Claude...")
        classified = classify_articles(name, raw_articles)
        relevant = [a for a in classified if a.get("category", "Irrelevant") != "Irrelevant"]
        all_classified.extend(relevant)
        print(f"  {len(relevant)} relevant signals (of {len(raw_articles)} total)")

    print("\n" + "=" * 60)
    print(f"  Total: {len(all_classified)} relevant signals from {total_raw} articles")
    print("=" * 60)

   # Deduplicate — same method as the weekly (Jaccard 0.30 + same-subject guard,
    # number-normalized, cross-pool, with the relevance >= MIN_RELEVANCE gate)
    if all_classified:
        from weekly_layout import _dedupe
        print("Deduplicating signals (weekly method)...")
        before = len(all_classified)
        all_classified = _dedupe(all_classified)
        removed = before - len(all_classified)
        print(f"  {before} → {len(all_classified)} signals ({removed} duplicates removed)")
    if args.dry_run:
        print("\n[DRY RUN] Skipping email and archive.\n")
        for item in all_classified:
            print(f"  [{item.get('category')}] {item.get('summary', item.get('title', ''))}")
        return

    # Build email
    print("Building daily brief email...")
    html = build_email_html(all_classified, targets)

    if args.save_html or args.no_email:
        brief_dir = Path(BRIEF_OUTPUT_DIR)
        brief_dir.mkdir(parents=True, exist_ok=True)
        html_path = brief_dir / f"brief_{today}.html"
        html_path.write_text(html)
        print(f"[OK] HTML brief saved: {html_path}")

    # Send email
    if not args.no_email:
        print("Sending email...")
        send_email(html, datetime.now().strftime("%b %d, %Y"))
    else:
        print("[SKIP] Email send skipped (--no-email)")

    # Archive
    print("Updating archive...")
    archive_items(all_classified, targets)

    print(f"\n✅ Daily run complete.\n")


def main():
    parser = argparse.ArgumentParser(description="Market Intelligence Engine")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email")
    parser.add_argument("--dry-run", action="store_true", help="Scrape + classify only, no email/archive")
    parser.add_argument("--company", type=str, help="Run for a single company only")
    parser.add_argument("--save-html", action="store_true", help="Save HTML brief to disk")
    parser.add_argument("--weekly-prepare", action="store_true", help="Weekly: build + draft key events, write JSON (no email)")
    parser.add_argument("--weekly-send", action="store_true", help="Weekly: render saved JSON, email, publish (no analysis)")
    parser.add_argument("--dedup", action="store_true", help="Run deduplicator against the full archive")
    parser.add_argument("--days", type=int, default=7, help="Lookback days for weekly recap (default: 7)")
    args = parser.parse_args()

    # ── Dedup Mode ─────────────────────────────────────────────
    if args.dedup:
        from deduplicator import run_standalone
        run_standalone(dry_run=args.dry_run)
        return
        
    # ── Weekly Prepare / Send (hybrid) ─────────────────────────────
    if args.weekly_prepare:
        from weekly_recap import run_weekly_prepare
        run_weekly_prepare(days=args.days)
        return
    if args.weekly_send:
        from weekly_recap import run_weekly_send
        run_weekly_send()
        return

    # ── Daily Mode ─────────────────────────────────────────────────
    if args.company:
        targets = [c for c in WATCHLIST if c["name"].lower() == args.company.lower()]
        if not targets:
            print(f"[ERROR] Company '{args.company}' not found in watchlist.")
            sys.exit(1)
    else:
        targets = WATCHLIST

    run_daily(args, targets)


if __name__ == "__main__":
    main()
