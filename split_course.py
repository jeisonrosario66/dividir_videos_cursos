import os
import re
import subprocess
import sys

# ---------- utils ----------
def time_to_seconds(t):
    parts = [int(p) for p in t.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0

def clean_title(title):
    return re.sub(r"[^\w\- ]", "", title).strip().replace(" ", "_")

# ---------- parsing ----------
def parse_content(content_path):
    volumes = {}
    current_volume = None

    with open(content_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            vol_match = re.match(r"Volume (\d+)", line, re.IGNORECASE)
            if vol_match:
                current_volume = int(vol_match.group(1))
                volumes[current_volume] = []
                continue

            if "\t" in line and current_volume:
                try:
                    title, times = line.split("\t")
                    start = times.split("-")[0].strip().replace("+", "")

                    volumes[current_volume].append({
                        "title": clean_title(title),
                        "start": time_to_seconds(start)
                    })
                except:
                    continue

    return volumes

# ---------- file detection ----------
def has_content_file(folder):
    for f in os.listdir(folder):
        if f.lower() in ["content.txt", "timing.txt"]:
            return os.path.join(folder, f)
    return None

def find_video_file(folder, volume):
    for f in os.listdir(folder):
        name = f.lower()

        if not (name.endswith(".mp4") or name.endswith(".mkv")):
            continue

        # detectar número de volumen de forma flexible
        if str(volume) in name:
            return os.path.join(folder, f)

    return None

# ---------- splitting ----------
def split_videos(base_path, volumes):
    for vol, chapters in volumes.items():
        input_file = find_video_file(base_path, vol)

        if not input_file:
            raise Exception(f"No se encontró video para volumen {vol}")

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

            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            if result.returncode != 0:
                raise Exception(f"Error en ffmpeg en volumen {vol}, capítulo {i+1}")

# ---------- core ----------
def process_course(folder):
    content_path = has_content_file(folder)

    if not content_path:
        return False, "No content file"

    try:
        volumes = parse_content(content_path)

        if not volumes:
            return False, "No se detectaron volúmenes"

        split_videos(folder, volumes)
        return True, "OK"

    except Exception as e:
        return False, str(e)

def find_courses(root_path):
    courses = []
    for root, dirs, files in os.walk(root_path):
        if any(f.lower() in ["content.txt", "timing.txt"] for f in files):
            courses.append(root)
    return courses

# ---------- main ----------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python split_course.py /ruta/base")
        sys.exit(1)

    base_path = sys.argv[1]

    success = []
    failed = []

    courses = find_courses(base_path)

    print(f"🔍 Encontrados {len(courses)} cursos\n")

    for course in courses:
        print(f"▶️ Procesando: {course}")

        ok, msg = process_course(course)

        if ok:
            success.append(course)
            print("   ✅ OK\n")
        else:
            failed.append((course, msg))
            print(f"   ❌ ERROR: {msg}\n")

    # ---------- resumen ----------
    print("\n===== RESUMEN =====\n")

    print(f"✅ Exitosos ({len(success)}):")
    for s in success:
        print(f"  - {s}")

    print(f"\n❌ Fallidos ({len(failed)}):")
    for f, msg in failed:
        print(f"  - {f} → {msg}")