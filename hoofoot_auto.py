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

def find_matches_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    seen = set()

    # find all match containers (div id starts with "port")
    match_divs = soup.find_all("div", id=lambda x: x and x.startswith("port"))
    for div in match_divs:
        title_el = div.find("h2")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        a = div.find("a", href=True)
        if not a or "?match=" not in a["href"]:
            continue
        url = urljoin(BASE, a["href"])

        # image extraction (same logic as the .html script)
        img_el = div.find("img", src=True)
        if img_el:
            img_url = img_el["src"]
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif not img_url.startswith("http"):
                img_url = urljoin(BASE, img_url)
        else:
            img_url = None

        if url in seen:
            continue
        seen.add(url)
        matches.append({"title": title, "url": url, "image": img_url})
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
        m_html = fetch(match["url"])
        embed = extract_embed_url(m_html)
        if not embed:
            return {"title": match["title"], "embed": None, "m3u8": None, "image": match.get("image")}
        embed_html = fetch(embed)
        m3u8 = extract_m3u8_from_embed(embed_html)
        return {"title": match["title"], "embed": embed, "m3u8": m3u8, "image": match.get("image")}
    except Exception:
        return {"title": match["title"], "embed": None, "m3u8": None, "image": match.get("image")}

def main():
    # fetch homepage
    try:
        home_html = fetch(BASE)
    except Exception as e:
        print("❌ Fetch error:", e)
        sys.exit(1)

    matches = find_matches_from_html(home_html)
    if not matches:
        print("❌ No matches found.")
        sys.exit(1)

    results = []
    for match in matches:
        result = process_match(match)
        results.append(result)
        time.sleep(1)  # polite delay

    # save results.txt
    with open("results.txt", "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"⚽ {r['title']}\n")
            f.write(f"📺 Embed: {r['embed'] or '❌ Not found'}\n")
            f.write(f"🖼️ Image: {r['image'] or '❌ Not found'}\n")
            f.write(f"🎥 M3U8:  {r['m3u8'] or '❌ Not found'}\n")
            f.write("------------------------------------------------------------\n")

    print("✅ results.txt generated successfully!")

if __name__ == "__main__":
    main()
