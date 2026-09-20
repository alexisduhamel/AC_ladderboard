from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

try:
    import pylnk3

    HAS_PYLNK = True
except ImportError:
    HAS_PYLNK = False

# Optional: Set your Assetto Corsa root path here to read friendly names from ui_car.json / ui_track.json
AC_ROOT_PATH = None  # Example: Path(r"C:\Program Files (x86)\Steam\steamapps\common\assettocorsa")


def resolve_ini_path(filepath):
    """Resolves a file path, handling Windows .lnk shortcuts if necessary."""
    if filepath.suffix.lower() == ".lnk":
        if not HAS_PYLNK:
            raise ImportError(
                f"Found shortcut {filepath.name}, but 'pylnk3' is not installed. "
                "Install it via 'pip install pylnk3' to parse .lnk shortcuts."
            )
        shortcut = pylnk3.parse(str(filepath))
        target_path = Path(shortcut.path)
        if not target_path.exists():
            raise FileNotFoundError(
                f"Shortcut {filepath.name} points to non-existent path:"
                f" {target_path}"
            )
        return target_path
    return filepath


def get_car_display_name(car_folder):
    """Reads the friendly car name from ui/ui_car.json if AC_ROOT_PATH is set."""
    if AC_ROOT_PATH:
        ui_json = AC_ROOT_PATH / "content" / "cars" / car_folder / "ui" / "ui_car.json"
        if ui_json.exists():
            try:
                data = json.loads(ui_json.read_text(encoding="utf-8", errors="ignore"))
                brand = data.get("brand", "")
                name = data.get("name", "")
                if brand and name:
                    return f"{brand} {name}"
                elif name:
                    return name
            except Exception:
                pass
    return car_folder.replace("_", " ").title()


def get_track_display_name(track_and_layout):
    """Reads the friendly track and layout name from ui files if AC_ROOT_PATH is set."""
    if AC_ROOT_PATH:
        parts = track_and_layout.split("-", 1)
        track_name = parts[0]
        layout_name = parts[1] if len(parts) > 1 else None

        track_dir = AC_ROOT_PATH / "content" / "tracks" / track_name
        if layout_name:
            ui_json = track_dir / "ui" / layout_name / "ui_track.json"
            if not ui_json.exists():
                ui_json = track_dir / "ui" / f"{layout_name}.json"
        else:
            ui_json = track_dir / "ui" / "ui_track.json"

        if ui_json.exists():
            try:
                data = json.loads(ui_json.read_text(encoding="utf-8", errors="ignore"))
                t_name = data.get("name", track_name)
                l_name = data.get("layout", layout_name)
                if l_name:
                    return f"{t_name} - {l_name}"
                return t_name
            except Exception:
                pass

    return track_and_layout.replace("_", " ").title()


def parse_ini(filepath):
    """Parses an Assetto Corsa personalbest.ini file, keeping only GT3 cars.

    Returns a dict mapping track to a dict of (car, time, date).
    """
    records = {}
    resolved_path = resolve_ini_path(filepath)
    if not resolved_path.exists():
        return records

    with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
        current_car = None
        current_track = None
        current_time = float("inf")
        current_date = 0

        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue

            match = re.match(r"^\[(.+?)@(.+)\]$", line)
            if match:
                # Si on change de bloc, on sauvegarde le précédent s'il est valide
                if current_track:
                    if current_track not in records or current_time < records[current_track]["time"]:
                        records[current_track] = {
                            "car": current_car,
                            "time": current_time,
                            "date": current_date,
                        }

                car_candidate, track_candidate = match.groups()

                # Filtrer uniquement les voitures dont le nom contient "GT3"
                if "gt3" in car_candidate.lower():
                    current_car = car_candidate
                    current_track = track_candidate
                    current_time = float("inf")
                    current_date = 0
                else:
                    current_car = None
                    current_track = None
                    current_time = float("inf")
                    current_date = 0

            elif current_track and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip().upper()
                val = val.strip()
                if key == "TIME":
                    try:
                        current_time = int(val)
                    except ValueError:
                        pass
                elif key == "DATE":
                    try:
                        current_date = int(val)
                    except ValueError:
                        pass

        # Ne pas oublier le dernier bloc du fichier
        if current_track:
            if current_track not in records or current_time < records[current_track]["time"]:
                records[current_track] = {
                    "car": current_car,
                    "time": current_time,
                    "date": current_date,
                }

    return records


def format_time(ms_int):
    """Converts milliseconds integer into mm:ss.ms string."""
    if ms_int == float("inf"):
        return "N/A"
    total_seconds = ms_int / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:06.3f}"


def format_date(timestamp_ms):
    """Converts a Unix epoch timestamp in milliseconds to YYYY-MM-DD."""
    if not timestamp_ms:
        return "N/A"
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def main():
    pb_dir = Path("./pb")
    output_file = Path("index.html")

    ini_files = list(pb_dir.glob("*.ini")) + list(pb_dir.glob("*.lnk"))

    if len(ini_files) < 2:
        print(
            "Error: Expected at least two personalbest files (ini or lnk) in the"
            " './pb/' directory to compare."
        )
        return

    user1_path, user2_path = ini_files[0], ini_files[1]
    user1_name = user1_path.stem
    user2_name = user2_path.stem

    try:
        user1_data = parse_ini(user1_path)
        user2_data = parse_ini(user2_path)
    except Exception as e:
        print(f"Error reading user files: {e}")
        if not HAS_PYLNK:
            print("Tip: If your files are .lnk shortcuts, run: pip install pylnk3")
        return

    all_tracks = set(user1_data.keys()).union(set(user2_data.keys()))

    table_rows = []
    if not all_tracks:
        table_rows.append(
            '<tr><td colspan="5" style="text-align: center;">No GT3 track records'
            " found between the two users.</td></tr>"
        )
    else:
        for track in sorted(all_tracks):
            u1_info = user1_data.get(track, {"car": "", "time": float("inf"), "date": 0})
            u2_info = user2_data.get(track, {"car": "", "time": float("inf"), "date": 0})

            if u1_info["time"] <= u2_info["time"]:
                best_car = u1_info["car"]
                best_time = format_time(u1_info["time"])
                best_date = format_date(u1_info["date"])
                sort_time_val = u1_info["time"]
                sort_date_val = u1_info["date"]
                holder = f"<strong>{user1_name}</strong>"
            else:
                best_car = u2_info["car"]
                best_time = format_time(u2_info["time"])
                best_date = format_date(u2_info["date"])
                sort_time_val = u2_info["time"]
                sort_date_val = u2_info["date"]
                holder = f"<strong>{user2_name}</strong>"

            track_display = get_track_display_name(track)
            car_display = get_car_display_name(best_car) if best_car else "N/A"

            table_rows.append(
                f"<tr>"
                f'<td data-sort="{track}">{track_display}</td>'
                f'<td data-sort="{best_car}">{car_display}</td>'
                f'<td data-sort="{sort_time_val}">{best_time}</td>'
                f'<td data-sort="{sort_date_val}">{best_date}</td>'
                f"<td>{holder}</td>"
                f"</tr>"
            )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Assetto Corsa GT3 Shared Leaderboard - By Track</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 40px;
            background-color: #0d1117;
            color: #c9d1d9;
        }}
        h1 {{
            font-size: 1.5rem;
            border-bottom: 1px solid #30363d;
            padding-bottom: 0.3rem;
        }}
        p.subtitle {{
            color: #8b949e;
            margin-bottom: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            overflow: hidden;
        }}
        th, td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid #30363d;
        }}
        th {{
            background-color: #21262d;
            color: #f0f6fc;
            cursor: pointer;
            user-select: none;
            position: relative;
        }}
        th:hover {{
            background-color: #30363d;
        }}
        th::after {{
            content: " ↕";
            font-size: 0.8rem;
            color: #8b949e;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        tr:hover td {{
            background-color: #1f242c;
        }}
        code {{
            font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
            background-color: rgba(110,118,129,0.4);
            padding: 0.2em 0.4em;
            border-radius: 6px;
            font-size: 85%;
        }}
    </style>
</head>
<body>
    <h1>Assetto Corsa GT3 Shared Leaderboard</h1>
    <p class="subtitle">Comparing: <strong>{user1_name}</strong> vs <strong>{user2_name}</strong> (Best GT3 lap time per track)</p>
    
    <table id="leaderboard">
        <thead>
            <tr>
                <th onclick="sortTable(0)">Track</th>
                <th onclick="sortTable(1)">Best Car</th>
                <th onclick="sortTable(2, true)">Best Lap Time</th>
                <th onclick="sortTable(3, true)">Date</th>
                <th onclick="sortTable(4)">Holder</th>
            </tr>
        </thead>
        <tbody>
            {"".join(table_rows)}
        </tbody>
    </table>

    <script>
    function sortTable(colIndex, isNumeric = false) {{
        const table = document.getElementById("leaderboard");
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.querySelectorAll("tr"));
        
        const currentDir = table.getAttribute("data-sort-dir") === "asc" ? "desc" : "asc";
        table.setAttribute("data-sort-dir", currentDir);

        rows.sort((a, b) => {{
            let cellA = a.cells[colIndex];
            let cellB = b.cells[colIndex];

            let valA = cellA.getAttribute("data-sort") !== null ? cellA.getAttribute("data-sort") : cellA.textContent.trim();
            let valB = cellB.getAttribute("data-sort") !== null ? cellB.getAttribute("data-sort") : cellB.textContent.trim();

            if (isNumeric) {{
                valA = parseFloat(valA) || 0;
                valB = parseFloat(valB) || 0;
            }} else {{
                valA = valA.toLowerCase();
                valB = valB.toLowerCase();
            }}

            if (valA < valB) return currentDir === "asc" ? -1 : 1;
            if (valA > valB) return currentDir === "asc" ? 1 : -1;
            return 0;
        }});

        rows.forEach(row => tbody.appendChild(row));
    }}
    </script>
</body>
</html>
"""

    output_file.write_text(html_content, encoding="utf-8")
    print(f"Interactive GT3 HTML leaderboard generated at {output_file.resolve()}")

    # Automatically commit and push index.html via Git
    try:
        subprocess.run(
            ["git", "add", str(output_file)], check=True, capture_output=True
        )
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], capture_output=True
        )
        if status.returncode != 0:
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "Auto-update GT3 leaderboard index.html via update_pb.py",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(["git", "push"], check=True, capture_output=True)
            print("Successfully committed and pushed index.html to GitHub.")
        else:
            print("No changes detected in index.html to commit.")
    except Exception as e:
        print(f"Git auto-commit/push skipped or failed: {e}")


if __name__ == "__main__":
    main()