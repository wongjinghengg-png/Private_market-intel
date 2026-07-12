"""
weekly_layout.py — presentation layer for the weekly recap.

Pure rendering + data-shaping (NO API calls, NO network). Given the per-company
`recaps` your pipeline already builds, plus the industry synthesis and the
key-events list, this produces the final email-safe HTML in the locked layout:

    Week in brief  →  Watchlist (by sector)  →  Private Markets — Also Notable
    (non-watchlist private names, by sector)  →  Key Events · Next Week

Entry points:
    data = assemble(recaps, industry_news, key_events, days=7, issue="")
    html = render_weekly(data)

Everything is table-based with inline styles: no flexbox, CSS variables, or JS,
so it survives Gmail / Outlook / Apple Mail and renders fine on GitHub Pages.
"""

import re
from datetime import datetime, timedelta

from jinja2 import Template

from config import (
    SOURCE_TIER_LOOKUP,
    DEFAULT_SOURCE_TIER,
    INDUSTRY_SECTORS,
    MIN_RELEVANCE,
    MAX_SOURCE_TIER,
)

# ── Category → (colour, short label) ─────────────────────────────────
# Keys are the exact strings in config.CATEGORIES.
CATEGORY_STYLE = {
    "Fundraise / IPO":                                ("#059669", "Fundraise / IPO"),
    "Acquisitions / Merger":                          ("#7c3aed", "Acquisition"),
    "Valuation Updates":                              ("#d97706", "Valuation"),
    "Capital Markets / Financial Milestones":         ("#0284c7", "Capital Markets"),
    "Company Timeline":                               ("#475569", "Timeline"),
    "New Management":                                 ("#0891b2", "Management"),
    "High Impact New Partnerships / Contracts":       ("#0d9488", "Partnership / Contract"),
    "Financial / Infrastructure Metrics / Milestone": ("#65a30d", "Metrics / Milestone"),
    "Corporate Structuring":                          ("#4f46e5", "Structuring"),
    "Government, Regulatory & Legal Actions":         ("#e11d48", "Regulatory / Legal"),
}
DEFAULT_STYLE = ("#64748b", "Other")

# ── Sector display names (long config name → short label) ────────────
SECTOR_DISPLAY = {
    "AI & Machine Learning":     "AI & ML",
    "Defense Tech & Aerospace":  "Defense & Aerospace",
    "Fintech & Crypto":          "Fintech & Crypto",
    "Robotics & Hardware":       "Robotics & Hardware",
    "Energy & Nuclear":          "Energy & Nuclear",
    "Social & Gaming":           "Social & Gaming",
}


# ── helpers ──────────────────────────────────────────────────────────

def _style(category):
    return CATEGORY_STYLE.get(category, DEFAULT_STYLE)


def _tier(source):
    return SOURCE_TIER_LOOKUP.get((source or "").lower(), DEFAULT_SOURCE_TIER)


def _date_val(d):
    try:
        return int((d or "")[:10].replace("-", ""))
    except Exception:
        return 0


def _rank_key(sig):
    # relevance DESC, source tier ASC (1 = most credible), recency DESC
    return (
        -int(sig.get("relevance", 0) or 0),
        _tier(sig.get("source")),
        -_date_val(sig.get("published_date") or sig.get("date", "")),
    )


def _fmt_date(d):
    raw = (d or "")[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%b %d").replace(" 0", " ")
    except Exception:
        return raw


def _sector_disp(sector):
    s = (sector or "").strip()
    return SECTOR_DISPLAY.get(s, s)


def flatten_signals(recaps):
    """Pool every signal across all companies into one list (company-agnostic)."""
    out = []
    for r in recaps:
        for s in r.get("signals", []):
            s = dict(s)
            s.setdefault("company", r.get("company"))
            s.setdefault("sector", r.get("sector", ""))
            out.append(s)
    return out


# Tokens ignored when comparing headline similarity
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at",
    "by", "from", "as", "is", "are", "was", "were", "be", "its", "it", "this",
    "that", "after", "over", "into", "amid", "said", "says", "reportedly", "new",
    "up", "out", "off", "per", "than", "plans", "amid",
}


_NUM_UNIT = re.compile(r"\$?\s?(\d+(?:\.\d+)?)\s*(trillion|billion|million|thousand|bn|mn|[bmkt])\b", re.I)
_UNIT_MAP = {"b": "billion", "bn": "billion", "billion": "billion",
             "m": "million", "mn": "million", "million": "million",
             "k": "thousand", "thousand": "thousand",
             "t": "trillion", "trillion": "trillion"}


def _norm_numbers(text):
    """Unify money figures so '$39B', '39 billion', '$39bn' all tokenize the same."""
    def repl(m):
        return f"{m.group(1)} {_UNIT_MAP.get(m.group(2).lower(), m.group(2).lower())}"
    return _NUM_UNIT.sub(repl, text or "")


def _tokenize(text):
    words = re.findall(r"[a-z0-9]+", _norm_numbers(text).lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _same_subject(a, b):
    """True unless a and b are clearly about different companies. Same company, or
    either company named in the other's text (co-mentioned → likely the same story),
    counts as same subject. Prevents low thresholds from merging two different
    companies' look-alike boilerplate stories."""
    ca = (a.get("company") or "").strip().lower()
    cb = (b.get("company") or "").strip().lower()
    if not ca or not cb or ca == cb:
        return True
    ta = ((a.get("headline") or "") + " " + (a.get("summary") or "")).lower()
    tb = ((b.get("headline") or "") + " " + (b.get("summary") or "")).lower()
    return ca in tb or cb in ta


def _dedupe(signals, threshold=0.30, include_summary=True):
    """Quality-gate (relevance >= MIN_RELEVANCE), drop exact repeats, then collapse
    near-identical headlines via Jaccard title similarity — keeping the best-ranked
    (most credible / most relevant / most recent) representative of each cluster.
    A same-subject guard stops different companies' look-alike stories from merging.
    Returns signals already sorted best-first.
    """
    # 1) quality gate — relevance floor AND accepted source tier
    pool = [s for s in signals
            if int(s.get("relevance", 0) or 0) >= MIN_RELEVANCE
            and _tier(s.get("source")) <= MAX_SOURCE_TIER]

    # 2) exact de-dupe on URL (or headline when URL is missing/placeholder)
    seen, exact = set(), []
    for s in pool:
        u = (s.get("url") or "").strip().lower()
        key = u if u and u not in ("#", "n/a", "none") \
            else (s.get("headline") or s.get("summary") or "").strip().lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        exact.append(s)

    # 3) best-first, then greedily keep headlines that aren't near-duplicates.
    #    include_summary=False compares HEADLINES ONLY — used within a single company,
    #    where divergent per-outlet summaries would otherwise dilute the similarity of
    #    the same event below threshold (even identical headlines can slip through).
    exact.sort(key=_rank_key)
    kept, kept_tokens = [], []
    for s in exact:
        text = s.get("headline") or ""
        if include_summary:
            text = text + " " + (s.get("summary") or "")
        toks = _tokenize(text)
        is_dup = False
        for k, kt in zip(kept, kept_tokens):
            if toks and _jaccard(toks, kt) >= threshold and _same_subject(s, k):
                is_dup = True
                break
        if is_dup:
            continue  # near-duplicate of a higher-ranked story already kept
        kept.append(s)
        kept_tokens.append(toks)
    return kept


def rank_and_split(signals, top_n=10, radar_n=10):
    """Return (top10, radar) ranked signals with display fields attached.

    Ranking is signal-level, not company-bound — an industry/regulatory item
    with no single company can rank into the Top 10 on its own merits.
    """
    uniq = _dedupe(signals)
    uniq.sort(key=_rank_key)

    top = uniq[:top_n]
    radar = uniq[top_n:top_n + radar_n]

    for i, s in enumerate(top, 1):
        color, label = _style(s.get("category"))
        s["rank"] = f"{i:02d}"
        s["color"] = color
        s["label"] = label
        s["sector_disp"] = _sector_disp(s.get("sector"))
        s["date_disp"] = _fmt_date(s.get("published_date") or s.get("date", ""))
        s.setdefault("why", "")  # optional investor takeaway, if the pipeline set one

    for i, s in enumerate(radar, top_n + 1):
        color, _ = _style(s.get("category"))
        s["num"] = str(i)
        s["color"] = color
        s["sector_disp"] = _sector_disp(s.get("sector"))

    return top, radar


def build_legend(*signal_lists):
    """Distinct (colour, label) pairs for the categories actually present."""
    seen, legend = set(), []
    for lst in signal_lists:
        for s in lst:
            cat = s.get("category")
            if cat in seen:
                continue
            seen.add(cat)
            color, label = _style(cat)
            legend.append({"color": color, "label": label})
    return legend


def build_sector_groups(recaps, min_signals=1, items_per_company=4):
    """Group active watchlist companies by sector for the Notable Companies section."""
    by_sector = {}  # display sector -> [company dicts]

    for r in recaps:
        # Collapse near-duplicate same-event stories within the company and apply the
        # quality/tier gate. Headline-only comparison (include_summary=False): within one
        # company every pair is same-subject, and divergent per-outlet summaries would
        # otherwise hide same-event repeats (even identical headlines). Returns best-first.
        sigs = _dedupe(r.get("signals", []), include_summary=False)
        if len(sigs) < min_signals:
            continue
        name = r.get("company") or ""
        disp = _sector_disp(r.get("sector"))

        ranked = sigs[:items_per_company]
        items = [{
            "title": s.get("headline") or s.get("summary", ""),
            "source": s.get("source", ""),
            "date": _fmt_date(s.get("published_date") or s.get("date", "")),
            "url": s.get("url", "") or "#",
            "color": _style(s.get("category"))[0],
        } for s in ranked]

        by_sector.setdefault(disp, []).append({
            "name": name,
            "connection": (r.get("connection") or "").strip() or None,
            "links": items,
            "_sc": len(sigs),
        })  # _sc now reflects the deduped signal count

    # Order sectors by config; within a sector, by activity then name
    ordered = []
    for sec in INDUSTRY_SECTORS:
        disp = _sector_disp(sec)
        cos = by_sector.pop(disp, None)
        if not cos:
            continue
        cos.sort(key=lambda c: (-c["_sc"], c["name"]))
        ordered.append({"name": disp, "count": len(cos), "companies": cos})
    # any unexpected sectors (not in config) appended at the end
    for disp, cos in by_sector.items():
        cos.sort(key=lambda c: (-c["_sc"], c["name"]))
        ordered.append({"name": disp, "count": len(cos), "companies": cos})

    return ordered


def normalise_key_events(key_events):
    """Accept a flat list of events and split into {key, others}.

    Each event: {"when", "label", "text", "key": bool}. The first event flagged
    key (or the first event, if none flagged) becomes the highlighted box.
    """
    events = list(key_events or [])
    if not events:
        return {"key": None, "others": []}
    key = next((e for e in events if e.get("key")), None)
    if key is None:
        key = events[0]
    others = [e for e in events if e is not key]
    return {"key": key, "others": others}


def assemble(recaps, industry_news=None, key_events=None, days=7, issue=""):
    """Build the full data dict the template expects."""
    industry_news = industry_news or {}

    signals = _dedupe(flatten_signals(recaps))
    legend = build_legend(signals)

    # Two segments: the tracked watchlist, then notable non-watchlist private names.
    segments = []
    wl_sectors = build_sector_groups([r for r in recaps if r.get("watchlist", True)])
    if wl_sectors:
        segments.append({"key": "watchlist", "title": "Watchlist",
                         "subtitle": "companies we track", "sectors": wl_sectors})
    other_sectors = build_sector_groups([r for r in recaps if not r.get("watchlist", True)])
    if other_sectors:
        segments.append({"key": "other", "title": "Private Markets — Also Notable",
                         "subtitle": "notable private names off the watchlist", "sectors": other_sectors})

    # Counts reflect what's actually shown after the tier gate
    active_companies = sum(len(sec["companies"]) for seg in segments for sec in seg["sectors"])
    active_sectors = len({sec["name"] for seg in segments for sec in seg["sectors"]})

    now = datetime.utcnow()
    start = now - timedelta(days=days)
    week_label = f"{start.strftime('%b %d')} \u2013 {now.strftime('%b %d, %Y')}"

    return {
        "week_label": week_label,
        "issue": issue or "",
        "counts": {
            "signals": len(signals),
            "companies": active_companies,
            "sectors": active_sectors,
        },
        "brief": industry_news.get("week_in_brief") or industry_news.get("market_sentiment") or "",
        "legend": legend,
        "segments": segments,
        "key_events": normalise_key_events(key_events),
        "generated_at": now.strftime("%b %d, %Y \u00b7 %H:%M UTC"),
    }


def render_weekly(data, archive_url=""):
    """Render the locked email-safe layout to an HTML string."""
    return EMAIL_TEMPLATE.render(font=FONT, archive_url=archive_url, **data)


# ── Email-safe template (tables + inline styles, no flex/var/JS) ─────
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

EMAIL_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light only">
<title>Private Markets Weekly</title>
<style> @media only screen and (max-width:620px){ .container{width:100% !important;} } </style>
</head>
<body style="margin:0;padding:0;background:#eef1f5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f5;">
<tr><td align="center" style="padding:16px;">
<table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;font-family:{{ font }};">

  <!-- MASTHEAD -->
  <tr><td style="padding:6px 2px 12px;border-bottom:2px solid #0f172a;">
    <div style="font-size:10.5px;font-weight:700;letter-spacing:1.3px;text-transform:uppercase;color:#2563eb;margin:0 0 5px;">Private Markets Weekly</div>
    <div style="font-size:25px;font-weight:800;color:#0f172a;letter-spacing:-0.5px;line-height:1.1;">The Private Markets Recap</div>
    <div style="margin-top:8px;font-size:12px;color:#64748b;">
      <span style="color:#334155;font-weight:600;">{{ week_label }}</span>{% if issue %}&nbsp;&nbsp;{{ issue }}{% endif %}&nbsp;&nbsp;
      <span style="color:#94a3b8;"><b style="color:#0f172a;">{{ counts.signals }}</b> signals &middot; <b style="color:#0f172a;">{{ counts.companies }}</b> companies &middot; <b style="color:#0f172a;">{{ counts.sectors }}</b> sectors</span>
    </div>
    {% if legend %}<div style="margin-top:9px;line-height:1.9;">
      {% for l in legend %}<span style="white-space:nowrap;margin-right:12px;font-size:10.5px;color:#64748b;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{{ l.color }};vertical-align:middle;margin-right:5px;"></span>{{ l.label }}</span>{% endfor %}
    </div>{% endif %}
  </td></tr>

  <!-- WEEK IN BRIEF -->
  {% if brief %}<tr><td style="padding:12px 0 0;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;border:1px solid #e2e8f0;border-left:3px solid #2563eb;border-radius:8px;">
    <tr><td style="padding:12px 15px;">
      <div style="font-size:10px;font-weight:800;letter-spacing:0.8px;text-transform:uppercase;color:#2563eb;margin:0 0 5px;">The week in brief</div>
      <div style="font-size:13px;color:#334155;line-height:1.6;">{{ brief }}</div>
    </td></tr>
   </table>
  </td></tr>{% endif %}

  <!-- SECTION: NOTABLE COMPANIES (watchlist + non-watchlist private) -->
  {% for seg in segments %}
  <tr><td style="padding:22px 0 6px;border-bottom:1px solid #e2e8f0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="font-size:16px;font-weight:800;color:#0f172a;">{{ seg.title }}</td>
      <td align="right" style="font-size:12px;color:#94a3b8;">{{ seg.subtitle }}</td>
    </tr></table>
  </td></tr>
  {% for sec in seg.sectors %}
  <tr><td style="padding:14px 0 4px;">
    <div style="font-size:11px;font-weight:800;color:#0f172a;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;">{{ sec.name }} &nbsp;<span style="font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:0;text-transform:none;">{{ sec.count }}</span></div>
  </td></tr>
  {% for co in sec.companies %}
  <tr><td style="padding:7px 0 0;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{% if seg.key == 'watchlist' %}#fcfdfe{% else %}#ffffff{% endif %};border:1px solid #e2e8f0;border-left:3px solid {% if seg.key == 'watchlist' %}#0f172a{% else %}#94a3b8{% endif %};border-radius:8px;">
    <tr><td style="padding:11px 14px;">
     <div style="margin-bottom:4px;"><span style="font-size:15px;font-weight:800;color:#0f172a;">{{ co.name }}</span></div>
     {% if co.connection %}<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 6px;"><tr><td style="background:#eff6ff;border:1px solid #dbeafe;border-radius:8px;padding:8px 11px;font-size:12px;color:#1e40af;line-height:1.5;"><span style="font-size:9px;font-weight:800;letter-spacing:0.3px;text-transform:uppercase;color:#2563eb;">Private &#8596; Public</span>&nbsp; {{ co.connection }}</td></tr></table>{% endif %}
     <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      {% for item in co.links %}
      <tr><td style="{% if not loop.first %}border-top:1px solid #e2e8f0;{% endif %}padding:5px 0;font-size:12px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{{ item.color }};vertical-align:middle;margin-right:6px;"></span><a href="{{ item.url }}" style="color:#0f172a;text-decoration:none;">{{ item.title }}</a></td>
      <td align="right" style="{% if not loop.first %}border-top:1px solid #e2e8f0;{% endif %}padding:5px 0;font-size:10.5px;color:#94a3b8;white-space:nowrap;">{{ item.source }}{% if item.date %} &middot; {{ item.date }}{% endif %}</td></tr>
      {% endfor %}
     </table>
    </td></tr>
   </table>
  </td></tr>
  {% endfor %}
  {% endfor %}
  {% endfor %}

  <!-- SECTION: KEY EVENTS -->
  {% if key_events.key or key_events.others %}
  <tr><td style="padding:22px 0 6px;border-bottom:1px solid #e2e8f0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="font-size:16px;font-weight:800;color:#0f172a;">Key Events &middot; Next Week</td>
      <td align="right" style="font-size:12px;color:#94a3b8;">what to watch</td>
    </tr></table>
  </td></tr>
  {% if key_events.key %}
  <tr><td style="padding:8px 0 0;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eff6ff;border:1px solid #dbeafe;border-left:3px solid #2563eb;border-radius:8px;">
    <tr><td style="padding:11px 14px;">
      <div style="font-size:9px;font-weight:800;letter-spacing:0.6px;text-transform:uppercase;color:#2563eb;">&#9733; Top event &nbsp; <span style="color:#0f172a;">{{ key_events.key.when }}</span></div>
      <div style="font-size:13px;color:#334155;line-height:1.55;margin-top:5px;">{% if key_events.key.label %}<b style="color:#0f172a;">{{ key_events.key.label }}</b> {% endif %}{{ key_events.key.text }}</div>
    </td></tr>
   </table>
  </td></tr>
  {% endif %}
  {% if key_events.others %}
  <tr><td style="padding:0;">
   <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;">
    {% for ev in key_events.others %}
    <tr>
      <td width="58" valign="top" align="right" style="{% if not loop.first %}border-top:1px solid #e2e8f0;{% endif %}padding:8px 12px 8px 0;font-size:10.5px;font-weight:800;color:#64748b;text-transform:uppercase;white-space:nowrap;">{{ ev.when }}</td>
      <td valign="top" style="{% if not loop.first %}border-top:1px solid #e2e8f0;{% endif %}padding:8px 0;font-size:12.5px;color:#334155;line-height:1.5;">{% if ev.label %}<b style="color:#0f172a;">{{ ev.label }}</b> &mdash; {% endif %}{{ ev.text }}</td>
    </tr>
    {% endfor %}
   </table>
  </td></tr>
  {% endif %}
  {% endif %}

  <!-- FOOTER -->
  <tr><td style="padding:26px 0 10px;border-top:1px solid #e2e8f0;text-align:center;">
    <div style="font-size:11px;color:#94a3b8;">Generated {{ generated_at }} &middot; Private Markets Weekly &middot; <a href="{{ archive_url or '#' }}" style="color:#2563eb;font-weight:600;text-decoration:none;">Browse the archive &rarr;</a></div>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>
""", autoescape=True)
