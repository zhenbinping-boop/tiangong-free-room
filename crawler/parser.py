import json
import datetime
from typing import List, Dict, Any

# Bitmask slot definitions according to PRD
TIME_SLOTS = [
    { "slot": 1, "name": "第1-2节", "time": "08:00-09:35", "mask": 3 },
    { "slot": 2, "name": "第3-4节", "time": "09:55-11:30", "mask": 12 },
    { "slot": 3, "name": "第5节",   "time": "11:35-12:20", "mask": 16 },
    { "slot": 4, "name": "第6-7节", "time": "13:30-15:05", "mask": 96 },
    { "slot": 5, "name": "第8-9节", "time": "15:25-17:00", "mask": 384 },
    { "slot": 6, "name": "第10-11节","time": "18:30-20:05", "mask": 1536 }
]

BUILDINGS = ["公教1", "公教2", "公教3", "公教4", "公教5", "博雅书院"]

def sections_to_bitmask(sections: List[int]) -> int:
    """
    Converts 1-indexed section numbers (1..11) to integer bitmask.
    Section 1 maps to Bit0 (value 1), Section 2 maps to Bit1 (value 2), ..., Section 11 maps to Bit10 (value 1024).
    """
    mask = 0
    for s in sections:
        if 1 <= s <= 11:
            mask |= (1 << (s - 1))
    return mask

def is_classroom_free(occupied_mask: int, slot_mask: int) -> bool:
    """
    Checks if a classroom is free during a target time slot or combined time slots.
    Returns True if (occupied_mask & slot_mask) == 0.
    """
    return (occupied_mask & slot_mask) == 0

def format_today_data(
    classrooms_raw: List[Dict[str, Any]],
    term: str = "2026-2027-1",
    week: int = 2,
    day_of_week: int = 2,
    updated_at: str = None
) -> Dict[str, Any]:
    """
    Cleans raw classroom data and generates standardized JSON structure matching PRD §3.2.
    """
    if updated_at is None:
        updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    processed_classrooms = []
    for item in classrooms_raw:
        # If item has raw section numbers, convert them to bitmask
        occ_val = item.get("occ")
        if occ_val is None and "occupied_sections" in item:
            occ_val = sections_to_bitmask(item["occupied_sections"])
        elif occ_val is None:
            occ_val = 0

        processed_classrooms.append({
            "id": item["id"],
            "b": item["b"],          # Building name
            "r": item["r"],          # Room number (e.g. A101)
            "c": item.get("c", 120), # Capacity
            "t": item.get("t", "多媒体"), # Type
            "occ": int(occ_val)      # Occupied Bitmask
        })

    return {
        "updated_at": updated_at,
        "term": term,
        "week": week,
        "day_of_week": day_of_week,
        "buildings": BUILDINGS,
        "time_slots": TIME_SLOTS,
        "classrooms": processed_classrooms
    }

if __name__ == "__main__":
    # Quick sanity check
    print("Testing Bitmask Parser...")
    mask_1_2 = sections_to_bitmask([1, 2])
    print(f"Sections 1, 2 bitmask: {mask_1_2} (Expected: 3)")
    print(f"Is 1-2 free when occ is {mask_1_2}? {is_classroom_free(mask_1_2, TIME_SLOTS[0]['mask'])}")
    print(f"Is 3-4 free when occ is {mask_1_2}? {is_classroom_free(mask_1_2, TIME_SLOTS[1]['mask'])}")
