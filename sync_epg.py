import os
import gzip
import shutil
import time
import urllib.request
import xml.etree.ElementTree as ET

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------

FILTER_FILE = "channels.txt"

EPG_SOURCE_URL = "https://iptv-org.github.io/epg/guides/all.xml.gz"

TEMP_GZ = "master_epg.xml.gz"
OUTPUT_XML = "family_epg.xml"
OUTPUT_GZ = "family_epg.xml.gz"

DOWNLOAD_RETRIES = 3


# -------------------------------------------------------
# Helper
# -------------------------------------------------------

def normalize(name):
    if not name:
        return ""

    return (
        name.upper()
        .replace("&", "AND")
        .replace("-", " ")
        .replace("_", " ")
        .strip()
    )


def download_file(url, filename):

    for attempt in range(1, DOWNLOAD_RETRIES + 1):

        try:
            print(f"Downloading ({attempt}/{DOWNLOAD_RETRIES})...")

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                with open(filename, "wb") as f:
                    shutil.copyfileobj(response, f)

            print("Download completed.")
            return True

        except Exception as e:

            print(e)

            if attempt != DOWNLOAD_RETRIES:
                time.sleep(5)

    return False


# -------------------------------------------------------
# Main
# -------------------------------------------------------

def main():

    if not os.path.exists(FILTER_FILE):
        print("channels.txt not found.")
        return

    # ---------------------------------------------------
    # Load wanted channels
    # ---------------------------------------------------

    wanted = set()

    with open(FILTER_FILE, encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if line.startswith(":"):
                continue

            wanted.add(normalize(line))

    print(f"Loaded {len(wanted)} wanted channels.")

    # ---------------------------------------------------
    # Download
    # ---------------------------------------------------

    if not download_file(EPG_SOURCE_URL, TEMP_GZ):
        print("Download failed.")
        return

    # ---------------------------------------------------
    # PASS 1
    #
    # Find channel IDs
    # ---------------------------------------------------

    print()
    print("PASS 1 : Finding matching channels...")

    allowed_ids = set()

    channel_count = 0

    with gzip.open(TEMP_GZ, "rb") as f:

        context = ET.iterparse(f, events=("end",))

        for event, elem in context:

            if elem.tag != "channel":
                continue

            channel_count += 1

            channel_id = elem.get("id")

            matched = False

            for dn in elem.findall("display-name"):

                text = normalize(dn.text)

                if not text:
                    continue

                for target in wanted:

                    if (
                        target == text
                        or target in text
                        or text in target
                    ):
                        matched = True
                        break

                if matched:
                    break

            if matched:
                allowed_ids.add(channel_id)

            elem.clear()

            if channel_count % 5000 == 0:
                print(f"Checked {channel_count:,} channels...")

    print()
    print(f"Matched {len(allowed_ids)} channel IDs.")

    if not allowed_ids:
        print("No channels matched.")
        return

    # ---------------------------------------------------
    # PASS 2
    # Build new XML
    # ---------------------------------------------------

    print()
    print("PASS 2 : Building filtered XML...")

    new_root = ET.Element("tv")

    programme_count = 0
    kept_programmes = 0

    with gzip.open(TEMP_GZ, "rb") as f:

        context = ET.iterparse(f, events=("start", "end"))

        event, root = next(context)

        new_root.attrib = root.attrib

        for event, elem in context:

            if event != "end":
                continue

            if elem.tag == "channel":

                cid = elem.get("id")

                if cid in allowed_ids:
                    new_root.append(elem)

                elem.clear()

            elif elem.tag == "programme":

                programme_count += 1

                if elem.get("channel") in allowed_ids:

                    kept_programmes += 1
                    new_root.append(elem)

                elem.clear()

                if programme_count % 100000 == 0:

                    print(
                        f"Processed {programme_count:,} programmes "
                        f"(kept {kept_programmes:,})"
                    )

    # ---------------------------------------------------
    # Write XML
    # ---------------------------------------------------

    print()
    print("Writing XML...")

    tree = ET.ElementTree(new_root)

    tree.write(
        OUTPUT_XML,
        encoding="utf-8",
        xml_declaration=True
    )

    # ---------------------------------------------------
    # Compress
    # ---------------------------------------------------

    print("Compressing...")

    with open(OUTPUT_XML, "rb") as src:
        with gzip.open(OUTPUT_GZ, "wb") as dst:
            shutil.copyfileobj(src, dst)

    # ---------------------------------------------------
    # Cleanup
    # ---------------------------------------------------

    if os.path.exists(OUTPUT_XML):
        os.remove(OUTPUT_XML)

    if os.path.exists(TEMP_GZ):
        os.remove(TEMP_GZ)

    print()
    print("----------------------------------------")
    print("Finished successfully.")
    print(f"Matched channels : {len(allowed_ids)}")
    print(f"Programmes kept  : {kept_programmes:,}")
    print(f"Output           : {OUTPUT_GZ}")
    print("----------------------------------------")


if __name__ == "__main__":
    main()
