import urllib.request
import os
import re
import asyncio
import aiohttp

# --- STREAM VALIDATION LOGIC ---
async def check_stream_url(session, url, timeout=5):
    """
    Asynchronously checks if an HLS/IPTV stream URL is active and reachable.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        # Using GET with a stream=True equivalent (reading only headers/initial chunks)
        async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as response:
            if response.status != 200:
                return False
            
            # Read the first few lines of the stream playlist to ensure it's a real HLS target
            # Valid HLS manifests start with #EXTM3U
            first_chunk = await response.content.read(128)
            content_text = first_chunk.decode('utf-8', errors='ignore')
            
            # If it's an M3U8 playlist or a direct Transport Stream (.ts video container)
            if "#EXTM3U" in content_text or response.headers.get('Content-Type', '').strip().startswith(('video/', 'application/x-mpegURL', 'application/vnd.apple.mpegurl')):
                return True
                
            return False
    except Exception:
        return False

async def validate_all_streams(playlist_data):
    """
    Filters through gathered playlist data to weed out dead links concurrently.
    """
    print("\n--- Starting Live Stream Validation ---")
    valid_playlist_data = {}
    
    # Configure connection pooling to prevent hitting rate-limits or system file limits
    connector = aiohttp.TCPConnector(limit=50, ssl=False) 
    async with aiohttp.ClientSession(connector=connector) as session:
        
        for group, channels in playlist_data.items():
            print(f"Validating group: {group} ({len(channels)} candidates)...")
            tasks = []
            
            for channel_name, extinf, stream_url in channels:
                tasks.append(check_stream_url(session, stream_url))
                
            # Run all checks for this group concurrently
            results = await asyncio.gather(*tasks)
            
            # Filter and keep only working streams
            valid_channels = []
            for i, is_alive in enumerate(results):
                channel_info = channels[i]
                if is_alive:
                    valid_channels.append(channel_info)
                else:
                    print(f"  ❌ Removing Dead Stream: {channel_info[0]} ({channel_info[2]})")
                    
            if valid_channels:
                valid_playlist_data[group] = valid_channels
                
    return valid_playlist_data


# --- MAIN PIPELINE ---
def main():
    sources_file = "sources.txt"
    filter_file = "channels.txt"
    output_file = "family.m3u"
    
    current_target_group = "Other"
    
    if not os.path.exists(sources_file):
        print("sources.txt not found!")
        return

    channel_to_group_map = {}
    if os.path.exists(filter_file):
        with open(filter_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(":"):
                    current_target_group = line[1:].strip()
                else:
                    channel_to_group_map[line.upper()] = current_target_group
        print(f"Loaded {len(channel_to_group_map)} total filtered channels from master list.")
    else:
        print("channels.txt not found! Keeping all channels under 'Other' by default.")

    sorted_allowed_channels = sorted(channel_to_group_map.keys(), key=len, reverse=True)

    with open(sources_file, "r") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    raw_playlist_data = {}
    seen_streams = set()

    for url in urls:
        print(f"Fetching: {url}")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode('utf-8', errors='ignore')
                lines = content.splitlines()
                
                current_extinf = None
                for line in lines:
                    line = line.strip()
                    if line.startswith("#EXTINF"):
                        current_extinf = line
                    elif line and not line.startswith("#"):
                        if line not in seen_streams:
                            if current_extinf:
                                channel_name = current_extinf.split(",")[-1].strip()
                                channel_name_upper = channel_name.upper()
                                
                                assigned_group = None
                                if channel_to_group_map:
                                    for allowed_name in sorted_allowed_channels:
                                        if allowed_name in channel_name_upper:
                                            assigned_group = channel_to_group_map[allowed_name]
                                            break
                                    if not assigned_group:
                                        current_extinf = None
                                        continue
                                else:
                                    assigned_group = "Other"
                                
                                seen_streams.add(line)
                                
                                if 'group-title="' in current_extinf:
                                    fixed_extinf = re.sub(r'group-title="[^"]+"', f'group-title="{assigned_group}"', current_extinf)
                                else:
                                    fixed_extinf = re.sub(r'(#EXTINF:[-\d]+)', f'\\1 group-title="{assigned_group}"', current_extinf)
                                
                                if assigned_group not in raw_playlist_data:
                                    raw_playlist_data[assigned_group] = []
                                raw_playlist_data[assigned_group].append((channel_name, fixed_extinf, line))
                            else:
                                if not channel_to_group_map:
                                    seen_streams.add(line)
                                    if "Other" not in raw_playlist_data:
                                        raw_playlist_data["Other"] = []
                                    raw_playlist_data["Other"].append(("Uncategorized Stream", f'#EXTINF:-1 group-title="Other",Uncategorized Stream', line))
                                    
                        current_extinf = None
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")

    # --- RUN THE VALIDATION COMPONENT ---
    playlist_data = asyncio.run(validate_all_streams(raw_playlist_data))

    # --- SORTING LOGIC ---
    all_groups = sorted([g for g in playlist_data.keys() if g.lower() != "other"], key=lambda s: s.lower())
    if "Other" in playlist_data or "other" in [g.lower() for g in playlist_data.keys()]:
        other_key = next((g for g in playlist_data.keys() if g.lower() == "other"), "Other")
        all_groups.append(other_key)

    combined_lines = ["#EXTM3U\n"]
    total_channels_count = 0
    
    for group in all_groups:
        sorted_channels = sorted(playlist_data[group], key=lambda x: x[0].lower().strip())
        for channel_name, extinf, stream_url in sorted_channels:
            combined_lines.append(extinf + "\n")
            combined_lines.append(stream_url + "\n")
            total_channels_count += 1

    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(combined_lines)
        
    print(f"\nSuccessfully generated sorted {output_file} with {total_channels_count} LIVE channels.")

if __name__ == "__main__":
    main()
