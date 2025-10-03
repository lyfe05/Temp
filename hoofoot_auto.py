#!/usr/bin/env python3
import pycurl
from io import BytesIO
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import sys
import time

BASE = "https://hoofoot.com/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def fetch(url, timeout=30):
    buf = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, url)
    c.setopt(c.WRITEFUNCTION, buf.write)
    c.setopt(c.FOLLOWLOCATION, True)
    c.setopt(c.USERAGENT, UA)
    c.setopt(c.ACCEPT_ENCODING, "gzip, deflate")
    c.setopt(c.CONNECTTIMEOUT, 10)
    c.setopt(c.TIMEOUT, timeout)
    try:
        c.perform()
    finally:
        c.close()
    return buf.getvalue().decode("utf-8", errors="ignore")

def normalize_url(src):
    if not src:
        return None
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(BASE, src)
    if not src.startswith("http"):
        return urljoin(BASE, src)
    return src

def find_matches_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    matches = []

    match_containers = soup.find_all("div", id=lambda x: x and x.startswith("port"))

    for container in match_containers:
        try:
            title_element = container.find("h2")
            if not title_element:
                continue
            title = title_element.get_text(strip=True)

            link_element = container.find("a", href=True)
            if not link_element or "match=" not in link_element["href"]:
                continue
            url = normalize_url(link_element["href"])

            img_element = container.find("img", src=True)
            image_url = normalize_url(img_element["src"]) if img_element else None

            matches.append({
                "title": title,
                "url": url,
                "image": image_url
            })
        except Exception:
            continue

    return matches

def extract_embed_url(match_html):
    soup = BeautifulSoup(match_html, "html.parser")
    player = soup.find("div", id="player")
    if player:
        a = player.find("a", href=True)
        if a:
            return urljoin(BASE, a["href"])
    for a in soup.find_all("a", href=True):
        if "embed" in a["href"] or "spotlightmoment" in a["href"]:
            return urljoin(BASE, a["href"])
    return None

def extract_m3u8_from_embed(embed_html):
    m = re.search(r"src\s*:\s*{\s*hls\s*:\s*'(?P<u>//[^']+)'\s*}", embed_html)
    if m:
        return "https:" + m.group("u")
    m = re.search(r"backupSrc\s*:\s*{\s*hls\s*:\s*'(?P<u>//[^']+)'\s*}", embed_html)
    if m:
        return "https:" + m.group("u")
    m = re.search(r"(https?:)?//[^\s'\";]+\.m3u8[^\s'\";]*", embed_html)
    if m:
        url = m.group(0)
        if url.startswith("//"):
            return "https:" + url
        return url
    return None

def process_match(match):
    try:
        m_html = fetch(match['url'])
        embed = extract_embed_url(m_html)
        if not embed:
            return {"title": match['title'], "embed": None, "m3u8": None, "image": match.get("image")}
        embed_html = fetch(embed)
        m3u8 = extract_m3u8_from_embed(embed_html)
        return {"title": match['title'], "embed": embed, "m3u8": m3u8, "image": match.get("image")}
    except Exception:
        return {"title": match['title'], "embed": None, "m3u8": None, "image": match.get("image")}

def main():
    print("📡 Fetching HooFoot homepage...")
    try:
        home_html = fetch(BASE)
    except Exception as e:
        print("❌ Fetch error:", e)
        sys.exit(1)

    matches = find_matches_from_html(home_html)
    if not matches:
        print("❌ No matches found.")
        sys.exit(1)

    print(f"\n🚀 Found {len(matches)} matches. Fetching embed + m3u8 for all...\n")

    results = []
    for i, match in enumerate(matches, 1):
        print(f"⏳ [{i}/{len(matches)}] Processing: {match['title']}")
        result = process_match(match)
        results.append(result)
        time.sleep(1)

    print("\n✅ FINAL RESULTS\n" + "="*60)
    for r in results:
        print(f"⚽ {r['title']}")
        print(f"📺 Embed: {r['embed'] or '❌ Not found'}")
        print(f"🖼️ Image: {r['image'] or '❌ Not found'}")
        print(f"🎥 M3U8:  {r['m3u8'] or '❌ Not found'}")
        print("-"*60)

if __name__ == "__main__":
    main()
