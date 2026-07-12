"""
Classifier module — sends scraped articles to Claude for categorization.
Batches articles into groups of 10 to avoid JSON response issues.
Returns structured items with category, summary, and relevance score.
"""

import json
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CATEGORIES

client = Anthropic(api_key=ANTHROPIC_API_KEY)

BATCH_SIZE = 10  # Classify 10 articles per API call to keep responses clean

SYSTEM_PROMPT = f"""You are a private-market research analyst. You will receive a batch of 
news article titles, snippets, and URLs about a specific company.

For EACH article, classify it into exactly ONE of these categories:
{json.dumps(CATEGORIES)}

If the article does not fit any category or is irrelevant noise (e.g. product reviews, 
generic industry commentary with no company-specific signal), classify it as "Irrelevant".

For each article, return:
- category: one of the categories above, or "Irrelevant"
- summary: a crisp 1-2 sentence summary an investor would care about
- relevance: integer 1-5 (5 = major signal, 1 = minor mention)

Respond ONLY with valid JSON — no markdown, no preamble. Use this exact schema:
{{
  "items": [
    {{
      "index": 0,
      "category": "...",
      "summary": "...",
      "relevance": 3
    }}
  ]
}}"""


def classify_articles(company_name: str, articles: list[dict]) -> list[dict]:
    """Classify articles in batches for one company. Returns enriched articles."""
    if not articles:
        return []

    all_enriched = []

    # Process in batches
    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_start:batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Classifying batch {batch_num}/{total_batches} ({len(batch)} articles)...")

        enriched = _classify_batch(company_name, batch)
        all_enriched.extend(enriched)

    return all_enriched


def _classify_batch(company_name: str, articles: list[dict]) -> list[dict]:
    """Classify a single batch of articles via Claude API."""
    # Build the prompt with numbered articles
    lines = [f"Company: {company_name}\n"]
    for i, a in enumerate(articles):
        lines.append(
            f"[{i}] Title: {a['title']}\n"
            f"    Source: {a['source']} | Date: {a['published_date']}\n"
            f"    Snippet: {a['snippet']}\n"
        )

    user_msg = "\n".join(lines)

    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(raw)

        # Merge classification back into article dicts
        enriched = []
        for item in parsed.get("items", []):
            idx = item.get("index", -1)
            if 0 <= idx < len(articles):
                article = articles[idx].copy()
                article["category"] = item.get("category", "Irrelevant")
                article["summary"] = item.get("summary", article["title"])
                article["relevance"] = item.get("relevance", 1)
                enriched.append(article)

        return enriched

    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON parse failed for {company_name}: {e}")
        for a in articles:
            a["category"] = "Unknown"
            a["summary"] = a["title"]
            a["relevance"] = 1
        return articles

    except Exception as e:
        print(f"  [ERROR] Claude API error for {company_name}: {e}")
        for a in articles:
            a["category"] = "Unknown"
            a["summary"] = a["title"]
            a["relevance"] = 1
        return articles
