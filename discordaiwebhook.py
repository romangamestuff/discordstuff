import feedparser
import requests
import json
import os
import time
import logging
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

if not WEBHOOK_URL:
    raise EnvironmentError("DISCORD_WEBHOOK environment variable is not set.")

RAW_QUERIES = [
    {
        "label": "AI Tools",
        "query": '("Claude AI" OR "OpenAI Codex" OR "Cursor AI" OR "Replit AI" OR "Devin AI") AND (release OR launch OR update)',
    },
    {
        "label": "AI Dev",
        "query": '"AI coding assistant" OR "AI code generation" OR "LLM developer tools"',
    },
]

KEYWORDS = [
    "claude", "codex", "cursor", "replit", "devin",
    "ai coding", "code generation", "developer tool", "llm", "vibe coding"
]

MAX_POSTS = 5
MAX_AGE_DAYS = 7
MAX_HISTORY = 500
HISTORY_FILE = "posted.json"
DISCORD_RATE_LIMIT_SLEEP = 2.1   # seconds between webhook POSTs (~28/min, under 30 limit)

EMBED_COLOR = 5814783            # original purple

# =========================
# BUILD FEED URLS
# =========================
def build_google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )

FEEDS = [
    {"label": f["label"], "url": build_google_news_url(f["query"])}
    for f in RAW_QUERIES
]

# =========================
# HTTP SESSION W/ RETRIES
# =========================
def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

SESSION = make_session()

# =========================
# LOAD HISTORY
# =========================
def load_history() -> set:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_history(posted: set) -> None:
    # Trim to last MAX_HISTORY entries (sets aren't ordered, but this caps growth)
    trimmed = list(posted)[-MAX_HISTORY:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(trimmed, f, indent=2)
    log.info(f"History saved ({len(trimmed)} entries).")

# =========================
# HELPERS
# =========================
def relevance_score(title: str) -> int:
    t = title.lower()
    return sum(1 for k in KEYWORDS if k in t)

def is_recent(entry) -> bool:
    """Return True if the entry was published within MAX_AGE_DAYS."""
    published = entry.get("published_parsed")
    if not published:
        return True  # no date info → don't filter it out
    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    return pub_dt >= cutoff

def send_to_discord(title: str, link: str, source_label: str) -> bool:
    now_str = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    data = {
        "embeds": [
            {
                "title": "⚡ Ub3r Vibe Coding Drop",
                "description": f"**{title}**",
                "url": link,
                "color": EMBED_COLOR,
                "footer": {
                    "text": f"Source: {source_label}  •  {now_str}"
                },
            }
        ]
    }
    try:
        resp = SESSION.post(WEBHOOK_URL, json=data, timeout=10)
        resp.raise_for_status()
        log.info(f"  ✅ Sent: {title[:80]}")
        return True
    except requests.HTTPError as e:
        log.error(f"  ❌ HTTP error sending to Discord: {e} (status {resp.status_code})")
    except requests.RequestException as e:
        log.error(f"  ❌ Request error sending to Discord: {e}")
    return False

# =========================
# FETCH + SCORE ENTRIES
# =========================
posted = load_history()
candidates = []

for feed_info in FEEDS:
    label = feed_info["label"]
    url = feed_info["url"]
    log.info(f"Fetching feed: [{label}] {url}")

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        log.error(f"  Failed to parse feed [{label}]: {e}")
        continue

    if feed.bozo and feed.bozo_exception:
        log.warning(f"  Feed [{label}] parse warning: {feed.bozo_exception}")

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()

        if not title or not link:
            continue
        if link in posted:
            continue
        if not is_recent(entry):
            continue

        score = relevance_score(title)
        if score == 0:
            continue

        candidates.append({
            "title": title,
            "link": link,
            "label": label,
            "score": score,
        })

log.info(f"Found {len(candidates)} new relevant entries.")

# =========================
# SORT + SEND (best first)
# =========================
candidates.sort(key=lambda x: x["score"], reverse=True)

sent = 0
for item in candidates:
    if sent >= MAX_POSTS:
        break

    success = send_to_discord(item["title"], item["link"], item["label"])
    if success:
        posted.add(item["link"])
        sent += 1
        if sent < MAX_POSTS:
            time.sleep(DISCORD_RATE_LIMIT_SLEEP)

log.info(f"Done. Sent {sent} post(s).")

# =========================
# SAVE HISTORY
# =========================
save_history(posted)
