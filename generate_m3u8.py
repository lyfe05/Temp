import requests
import os
import re

def fetch_matches():
    """Fetch matches from GitHub"""
    url = "https://raw.githubusercontent.com/lyfe05/lyfe05/refs/heads/main/matches.txt"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            print(f"❌ Failed to fetch matches. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error fetching matches: {e}")
        return None

def parse_matches(matches_text):
    """Parse the matches text into a list of match names"""
    matches = []
    current_match = ""
    
    for line in matches_text.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        if '🏟️ Match:' in line:
            if current_match:
                matches.append(current_match)
            current_match = line.split('Match: ')[1].strip()
    
    if current_match:
        matches.append(current_match)
    
    return matches

def fetch_iptv_channels():
    """Fetch IPTV channels directly from the server"""
    base_url = "http://line.stayconnected.pro/server/load.php"
    cookies = {"mac": "00:1A:79:63:32:60"}
    headers = {
        "x-user-agent": "Model: MAG250; Link: WiFi",
        "user-agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Host": "line.stayconnected.pro"
    }

    try:
        # Handshake to get token
        print("🤝 Handshaking with IPTV server...")
        handshake_params = {"type": "stb", "action": "handshake"}
        handshake_resp = requests.get(base_url, headers=headers, cookies=cookies, params=handshake_params, timeout=15)
        handshake_data = handshake_resp.json()
        token = handshake_data["js"]["token"]
        print(f"✅ Got token: {token[:10]}...")

        # Get all channels
        print("📡 Fetching IPTV channels...")
        channels_params = {"type": "itv", "action": "get_all_channels"}
        headers["Authorization"] = f"Bearer {token}"
        channels_resp = requests.get(base_url, headers=headers, cookies=cookies, params=channels_params, timeout=30)
        
        if channels_resp.status_code == 200:
            channels_data = channels_resp.json()
            total_channels = len(channels_data['js']['data'])
            print(f"✅ Successfully fetched {total_channels} channels")
            return channels_data
        else:
            print(f"❌ Failed to fetch channels. Status: {channels_resp.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error fetching IPTV channels: {e}")
        return None

def convert_to_m3u8_url(ts_url):
    """Convert TS URL with token to M3U8 URL"""
    if 'stream=' in ts_url:
        stream_id = ts_url.split('stream=')[1].split('&')[0]
        m3u8_url = f"http://line.stayconnected.pro:80/play/live.php?mac=00:1A:79:63:32:60&stream={stream_id}&extension=m3u8"
        return m3u8_url
    return ts_url

def find_channels_for_match(match_name, iptv_channels_data):
    """Find IPTV channels that contain the match name in their channel name"""
    matching_channels = []
    
    # Split match name into teams
    teams = [team.strip() for team in match_name.split('Vs')]
    if len(teams) < 2:
        teams = [team.strip() for team in match_name.split('vs')]
    if len(teams) < 2:
        teams = [team.strip() for team in match_name.split('VS')]
    
    for channel in iptv_channels_data['js']['data']:
        channel_name = channel['name']
        
        # Check if both team names appear in the channel name (case insensitive)
        if all(team.lower() in channel_name.lower() for team in teams if team):
            m3u8_url = convert_to_m3u8_url(channel['cmd'])
            
            channel_info = {
                "id": channel['id'],
                "name": channel['name'],
                "number": channel['number'],
                "cmd": m3u8_url,
                "logo": channel.get('logo', '')
            }
            matching_channels.append(channel_info)
    
    return matching_channels

def create_safe_filename(match_name):
    """Convert match name to safe filename"""
    safe_name = re.sub(r'[^a-zA-Z0-9_ ]', '', match_name)
    safe_name = safe_name.replace(' ', '_').lower()
    return safe_name

def create_m3u8_file(filename, stream_url):
    """Create M3U8 file with the specified format"""
    m3u8_content = f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1920x1080
{stream_url}"""
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(m3u8_content)

def generate_m3u8_files(matches_with_channels):
    """Generate M3U8 files for each match"""
    os.makedirs('streams', exist_ok=True)
    files_created = 0
    
    for match in matches_with_channels:
        match_name = match['name']
        channels = match['channels']
        safe_name = create_safe_filename(match_name)
        
        if len(channels) == 1:
            # Single channel - create one file
            filename = f"streams/{safe_name}.m3u8"
            create_m3u8_file(filename, channels[0]['cmd'])
            print(f"   📄 Created: {filename}")
            files_created += 1
        else:
            # Multiple channels - create multiple files
            for i, channel in enumerate(channels, 1):
                if i == 1:
                    filename = f"streams/{safe_name}.m3u8"
                else:
                    filename = f"streams/{safe_name}_{i}.m3u8"
                
                create_m3u8_file(filename, channel['cmd'])
                print(f"   📄 Created: {filename}")
                files_created += 1
    
    return files_created

def main():
    print("🚀 Starting M3U8 generator...")
    print("=" * 50)
    
    # Step 1: Fetch matches from GitHub
    print("📡 Step 1: Fetching matches from GitHub...")
    matches_text = fetch_matches()
    if not matches_text:
        return
    
    matches = parse_matches(matches_text)
    print(f"✅ Found {len(matches)} matches")
    
    # Step 2: Fetch IPTV channels
    print("\n📡 Step 2: Fetching IPTV channels...")
    iptv_channels = fetch_iptv_channels()
    if not iptv_channels:
        return
    
    # Step 3: Find matching channels for each match
    print("\n🔍 Step 3: Finding matches in IPTV channels...")
    matches_with_channels = []
    
    for match_name in matches:
        channels = find_channels_for_match(match_name, iptv_channels)
        
        if channels:
            matches_with_channels.append({
                'name': match_name,
                'channels': channels
            })
            print(f"✅ Found {len(channels)} channel(s) for: {match_name}")
        else:
            print(f"❌ No channels found for: {match_name}")
    
    if not matches_with_channels:
        print("\n😞 No matches found in IPTV channels")
        return
    
    # Step 4: Generate M3U8 files
    print(f"\n📁 Step 4: Generating M3U8 files for {len(matches_with_channels)} matches...")
    files_created = generate_m3u8_files(matches_with_channels)
    
    print("=" * 50)
    print(f"\n🎉 All done!")
    print(f"📊 Summary:")
    print(f"   • Matches processed: {len(matches)}")
    print(f"   • Matches with streams: {len(matches_with_channels)}")
    print(f"   • M3U8 files created: {files_created}")
    print(f"   • Files saved in: streams/ folder")
    print(f"\n📺 You can now use the M3U8 files with any media player!")

if __name__ == "__main__":
    main()
