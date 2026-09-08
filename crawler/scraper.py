import os
import sys

# Redirect to fetch_rooms.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_rooms import build_today_json

if __name__ == "__main__":
    build_today_json()
