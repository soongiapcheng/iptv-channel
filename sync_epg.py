import os
import gzip
import urllib.request
import xml.etree.ElementTree as ET

def main():
    filter_file = "channels.txt"
    # A reliable public global EPG repository source
    epg_source_url = "https://iptv-org.github.io/epg/guides/all.xml.gz" 
    output_xml = "family_epg.xml"
    output_gz = "family_epg.xml.gz"

    if not os.path.exists(filter_file):
        print("channels.txt not found. Cannot filter EPG.")
        return

    # 1. Read target channel names from your config file
    allowed_channels = set()
    with open(filter_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith(":"):
                allowed_channels.add(line.upper())

    print(f"Loaded {len(allowed_channels)} target channels for EPG matching.")

    # 2. Download the compressed master EPG file
    print(f"Downloading master EPG archive from: {epg_source_url}")
    temp_gz = "master_epg.xml.gz"
    try:
        req = urllib.request.Request(epg_source_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response, open(temp_gz, 'wb') as out_file:
            out_file.write(response.read())
    except Exception as e:
        print(f"Failed to download EPG source: {e}")
        return

    # 3. Parse and filter the XML contents sequentially to conserve memory
    print("Filtering EPG data down to your target channel list...")
    try:
        with gzip.open(temp_gz, 'rb') as f:
            # We parse the XML tree structure dynamically
            context = ET.iterparse(f, events=('start', 'end'))
            event, root = next(context) # Get root element (<tv>)

            # Create a brand new matching tree template
            new_root = ET.Element("tv", root.attrib)
            
            # Map elements out safely
            for event, elem in context:
                if event == 'end':
                    if elem.tag == 'channel':
                        # Match channel definitions
                        display_name = elem.find('display-name')
                        if display_name is not None and display_name.text.upper() in allowed_channels:
                            new_root.append(elem)
                        else:
                            root.clear() # Clear unused memory footprints instantly
                    elif elem.tag == 'programme':
                        # Match scheduled guide programs by channel ID
                        channel_id = elem.get('channel')
                        # Check if this program belongs to an allowed channel name fragment
                        if channel_id and any(allowed in channel_id.upper() for allowed in allowed_channels):
                            new_root.append(elem)
                        else:
                            root.clear()

        # 4. Save the filtered outputs
        print(f"Writing matching structures to {output_xml}...")
        tree = ET.ElementTree(new_root)
        tree.write(output_xml, encoding="utf-8", xml_declaration=True)

        # 5. Compress into .gz format (Media players like Tivimate/iPlayTV prefer compressed EPGs)
        print(f"Compressing file to {output_gz}...")
        with open(output_xml, 'rb') as f_in, gzip.open(output_gz, 'wb') as f_out:
            f_out.writelines(f_in)
            
        # Clean up uncompressed clutter
        if os.path.exists(temp_gz): os.remove(temp_gz)
        if os.path.exists(output_xml): os.remove(output_xml)
        print("EPG Integration completely finished successfully!")

    except Exception as e:
        print(f"Error parsing EPG data stream: {e}")

if __name__ == "__main__":
    main()
