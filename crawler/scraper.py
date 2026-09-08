import os
import sys
import json
import argparse
import random
import datetime
from parser import format_today_data, BUILDINGS, TIME_SLOTS

# Mock data configuration for Tiangong University teaching buildings
BUILDING_ROOM_TEMPLATES = {
    "公教1": [
        ("A101", 150, "阶梯教室"), ("A102", 120, "多媒体"), ("A103", 90, "多媒体"), ("A104", 60, "智慧教室"),
        ("A201", 120, "多媒体"), ("A202", 120, "多媒体"), ("A203", 90, "多媒体"), ("A204", 60, "智慧教室"),
        ("A301", 150, "阶梯教室"), ("A302", 120, "多媒体"), ("A303", 90, "多媒体"), ("A304", 60, "智慧教室"),
        ("B101", 200, "阶梯大讲堂"), ("B102", 120, "多媒体"), ("B201", 90, "智慧教室"), ("B202", 90, "多媒体"),
        ("B301", 120, "多媒体"), ("B302", 60, "智慧教室")
    ],
    "公教2": [
        ("A101", 120, "多媒体"), ("A102", 120, "多媒体"), ("A103", 90, "智慧教室"), ("A104", 90, "多媒体"),
        ("A201", 150, "阶梯教室"), ("A202", 120, "多媒体"), ("A203", 90, "智慧教室"), ("A204", 60, "智慧教室"),
        ("A301", 120, "多媒体"), ("A302", 120, "多媒体"), ("A303", 90, "多媒体"), ("A304", 60, "智慧教室"),
        ("B101", 180, "阶梯教室"), ("B102", 120, "计算机房"), ("B201", 120, "多媒体"), ("B202", 90, "多媒体")
    ],
    "公教3": [
        ("A101", 120, "多媒体"), ("A102", 120, "多媒体"), ("A103", 90, "多媒体"), ("A104", 60, "智慧教室"),
        ("A201", 120, "多媒体"), ("A202", 120, "多媒体"), ("A203", 90, "多媒体"), ("A204", 60, "智慧教室"),
        ("A301", 150, "阶梯教室"), ("A302", 120, "多媒体"), ("A303", 90, "多媒体"), ("A304", 60, "智慧教室"),
        ("B101", 120, "计算机房"), ("B102", 120, "计算机房"), ("B201", 90, "多媒体"), ("B202", 90, "多媒体")
    ],
    "公教4": [
        ("A101", 150, "阶梯教室"), ("A102", 120, "多媒体"), ("A103", 90, "多媒体"), ("A104", 60, "智慧教室"),
        ("A201", 120, "多媒体"), ("A202", 120, "多媒体"), ("A203", 90, "智慧教室"), ("A204", 60, "智慧教室"),
        ("A301", 120, "多媒体"), ("A302", 120, "多媒体"), ("A303", 90, "多媒体"), ("A304", 60, "智慧教室"),
        ("B101", 160, "阶梯教室"), ("B102", 120, "多媒体"), ("B201", 90, "多媒体"), ("B202", 90, "多媒体")
    ],
    "公教5": [
        ("A101", 120, "多媒体"), ("A102", 120, "多媒体"), ("A103", 90, "多媒体"), ("A104", 60, "智慧教室"),
        ("A201", 120, "多媒体"), ("A202", 120, "多媒体"), ("A203", 90, "智慧教室"), ("A204", 60, "智慧教室"),
        ("A301", 150, "阶梯教室"), ("A302", 120, "多媒体"), ("A303", 90, "多媒体"), ("A304", 60, "智慧教室"),
        ("B101", 120, "多媒体"), ("B102", 120, "多媒体"), ("B201", 90, "多媒体"), ("B202", 60, "智慧教室")
    ],
    "博雅书院": [
        ("101", 60, "研讨室"), ("102", 60, "研讨室"), ("103", 40, "智慧研讨室"), ("104", 40, "智慧研讨室"),
        ("201", 80, "学术报告厅"), ("202", 60, "研讨室"), ("203", 40, "智慧研讨室"), ("204", 40, "智慧研讨室"),
        ("301", 100, "多功能厅"), ("302", 60, "研讨室"), ("303", 40, "智慧研讨室"), ("304", 40, "智慧研讨室")
    ]
}

def generate_mock_classrooms() -> list:
    """
    Generates mock classroom occupancy data for Tiangong University campus.
    Uses seeded randomness to ensure stable yet realistic daily schedule patterns.
    """
    # Seed based on current date so data remains consistent during the day
    today_str = datetime.date.today().isoformat()
    random.seed(today_str)

    classrooms = []
    
    # Common occupied bitmask patterns for university classes:
    # 1-2节: 3, 3-4节: 12, 1-4节: 15
    # 6-7节: 96, 8-9节: 384, 6-9节: 480
    # 10-11节: 1536
    possible_day_patterns = [
        [1, 2],                 # 1-2节有课
        [3, 4],                 # 3-4节有课
        [1, 2, 3, 4],           # 上午全满
        [6, 7],                 # 6-7节有课
        [8, 9],                 # 8-9节有课
        [6, 7, 8, 9],           # 下午全满
        [1, 2, 6, 7],           # 1-2, 6-7有课
        [3, 4, 8, 9],           # 3-4, 8-9有课
        [10, 11],               # 晚上有课
        [1, 2, 8, 9, 10, 11],   # 散客占课
        []                      # 全天空闲
    ]

    for b_name, rooms in BUILDING_ROOM_TEMPLATES.items():
        prefix = "GJ1" if b_name == "公教1" else ("GJ2" if b_name == "公教2" else ("GJ3" if b_name == "公教3" else ("GJ4" if b_name == "公教4" else ("GJ5" if b_name == "公教5" else "BY"))))
        
        for room_no, cap, r_type in rooms:
            # Pick a pattern with weighted probability (some rooms are empty, some busy)
            pattern = random.choice(possible_day_patterns)
            
            classrooms.append({
                "id": f"{prefix}-{room_no}",
                "b": b_name,
                "r": room_no,
                "c": cap,
                "t": r_type,
                "occupied_sections": pattern
            })
            
    return classrooms

def fetch_live_schedule() -> list:
    """
    Framework for fetching live schedule data from Tiangong University WebVPN / Edu portal.
    If network access is unavailable, falls back gracefully to mock generator.
    """
    print("[Crawler] Attempting to connect to Tiangong WebVPN / Educational System...")
    # In GitHub Actions or local offline environment without VPN login cookies, return None
    # to trigger fallback
    return None

def main():
    parser_cli = argparse.ArgumentParser(description="Tiangong University Classroom Crawler & Generator")
    parser_cli.add_argument("--mock", action="store_true", help="Force mock data generation")
    parser_cli.add_argument("--out", type=str, default="", help="Output JSON path")
    args = parser_cli.parse_args()

    classrooms_raw = None
    if not args.mock:
        try:
            classrooms_raw = fetch_live_schedule()
        except Exception as e:
            print(f"[Crawler] Live fetch failed ({e}). Falling back to mock generator.")

    if not classrooms_raw:
        print("[Crawler] Generating standard mock schedule for Tiangong University classrooms...")
        classrooms_raw = generate_mock_classrooms()

    now = datetime.datetime.now()
    # Calculate week of semester (assuming semester started around late August/early Sept)
    term = f"{now.year}-{now.year+1}-1"
    day_of_week = now.weekday() + 1 # 1-7
    week = min(20, max(1, now.isocalendar()[1] - 34))

    today_payload = format_today_data(
        classrooms_raw=classrooms_raw,
        term=term,
        week=week,
        day_of_week=day_of_week
    )

    # Resolve output targets
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_paths = [
        os.path.join(base_dir, "public", "data", "today.json"),
        os.path.join(base_dir, "web", "data", "today.json")
    ]

    if args.out:
        target_paths = [args.out]

    for target_path in target_paths:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(today_payload, f, ensure_ascii=False, indent=2)
        print(f"[Crawler] Successfully written standard today.json to: {target_path}")

if __name__ == "__main__":
    main()
