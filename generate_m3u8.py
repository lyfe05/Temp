import requests
import re
import json
import os
import shutil
from datetime import datetime
from rapidfuzz import fuzz

# ---------- CONFIG ----------
MATCHES_URL = "https://raw.githubusercontent.com/lyfe05/lyfe05/refs/heads/main/matches.txt"
CHANNELS_URL = "https://raw.githubusercontent.com/lyfe05/lyfe05/refs/heads/main/channels.txt"
WHITELIST_FILE = "whitelist.txt"
STREAMS_DIR = "streams"

# ---------- CLEANUP STREAMS ----------
if os.path.exists(STREAMS_DIR):
    shutil.rmtree(STREAMS_DIR)  # remove yesterday’s files
os.makedirs(STREAMS_DIR, exist_ok=True)  # recreate clean folder

# ---------- HELPERS ----------
def normalize_team_name(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())

def fuzzy_match(name1, name2, threshold=80):
    return fuzz.ratio(normalize_team_name(name1), normalize_team_name(name2)) >= threshold

def load_whitelist():
    if os.path.exists(WHITELIST_FILE):
        with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
            return [line.strip().upper() for line in f if line.strip()]
    return []

def fetch_lines(url):
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.text.strip().splitlines()
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
    return []

# ---------- FETCH DATA ----------
matches = fetch_lines(MATCHES_URL)
channels = fetch_lines(CHANNELS_URL)
lang_whitelist = load_whitelist()

merged_matches = []

# ---------- PROCESS MATCHES ----------
for match_line in matches:
    try:
        match = json.loads(match_line)
    except json.JSONDecodeError:
        continue

    home, away = match.get("home_team", ""), match.get("away_team", "")
    start_time = match.get("start_time", "")
    tournament = match.get("tournament", "")

    matched_channels = []
    for ch_line in channels:
        try:
            ch = json.loads(ch_line)
        except json.JSONDecodeError:
            continue

        ch_name = ch.get("name", "")
        ch_lang = ch.get("lang", "").upper()
        ch_url = ch.get("url", "")

        if not ch_name or not ch_url:
            continue

        # Whitelist filter
        if lang_whitelist and ch_lang not in lang_whitelist:
            continue

        # Match by fuzzy home/away
        if fuzzy_match(home, ch_name) or fuzzy_match(away, ch_name):
            # Replace vuen.link with vividmosaica.com format
            match_id = None
            m = re.search(r"id=(\d+)", ch_url)
            if m:
                match_id = m.group(1)
                ch_url = f"https://vividmosaica.com/embed3.php?player=desktop&live=do{match_id}"

            matched_channels.append(f"{ch_lang} | {ch_name}: {ch_url}")

    if matched_channels:
        merged_matches.append({
            "home": home,
            "away": away,
            "start_time": start_time,
            "tournament": tournament,
            "channels": matched_channels
        })

# ---------- SAVE TO FILE ----------
output_file = os.path.join(STREAMS_DIR, "merged.txt")

with open(output_file, "w", encoding="utf-8") as f:
    print("==============================================", file=f)
    print(f"✅ Found {len(merged_matches)} merged matches", file=f)
    print("==============================================\n", file=f)

    for m in merged_matches:
        print(f"🏟️ Match: {m['home']} Vs {m['away']}", file=f)
        print(f"🕒 Start: {m['start_time']} (GMT+3)", file=f)
        print(f"📍 Tournament: {m['tournament']}", file=f)
        print("📺 Channels:", file=f)
        for ch in m["channels"]:
            print(ch, file=f)
        print("--------------------------------------------------", file=f)
        print("--------------------------------------------------\n", file=f)

print(f"✅ Done! Results saved in {output_file}")
