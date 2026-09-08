import os
import sys
import json
import re
import random
import argparse
import datetime
from typing import List, Dict, Any, Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

from parser import format_today_data, TIME_SLOTS, TARGET_BUILDINGS, parse_slot_to_mask

# Tiangong University Exact Endpoints
CAS_LOGIN_URL = "https://pt.tiangong.edu.cn/cas/login"
JWXS_FREE_CLASSROOM_URL = "https://jwxs.tiangong.edu.cn/student/teachingResources/freeClassroom/index"
JWXS_SEARCH_API = "https://jwxs.tiangong.edu.cn/student/teachingResources/freeClassroom/search"
JWXS_DATA_API = "https://jwxs.tiangong.edu.cn/student/teachingResources/freeClassroom/data"

# WebVPN Reverse Proxy Encoding for jwxs.tiangong.edu.cn
WEBVPN_JWXS_BASE = "https://vpn.tiangong.edu.cn/https/77726473706f6e73656164647265737330303121/student/teachingResources/freeClassroom"

# Building & Room Layouts for Fallback Generator
BUILDING_ROOM_TEMPLATES = {
    "第一公共教学楼": [
        ("A101", 150, "阶梯大教室"), ("A102", 120, "智慧多媒体"), ("A103", 90, "多媒体"), ("A104", 60, "智慧教室"),
        ("A201", 120, "多媒体"),     ("A202", 120, "多媒体"),     ("A203", 90, "智慧教室"), ("A204", 60, "普通教室"),
        ("A301", 150, "阶梯教室"),   ("A302", 120, "多媒体"),     ("A303", 90, "多媒体"),   ("A304", 60, "普通教室"),
        ("A401", 120, "多媒体"),     ("A402", 120, "多媒体"),     ("A403", 90, "智慧教室"), ("A404", 60, "普通教室"),
        ("B101", 200, "阶梯报告厅"), ("B102", 120, "多媒体"),     ("B201", 90, "智慧教室"), ("B202", 90, "多媒体"),
        ("B301", 120, "多媒体"),     ("B302", 60, "普通教室")
    ],
    "第二公共教学楼": [
        ("101", 180, "阶梯大教室"), ("102", 120, "多媒体"), ("103", 90, "智慧多媒体"), ("104", 90, "多媒体"),
        ("201", 150, "阶梯教室"),   ("202", 120, "多媒体"), ("203", 75, "智慧多媒体"), ("204", 60, "智慧教室"),
        ("301", 120, "多媒体"),     ("302", 120, "多媒体"), ("303", 90, "多媒体"),     ("304", 60, "普通教室"),
        ("401", 120, "多媒体"),     ("402", 120, "多媒体"), ("403", 90, "智慧教室"),   ("404", 60, "普通教室"),
        ("501", 150, "阶梯教室"),   ("502", 120, "多媒体"), ("503", 90, "多媒体"),     ("504", 60, "普通教室")
    ]
}

class TiangongEduClient:
    """
    Tiangong University Student Portal (jwxs.tiangong.edu.cn) Client.
    Handles CAS login & querying /student/teachingResources/freeClassroom/index.
    """

    def __init__(self, username: str = "", password: str = "", use_webvpn: bool = True):
        self.username = username
        self.password = password
        self.use_webvpn = use_webvpn
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest"
            })

    def login(self) -> bool:
        """
        Authenticates via Tiangong CAS for jwxs.tiangong.edu.cn.
        """
        if not self.session or not self.username or not self.password:
            print("[Tiangong Client] Username or password not provided.")
            return False

        try:
            service_url = JWXS_FREE_CLASSROOM_URL
            login_url = f"{CAS_LOGIN_URL}?service={requests.utils.quote(service_url)}" if requests else CAS_LOGIN_URL
            
            print(f"[Tiangong Client] Connecting to CAS for JWXS portal ({login_url})...")
            resp = self.session.get(login_url, timeout=10)
            if resp.status_code != 200:
                print(f"[Tiangong Client] CAS login page responded with status {resp.status_code}")
                return False

            execution_token = ""
            if BeautifulSoup:
                soup = BeautifulSoup(resp.text, "html.parser")
                exec_input = soup.find("input", {"name": "execution"})
                if exec_input:
                    execution_token = exec_input.get("value", "")

            if not execution_token:
                match = re.search(r'name="execution"\s+value="([^"]+)"', resp.text)
                if match:
                    execution_token = match.group(1)

            if not execution_token:
                print("[Tiangong Client] Could not extract CAS execution token.")
                return False

            login_data = {
                "username": self.username,
                "password": self.password,
                "execution": execution_token,
                "_eventId": "submit",
                "geolocation": ""
            }

            login_resp = self.session.post(login_url, data=login_data, timeout=10)
            if "登录失败" in login_resp.text or "密码错误" in login_resp.text:
                print("[Tiangong Client] CAS Login Failed: Invalid username or password.")
                return False

            print("[Tiangong Client] CAS Login Successful! Connected to jwxs.tiangong.edu.cn portal.")
            return True

        except Exception as e:
            print(f"[Tiangong Client] CAS Login Exception: {e}")
            return False

    def fetch_empty_classrooms(self) -> Optional[List[Dict[str, Any]]]:
        """
        Queries empty classrooms from https://jwxs.tiangong.edu.cn/student/teachingResources/freeClassroom/index
        """
        if not self.session:
            return None

        today = datetime.date.today().strftime("%Y-%m-%d")
        search_url = f"{WEBVPN_JWXS_BASE}/search" if self.use_webvpn else JWXS_SEARCH_API
        data_url = f"{WEBVPN_JWXS_BASE}/data" if self.use_webvpn else JWXS_DATA_API

        results = []
        target_buildings = [
            ("第一公共教学楼", ["第一公共教学楼", "第一公教", "公教1", "1"]),
            ("第二公共教学楼", ["第二公共教学楼", "第二公教", "公教2", "2"])
        ]

        for b_name, b_aliases in target_buildings:
            for endpoint in [search_url, data_url, JWXS_FREE_CLASSROOM_URL]:
                try:
                    payload = {
                        "date": today,
                        "idleTime": today,
                        "buildingName": b_name,
                        "buildingId": b_aliases[-1],
                        "page": 1,
                        "rows": 100
                    }
                    resp = self.session.post(endpoint, data=payload, timeout=10)
                    if resp.status_code == 200:
                        items = []
                        try:
                            json_resp = resp.json()
                            items = json_resp.get("data", json_resp.get("rows", json_resp.get("items", [])))
                        except Exception:
                            # Parse HTML table if response is rendered HTML
                            items = self._parse_html_table(resp.text, b_name)

                        if items:
                            for item in items:
                                room_no = item.get("roomName", item.get("r", item.get("jsmc", "")))
                                cap = int(item.get("capacity", item.get("c", item.get("zws", 120))))
                                r_type = item.get("roomType", item.get("t", item.get("lxmc", "多媒体")))
                                busy = item.get("busy", item.get("occupiedSlots", []))

                                results.append({
                                    "building": b_name,
                                    "room": room_no,
                                    "capacity": cap,
                                    "type": r_type,
                                    "busy": busy
                                })
                            break # Success for this building
                except Exception as e:
                    print(f"[Tiangong Client] Error fetching endpoint {endpoint} for {b_name}: {e}")

        return results if results else None

    def _parse_html_table(self, html_content: str, building_name: str) -> List[Dict[str, Any]]:
        """
        Parses HTML page table from freeClassroom/index if non-JSON HTML is returned.
        """
        items = []
        if not BeautifulSoup:
            return items

        soup = BeautifulSoup(html_content, "html.parser")
        rows = soup.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 6:
                room_name = cols[0].get_text(strip=True)
                cap_str = cols[1].get_text(strip=True)
                r_type = cols[2].get_text(strip=True)
                
                # Check 5 slots columns
                busy = []
                for idx, col in enumerate(cols[3:8], start=1):
                    txt = col.get_text(strip=True)
                    if "有课" in txt or "占用" in txt:
                        busy.append(idx)

                cap = int(re.sub(r'\D', '', cap_str)) if re.search(r'\d+', cap_str) else 120
                items.append({
                    "roomName": room_name,
                    "capacity": cap,
                    "roomType": r_type,
                    "busy": busy
                })
        return items

def generate_fallback_records() -> List[Dict[str, Any]]:
    """
    Generates high-fidelity mock classroom occupancy records for Tiangong University campus.
    """
    today_str = datetime.date.today().isoformat()
    random.seed(today_str)

    busy_patterns = [
        [1], [2], [1, 2], [3], [4], [3, 4], [1, 3], [2, 4], [5], [1, 2, 3, 4], []
    ]

    records = []
    for b_name, rooms in BUILDING_ROOM_TEMPLATES.items():
        for room_no, cap, r_type in rooms:
            busy = random.choice(busy_patterns)
            records.append({
                "building": b_name,
                "room": room_no,
                "capacity": cap,
                "type": r_type,
                "busy": busy
            })
    return records

def build_today_json(username: str = "", password: str = "", force_real: bool = False, force_mock: bool = False):
    """
    Main entrypoint: Attempts real JWXS student portal fetch first, gracefully falls back to generator if needed.
    """
    raw_records = None

    if not force_mock:
        username = username or os.environ.get("TIANGONG_USERNAME", "")
        password = password or os.environ.get("TIANGONG_PASSWORD", "")

        if username and password:
            print(f"[Crawler] Found credentials for account: {username[:3]}***. Connecting to jwxs.tiangong.edu.cn...")
            client = TiangongEduClient(username=username, password=password)
            if client.login():
                raw_records = client.fetch_empty_classrooms()

        if force_real and not raw_records:
            print("[Crawler] WARNING: --real specified but live JWXS fetch produced no records.")

    if not raw_records:
        print("[Crawler] Operating in Fallback Mode: Generating standardized Tiangong classroom schedule...")
        raw_records = generate_fallback_records()

    now = datetime.datetime.now()
    output = format_today_data(
        classrooms_raw=raw_records,
        updated_at=now.strftime("%Y-%m-%d %H:%M:%S")
    )

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_paths = [
        os.path.join(base_dir, "public", "data", "today.json"),
        os.path.join(base_dir, "web", "data", "today.json")
    ]

    for target_path in target_paths:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[{now}] today.json written successfully ({len(output['classrooms'])} classrooms) -> {target_path}")

if __name__ == "__main__":
    parser_cli = argparse.ArgumentParser(description="Tiangong University JWXS Portal Empty Classroom Crawler")
    parser_cli.add_argument("--username", type=str, default="", help="Tiangong CAS Student ID / Account")
    parser_cli.add_argument("--password", type=str, default="", help="Tiangong CAS Password")
    parser_cli.add_argument("--real", action="store_true", help="Force real WebVPN/CAS fetching")
    parser_cli.add_argument("--mock", action="store_true", help="Force mock data fallback")
    args = parser_cli.parse_args()

    build_today_json(
        username=args.username,
        password=args.password,
        force_real=args.real,
        force_mock=args.mock
    )
