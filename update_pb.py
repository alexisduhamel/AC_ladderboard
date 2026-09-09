from datetime import datetime, timezone
import json
from pathlib import Path
import re

try:
  import pylnk3

  HAS_PYLNK = True
except ImportError:
  HAS_PYLNK = False

# Optional: Set your Assetto Corsa root path here to read friendly names from ui_car.json / ui_track.json
# Leave as None to use formatted folder names.
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
  # Fallback: Clean up internal name
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

  # Fallback: Clean up internal name
  return track_and_layout.replace("_", " ").title()


def parse_ini(filepath):
  """Parses an Assetto Corsa personalbest.ini file.

  Returns a dict mapping (car, track) to a dict of (time, date).
  """
  records = {}
  current_key = None

  resolved_path = resolve_ini_path(filepath)
  if not resolved_path.exists():
    return records

  with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
      line = line.strip()
      if not line or line.startswith(";"):
        continue

      match = re.match(r"^\[(.+?)@(.+)\]$", line)
      if match:
        car, track = match.groups()
        current_key = (car, track)
        if current_key not in records:
          records[current_key] = {"time": float("inf"), "date": 0}
      elif current_key and "=" in line:
        key, val = line.split("=", 1)
        key = key.strip().upper()
        val = val.strip()
        if key == "TIME":
          try:
            records[current_key]["time"] = int(val)
          except ValueError:
            pass
        elif key == "DATE":
          try:
            records[current_key]["date"] = int(val)
          except ValueError:
            pass

  return records


def format_time(ms_int):
  """Converts milliseconds integer into mm:ss.ms string."""
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

  common_keys = set(user1_data.keys()).intersection(set(user2_data.keys()))

  table_rows = []
  if not common_keys:
    table_rows.append(
        '<tr><td colspan="5" style="text-align: center;">No matching car and'
        " track combinations found between the two users.</td></tr>"
    )
  else:
    for car, track in sorted(common_keys):
      u1_t = user1_data[(car, track)]["time"]
      u1_d = user1_data[(car, track)]["date"]
      u2_t = user2_data[(car, track)]["time"]
      u2_d = user2_data[(car, track)]["date"]

      car_display = get_car_display_name(car)
      track_display = get_track_display_name(track)

      if u1_t <= u2_t:
        best_time = format_time(u1_t)
        best_date = format_date(u1_d)
        sort_time_val = u1_t
        sort_date_val = u1_d
        holder = f"<strong>{user1_name}</strong>"
      else:
        best_time = format_time(u2_t)
        best_date = format_date(u2_d)
        sort_time_val = u2_t
        sort_date_val = u2_d
        holder = f"<strong>{user2_name}</strong>"

      table_rows.append(
          f"<tr>"
          f'<td data-sort="{car}">{car_display}</td>'
          f'<td data-sort="{track}">{track_display}</td>'
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
    <title>Assetto Corsa Shared Leaderboard</title>
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
    <h1>Assetto Corsa Shared Leaderboard</h1>
    <p class="subtitle">Comparing: <strong>{user1_name}</strong> vs <strong>{user2_name}</strong> (Click column headers to sort)</p>
    
    <table id="leaderboard">
        <thead>
            <tr>
                <th onclick="sortTable(0)">Car</th>
                <th onclick="sortTable(1)">Track</th>
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
  print(f"Interactive HTML leaderboard generated at {output_file.resolve()}")


if __name__ == "__main__":
  main()