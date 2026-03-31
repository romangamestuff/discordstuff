import feedparser
import requests
import json
import os

# =========================
# CONFIG
# =========================
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")

FEEDS = [
    "https://news.google.com/rss/search?q=(\"Claude AI\" OR \"OpenAI Codex\" OR \"Cursor AI\" OR \"Replit AI\" OR \"Devin AI\") AND (release OR launch OR update)&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=(\"AI coding assistant\" OR \"AI code generation\" OR \"LLM developer tools\")&hl=en-US&gl=US&ceid=US:en"
]

KEYWORDS = [
    "claude", "codex", "cursor", "replit", "devin",
    "ai coding", "code generation", "developer tool"
]

MAX_POSTS = 5
HISTORY_FILE = "posted.json"

# =========================
# LOAD HISTORY
# =========================
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        posted = set(json.load(f))
else:
    posted = set()

# =========================
# HELPERS
# =========================
def is_relevant(title):
    t = title.lower()
    return any(k in t for k in KEYWORDS)

def send_to_discord(title, link):
    data = {
        "embeds": [
            {
                "title": "⚡ Ub3r Vibe Coding Drop",
                "description": title,
                "url": link,
                "color": 5814783
            }
        ]
    }
    requests.post(WEBHOOK_URL, json=data)

# =========================
# FETCH + PROCESS
# =========================
new_posts = []

for feed_url in FEEDS:
    feed = feedparser.parse(feed_url)

    for entry in feed.entries:
        title = entry.title.strip()
        link = entry.link.strip()

        # Deduplicate (persistent)
        if link in posted:
            continue

        # Relevance filter
        if not is_relevant(title):
            continue

        new_posts.append((title, link))

# =========================
# LIMIT + SEND
# =========================
count = 0

for title, link in new_posts:
    if count >= MAX_POSTS:
        break

    send_to_discord(title, link)
    posted.add(link)
    count += 1

# =========================
# SAVE HISTORY
# =========================
with open(HISTORY_FILE, "w") as f:
    json.dump(list(posted), f)
