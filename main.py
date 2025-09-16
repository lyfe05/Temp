import requests
import re
import json
from datetime import datetime, timezone, timedelta

# --- CONFIG ---
url = "https://super.league.do/index?sport=Football"
headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

TZ_GMT3 = timezone(timedelta(hours=3))

def get_match_dt_utc(m):
    """
    Return a timezone-aware UTC datetime for a match (best-effort).
    Priority:
      1. startTimestamp (ms or s)
      2. matchDate + time (if time is "HH:MM" or a full datetime)
      3. time only (assume today's date in UTC)
    Returns None if no parseable time found.
    """
    # 1) startTimestamp (often milliseconds)
    ts = m.get("startTimestamp")
    if ts is not None:
        try:
            ts_int = int(ts)
            # heuristic: >1e12 means milliseconds, else seconds
            if ts_int > 1e12:
                ts_int = ts_int / 1000.0
            return datetime.fromtimestamp(ts_int, tz=timezone.utc)
        except Exception:
            pass

    # helpers
    def try_parse(s, fmt):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            return None

    time_str = str(m.get("time") or "").strip()
    match_date = str(m.get("matchDate") or "").strip()  # e.g. "2025-09-14"

    # 2) If time already contains a full date
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        dt = try_parse(time_str, fmt)
        if dt:
            return dt

    # 3) If we have matchDate and time is HH:MM
    if match_date and re.match(r"^\d{4}-\d{2}-\d{2}$", match_date) and re.match(r"^\d{1,2}:\d{2}$", time_str):
        combined = f"{match_date} {time_str}"
        dt = try_parse(combined, "%Y-%m-%d %H:%M")
        if dt:
            return dt

    # 4) If only HH:MM provided, assume today's date in UTC
    if re.match(r"^\d{1,2}:\d{2}$", time_str):
        today_utc = datetime.now(timezone.utc).date()
        try:
            t = datetime.strptime(time_str, "%H:%M").time()
            return datetime.combine(today_utc, t).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    return None

def format_gmt3(dt_utc):
    if not dt_utc:
        return "Unknown time"
    return dt_utc.astimezone(TZ_GMT3).strftime("%Y-%m-%d %H:%M GMT+3")

try:
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    html = resp.text

    # extract JSON inside window.matches = JSON.parse(`...`);
    m = re.search(r"window\.matches\s*=\s*JSON\.parse\(`(.+?)`\);", html, re.S)
    if not m:
        raise ValueError("Could not find matches JSON in page.")

    raw_json = m.group(1)
    matches = json.loads(raw_json)

    # attach parsed datetime for sorting
    for match in matches:
        match["__dt_utc"] = get_match_dt_utc(match)

    # sort (None last)
    matches.sort(key=lambda x: (x.get("__dt_utc") is None, x.get("__dt_utc") or datetime.max.replace(tzinfo=timezone.utc)))

    print("✅ Extracted matches successfully!\n")

    # print in your style
    for match in matches:
        dt = match.get("__dt_utc")
        print(f"🏟️ Match: {match.get('team1','?')} Vs {match.get('team2','?')}")
        print(f"🕒 Start: {format_gmt3(dt)}")
        print(f"📍 Tournament: {match.get('league','?')}")
        print("📺 Channels:")
        for ch in match.get("channels", []):
            lang = (ch.get("language") or ch.get("lang") or "").upper() or "??"
            name = ch.get("name") or "Unknown"
            links = " | ".join(ch.get("links", []) or ch.get("oldLinks", []) or [])
            print(f"{lang} | {name}: {links}")
        print("\n" + "="*50 + "\n")

except Exception as e:
    print("❌ Error:", e)
