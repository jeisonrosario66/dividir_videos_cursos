import os
import re
import subprocess
import sys

def time_to_seconds(t):
    parts = [int(p) for p in t.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0

def parse_content(content_path):
    volumes = {}
    current_volume = None

    with open(content_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            vol_match = re.match(r"Volume (\d+)", line)
            if vol_match:
                current_volume = int(vol_match.group(1))
                volumes[current_volume] = []
                continue

            if "\t" in line and current_volume:
                title, times = line.split("\t")

                start = times.split("-")[0].strip().replace("+", "")

                volumes[current_volume].append({
                    "title": re.sub(r"[^\w\- ]", "", title).strip().replace(" ", "_"),
                    "start": time_to_seconds(start)
                })

    return volumes

def find_video_file(folder, volume):
    # busca archivo que termine en "X.mp4"
    for f in os.listdir(folder):
        if f.endswith(".mp4") and f.strip().endswith(f"{volume}.mp4"):
            return os.path.join(folder, f)
    return None

def split_videos(base_path, volumes):
    for vol, chapters in volumes.items():
        input_file = find_video_file(base_path, vol)

        if not input_file:
            print(f"❌ No se encontró video para volumen {vol}")
            continue

        output_dir = os.path.join(base_path, f"volume_{vol}")
        os.makedirs(output_dir, exist_ok=True)

        for i in range(len(chapters)):
            start = chapters[i]["start"]
            title = chapters[i]["title"]

            if i + 1 < len(chapters):
                end = chapters[i + 1]["start"]
                duration = end - start
                cmd = [
                    "ffmpeg", "-y",
                    "-i", input_file,
                    "-ss", str(start),
                    "-t", str(duration),
                    "-c", "copy",
                    os.path.join(output_dir, f"{i+1:02d}_{title}.mp4")
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", input_file,
                    "-ss", str(start),
                    "-c", "copy",
                    os.path.join(output_dir, f"{i+1:02d}_{title}.mp4")
                ]

            print("▶️", " ".join(cmd))
            subprocess.run(cmd)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python split_course.py /ruta/a/carpeta")
        sys.exit(1)

    base_path = sys.argv[1]
    content_path = os.path.join(base_path, "content.txt")

    if not os.path.exists(content_path):
        print("❌ No se encontró content.txt")
        sys.exit(1)

    volumes = parse_content(content_path)
    split_videos(base_path, volumes)