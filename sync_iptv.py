import urllib.request
import os
import re

def main():
    sources_file = "sources.txt"
    filter_file = "channels.txt"
    output_file = "family.m3u"
    
    # Default folder name if no colon header is found at the start of channels.txt
    current_target_group = "Other"
    
    if not os.path.exists(sources_file):
        print("sources.txt not found!")
        return

    # Load master allowed channels and map them to their respective folder categories
    channel_to_group_map = {}
    
    if os.path.exists(filter_file):
        with open(filter_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                # Check if this line defines a new folder group (e.g., ":News Channels")
                if line.startswith(":"):
                    current_target_group = line[1:].strip()
                else:
                    # Map the upper-case channel name to its designated group folder
                    channel_to_group_map[line.upper()] = current_target_group
        print(f"Loaded {len(channel_to_group_map)} total filtered channels from master list.")
    else:
        print("channels.txt not found! Keeping all channels under 'Other' by default.")

    with open(sources_file, "r") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    # Dictionary layout to hold streams by group
    playlist_data = {}
    seen_streams = set()
    total_channels_count = 0

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
                                # Extract channel name (everything after the last comma)
                                channel_name = current_extinf.split(",")[-1].strip()
                                channel_name_upper = channel_name.upper()
                                
                                # Match against your master channel map
                                assigned_group = None
                                if channel_to_group_map:
                                    for allowed_name, target_folder in channel_to_group_map.items():
                                        if allowed_name in channel_name_upper:
                                            assigned_group = target_folder
                                            break
                                    
                                    if not assigned_group:
                                        current_extinf = None
                                        continue
                                else:
                                    assigned_group = "Other"
                                
                                seen_streams.add(line)
                                
                                # Inject the custom group folder name
                                if 'group-title="' in current_extinf:
                                    fixed_extinf = re.sub(r'group-title="[^"]+"', f'group-title="{assigned_group}"', current_extinf)
                                else:
                                    fixed_extinf = re.sub(r'(#EXTINF:[-\d]+)', f'\\1 group-title="{assigned_group}"', current_extinf)
                                
                                # Store data for sorting later
                                if assigned_group not in playlist_data:
                                    playlist_data[assigned_group] = []
                                playlist_data[assigned_group].append((channel_name, fixed_extinf, line))
                                total_channels_count += 1
                            else:
                                if not channel_to_group_map:
                                    seen_streams.add(line)
                                    if "Other" not in playlist_data:
                                        playlist_data["Other"] = []
                                    playlist_data["Other"].append(("Uncategorized Stream", f'#EXTINF:-1 group-title="Other",Uncategorized Stream', line))
                                    total_channels_count += 1
                                    
                        current_extinf = None
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")

    # --- SORTING LOGIC ---
    # 1. Gather group names and sort them case-insensitively, keeping "Other" out for now
    all_groups = sorted([g for g in playlist_data.keys() if g.lower() != "other"], key=lambda s: s.lower())
    
    # 2. Append "Other" to the very end if it exists in our data
    if "Other" in playlist_data or "other" in [g.lower() for g in playlist_data.keys()]:
        other_key = next((g for g in playlist_data.keys() if g.lower() == "other"), "Other")
        all_groups.append(other_key)

    # 3. Compile final M3U file lines sequentially
    combined_lines = ["#EXTM3U\n"]
    
    for group in all_groups:
        # NATURAL SORT FIX: Sort purely on lowercase string value so spaces work correctly
        sorted_channels = sorted(
            playlist_data[group], 
            key=lambda x: x[0].lower().strip()
        )
        
        for channel_name, extinf, stream_url in sorted_channels:
            combined_lines.append(extinf + "\n")
            combined_lines.append(stream_url + "\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(combined_lines)
        
    print(f"Successfully generated sorted {output_file} with {total_channels_count} channels.")

if __name__ == "__main__":
    main()
