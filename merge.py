import requests
import re
import os
import shutil
import time
from rapidfuzz import fuzz
from typing import List

# --- Config: GitHub sources ---
URL_LYFE = "https://raw.githubusercontent.com/lyfe05/lyfe05/refs/heads/main/matches.txt"
URL_TEMP = "https://raw.githubusercontent.com/lyfe05/Temp/refs/heads/main/matches.txt"

# --- Headers for vividmosaica ---
HEADERS = {
    "Host": "vividmosaica.com",
    "upgrade-insecure-requests": "1",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "X-Requested-With": "mark.via.gp",
    "Referer": "https://vuen.link/",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
}


# --- Utility ---
def collapse_protocol_slashes(s: str) -> str:
    return re.sub(r'^(https?:)/*', r'\1//', s)


def extract_arrays_from_text(js_text: str) -> List[str]:
    results = []
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
            results.append(js_text[start:end + 1])
    return results


def join_array_chars(array_text: str) -> str:
    items = re.findall(r'"([^"]*)"|\'([^\']*)\'', array_text)
    elems = [d if d != "" else s for d, s in items]
    joined = "".join(elems)
    joined = joined.replace('\\/', '/').replace('\\\\', '\\')
    return collapse_protocol_slashes(joined)


def find_urls_in_text(text: str) -> List[str]:
    return re.findall(r'https?://[^\s"\'>]+', text)


def extract_direct_stream_url(embed_url: str) -> str:
    """Extract direct stream URL from vividmosaica embed"""
    try:
        r = requests.get(embed_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        text = r.text

        found_urls = []
        arrays = extract_arrays_from_text(text)
        for arr in arrays:
            url = join_array_chars(arr)
            if url.startswith(("http://", "https://")):
                found_urls.append(url)

        if not found_urls:
            found_urls = find_urls_in_text(text)

        return found_urls[0] if found_urls else embed_url

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
    m = re.search(r"id=(\d+)", url)
    if m:
        num = m.group(1)
        embed_url = f"https://vividmosaica.com/embed3.php?player=desktop&live=do{num}"
        return extract_direct_stream_url(embed_url)
    return url


def load_whitelist(filename="whitelist.txt"):
    if not os.path.exists(filename):
        raise FileNotFoundError("❌ whitelist.txt is missing. Please add it to the repo.")
    with open(filename, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def filter_channels(channels, whitelist):
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
            if "https://vuen.link/ch?id=" in lnk:
                direct_url = convert_url(lnk)
                valid_links.append(direct_url)
        if valid_links:
            filtered.append((lang, name, valid_links))
    return filtered


def safe_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]+', "_", name).lower()


def create_m3u8_file(filename, stream_url):
    m3u8_content = f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1920x1080
{stream_url}"""
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
            continue

        trial_channels = extract_channels(trial_map[best_title])
        trial_channels = filter_channels(trial_channels, whitelist)

        if not trial_channels:
            continue

        safe_name = safe_filename(title)
        for j, (_, name, links) in enumerate(trial_channels, 1):
            for k, link in enumerate(links, 1):
                fname = f"streams/{safe_name}.m3u8" if (j == 1 and k == 1) else f"streams/{safe_name}_{j}_{k}.m3u8"
                create_m3u8_file(fname, link)
                print(f"📄 Created {fname}")
                total_files += 1

        if i % 3 == 0 and i > 0:
            time.sleep(1)

    print(f"\n✅ Done! Created {total_files} .m3u8 files in streams/")


if __name__ == "__main__":
    process_and_generate()
