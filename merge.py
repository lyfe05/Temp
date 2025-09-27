#!/usr/bin/env python3
import requests
import re
import os
import shutil
import time
import base64
import html
from urllib.parse import urlparse, urljoin
from rapidfuzz import fuzz
from typing import List

# --- Config: GitHub sources ---
URL_LYFE = "https://raw.githubusercontent.com/lyfe05/lyfe05/refs/heads/main/matches.txt"
URL_TRIAL = "https://raw.githubusercontent.com/lyfe05/Temp/refs/heads/main/matches.txt"

# --- Headers for vividmosaica ---
HEADERS = {
    "Host": "vividmosaica.com",
    "upgrade-insecure-requests": "1",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "X-Requested-With": "mark.via.gp",
    "Referer": "https://dabac.link/",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
}

# --- Utility ---
def collapse_protocol_slashes(s: str) -> str:
    """Convert weird 'https:////host' to 'https://host'"""
    return re.sub(r'^(https?:)/*', r'\1//', s)

def extract_arrays_from_text(js_text: str) -> List[str]:
    """
    Extract JavaScript string-array literals likely used to build URLs.
    Tries two strategies:
      - capture arrays after 'return([' ... '])' (used in some obfuscation)
      - capture short string-array literals like ["h","t","t","p",...]
    """
    results = []

    # Strategy A: return ( [ ... ] ) scanning for balanced brackets
    for m in re.finditer(r"return\s*\(\s*\[", js_text):
        start = m.end() - 1
        depth = 0
        end = None
        for i in range(start, len(js_text)):
            ch = js_text[i]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end:
            arr = js_text[start:end + 1]
            results.append(arr)

    # Strategy B: general array-literal of short strings (avoid huge arrays)
    for m in re.finditer(r'\[\s*(?:"[^"]{1,30}"\s*,\s*)+"[^"]{1,30}"\s*\]', js_text):
        arr = m.group(0)
        if arr not in results:
            results.append(arr)

    return results

def join_array_chars(array_text: str) -> str:
    """
    Given a JS array literal like ["h","t","t","p","s",":","/","/",...]
    join the quoted pieces into a single string and tidy escapes.
    """
    items = re.findall(r'"([^"]*)"|\'([^\']*)\'', array_text)
    elems = [d if d != "" else s for d, s in items]
    joined = "".join(elems)
    # unescape common JS escapes and normalize protocol slashes
    joined = joined.replace('\\/', '/').replace('\\\\', '\\')
    joined = html.unescape(joined)
    return collapse_protocol_slashes(joined)

def find_urls_in_text(text: str) -> List[str]:
    return re.findall(r'https?://[^\s"\'>]+', text)

def extract_direct_stream_url(embed_url: str) -> str:
    """
    Fetch the embed page and attempt to extract the real .m3u8 URL.
    Preference order:
      1) decode JS-array-built URLs and return first .m3u8 if present
      2) decode atob(...) base64 strings that yield paths/URLs
      3) check hidden span elements referenced by document.getElementById(...).innerHTML
      4) search page for .m3u8 links directly
      5) return first sensible found URL or the embed_url (fallback)
    """
    try:
        r = requests.get(embed_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        text = r.text

        parsed_embed = urlparse(embed_url)
        base_url = f"{parsed_embed.scheme}://{parsed_embed.netloc}"

        found_urls: List[str] = []

        # 1) arrays -> join and inspect
        arrays = extract_arrays_from_text(text)
        for arr in arrays:
            try:
                url = join_array_chars(arr)
            except Exception:
                continue
            # if protocol-relative //host/path, make it https:
            if url.startswith('//'):
                url = 'https:' + url
            if url.startswith(('http://', 'https://', '/')):
                # if starts with '/', join with base
                if url.startswith('/'):
                    url = urljoin(base_url, url)
                found_urls.append(url)
                # immediate return if array decodes directly to .m3u8
                if '.m3u8' in url:
                    return url

        # 2) atob('...') base64 content — decode and inspect
        for m in re.finditer(r'atob\(\s*[\'"]([^\'"]+)[\'"]\s*\)', text):
            try:
                decoded = base64.b64decode(m.group(1)).decode('utf-8', errors='ignore')
            except Exception:
                continue
            decoded = decoded.strip()
            if decoded:
                if decoded.startswith('/'):
                    decoded = urljoin(base_url, decoded)
                if decoded.startswith('//'):
                    decoded = 'https:' + decoded
                if decoded.startswith('http'):
                    found_urls.append(decoded)
                    if '.m3u8' in decoded:
                        return decoded
                else:
                    # decoded might be a path like /hls/... or query part, join base
                    maybe = urljoin(base_url, decoded)
                    found_urls.append(maybe)
                    if '.m3u8' in maybe:
                        return maybe

        # 3) inspect document.getElementById(...).innerHTML referenced ids and extract text from matching <span id=...>...</span>
        ids = re.findall(r'document\.getElementById\(\s*[\'"]([^\'"]+)[\'"]\s*\)\.innerHTML', text)
        for idname in ids:
            # find span with that id
            span_re = re.search(rf'<span[^>]+id=[\'"]{re.escape(idname)}[\'"][^>]*>(.*?)</span>', text, flags=re.S | re.I)
            if span_re:
                content = span_re.group(1).strip()
                if content:
                    # content might be a part appended to other strings; if it contains http or /hls, try to combine
                    if content.startswith('/'):
                        url = urljoin(base_url, content)
                    elif content.startswith('//'):
                        url = 'https:' + content
                    elif content.startswith('http'):
                        url = content
                    else:
                        url = content  # possibly appended to earlier array + this piece; add raw
                    found_urls.append(url)
                    if '.m3u8' in url:
                        return url

        # 4) fallback: any .m3u8 link in page
        m3u8_matches = re.findall(r'https?://[^\s"\'>]+\.m3u8[^\s"\'>]*', text)
        if m3u8_matches:
            return m3u8_matches[0]

        # 5) if we have found_urls earlier (from arrays/atob/spans), prefer those with .m3u8 or common hls path
        if found_urls:
            for u in found_urls:
                if '.m3u8' in u:
                    return u
            for u in found_urls:
                if '/hls/' in u or 'm3u8' in u:
                    return u
            # otherwise return first found
            return found_urls[0]

        # 6) last-ditch: any URL in text
        any_urls = find_urls_in_text(text)
        if any_urls:
            # prefer .m3u8 if present
            for u in any_urls:
                if '.m3u8' in u:
                    return u
            # prefer /hls/
            for u in any_urls:
                if '/hls/' in u:
                    return u
            return any_urls[0]

        # nothing: return embed_url
        return embed_url

    except Exception as e:
        print(f"❌ Error extracting from {embed_url}: {e}")
        return embed_url

def fetch_matches(url: str) -> str:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text

def split_matches(text: str):
    blocks, current = [], []
    for line in text.splitlines():
        if line.strip().startswith("🏟️ Match:"):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks

def extract_title(block: str) -> str:
    m = re.search(r"🏟️ Match:\s*(.+)", block)
    return m.group(1).strip() if m else ""

def extract_channels(block: str):
    channels = []
    start = False
    for line in block.splitlines():
        if line.strip().startswith("📺 Channels:"):
            start = True
            continue
        if start:
            if not line.strip():
                break
            channels.append(line.strip())
    return channels

def convert_url(url: str) -> str:
    """
    Given the channel link (likely contains ch?id=NUMBER), return the best direct URL.
    If the link already contains .m3u8 we return it directly.
    Otherwise we build the vividmosaica embed URL (do{num}) and extract the .m3u8.
    """
    url = url.strip()
    # If it's already a direct m3u8, return as-is
    if '.m3u8' in url:
        return url

    # Extract numeric id if present
    m = re.search(r"id=(\d+)", url)
    if m:
        num = m.group(1)
        embed_url = f"https://vividmosaica.com/embed3.php?player=desktop&live=do{num}"
        return extract_direct_stream_url(embed_url)

    # fallback: attempt direct extraction from provided URL
    return extract_direct_stream_url(url)

def load_whitelist(filename="whitelist.txt"):
    if not os.path.exists(filename):
        raise FileNotFoundError("❌ whitelist.txt is missing. Please add it to the repo.")
    with open(filename, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def filter_channels(channels, whitelist):
    """
    Parse channel lines and return (lang, name, [direct_link, ...]) where direct_link
    is already processed by convert_url().
    """
    filtered = []
    for ch in channels:
        m = re.match(r"^([A-Z]{2})\s*\|\s*(.+?):\s*(.+)$", ch)
        if not m:
            continue
        lang, name, links = m.groups()
        if lang not in whitelist:
            continue
        valid_links = []
        for lnk in links.split("|"):
            lnk = lnk.strip()
            # match any ch?id= pattern or if the link already looks like a URL
            if "ch?id=" in lnk or lnk.startswith("http"):
                try:
                    direct_url = convert_url(lnk)
                    if direct_url:
                        valid_links.append(direct_url)
                except Exception:
                    continue
        if valid_links:
            filtered.append((lang, name, valid_links))
    return filtered

def safe_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]+', "_", name).lower()

def create_m3u8_file(filename, stream_url):
    # Keep headers but include the *real* .m3u8 URL
    m3u8_content = f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1920x1080
{stream_url.strip()}"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(m3u8_content)

def process_and_generate():
    whitelist = load_whitelist()

    print("🔄 Fetching matches...")
    text_lyfe = fetch_matches(URL_LYFE)
    text_trial = fetch_matches(URL_TRIAL)

    lyfe_blocks = split_matches(text_lyfe)
    trial_blocks = split_matches(text_trial)
    trial_map = {extract_title(b): b for b in trial_blocks}

    if os.path.exists("streams"):
        shutil.rmtree("streams")
    os.makedirs("streams", exist_ok=True)

    total_files = 0
    for i, lb in enumerate(lyfe_blocks):
        title = extract_title(lb)
        if not title:
            continue

        # fuzzy match title
        best_title, best_score = None, 0
        for tb_title in trial_map.keys():
            score = fuzz.ratio(title.lower(), tb_title.lower())
            if score > best_score:
                best_title, best_score = tb_title, score

        if best_score < 80:
            # Skip poorly-matching titles
            continue

        trial_channels = extract_channels(trial_map[best_title])
        trial_channels = filter_channels(trial_channels, whitelist)

        if not trial_channels:
            continue

        safe_name = safe_filename(title)
        # sequential naming and dedupe
        stream_index = 1
        written_urls = set()

        for _, name, links in trial_channels:
            for link in links:
                direct = link.strip()
                # If extractor returned an embed page rather than .m3u8, try again
                if '.m3u8' not in direct and 'http' in direct:
                    direct = extract_direct_stream_url(direct)

                # collapse protocol slashes just in case
                direct = collapse_protocol_slashes(direct)

                if direct in written_urls:
                    print(f"🔁 Skipping duplicate URL for {safe_name}: {direct}")
                    continue

                written_urls.add(direct)

                if stream_index == 1:
                    fname = f"streams/{safe_name}.m3u8"
                else:
                    fname = f"streams/{safe_name}_{stream_index}.m3u8"

                create_m3u8_file(fname, direct)
                print(f"📄 Created {fname}")
                total_files += 1
                stream_index += 1

        # small throttle
        if i % 3 == 0 and i > 0:
            time.sleep(1)

    print(f"\n✅ Done! Created {total_files} .m3u8 files in streams/")

if __name__ == "__main__":
    process_and_generate()
