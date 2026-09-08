import json
import datetime
from typing import List, Dict, Any

# Bitmask slot definitions according to PRD v2.0 (5-bit protocol)
TIME_SLOTS = [
    { "slot": 1, "name": "第1大节", "time": "08:20-10:00", "mask": 1 },
    { "slot": 2, "name": "第2大节", "time": "10:20-12:00", "mask": 2 },
    { "slot": 3, "name": "第3大节", "time": "14:00-15:40", "mask": 4 },
    { "slot": 4, "name": "第4大节", "time": "16:00-17:40", "mask": 8 },
    { "slot": 5, "name": "第5大节", "time": "18:30-20:10", "mask": 16 }
]

TARGET_BUILDINGS = ["第一公共教学楼", "第二公共教学楼"]

def parse_slot_to_mask(occupied_slots: List[int]) -> int:
    """
    Converts 1-indexed big slot numbers (1..5) to a 5-bit mask.
    Slot 1 -> Bit0 (1), Slot 2 -> Bit1 (2), Slot 3 -> Bit2 (4), Slot 4 -> Bit3 (8), Slot 5 -> Bit4 (16).
    """
    mask = 0
    for slot in occupied_slots:
        if 1 <= slot <= 5:
            mask |= (1 << (slot - 1))
    return mask

def is_classroom_free(occupied_mask: int, slot_mask: int) -> bool:
    """
    Checks if a classroom is free during a target time slot or combined slots.
    Returns True if (occupied_mask & slot_mask) == 0.
    """
    return (occupied_mask & slot_mask) == 0

def format_today_data(
    classrooms_raw: List[Dict[str, Any]],
    term: str = "2026-2027-1",
    updated_at: str = None
) -> Dict[str, Any]:
    """
    Cleans raw classroom data and generates standardized JSON structure matching PRD v2.0.
    """
    if updated_at is None:
        updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    processed_classrooms = []
    for item in classrooms_raw:
        building_name = item.get("b", item.get("building"))
        if building_name not in TARGET_BUILDINGS:
            continue

        room_no = item.get("r", item.get("room"))
        occ_val = item.get("occ")
        if occ_val is None and ("busy" in item or "occupied_slots" in item):
            busy_list = item.get("busy", item.get("occupied_slots", []))
            occ_val = parse_slot_to_mask(busy_list)
        elif occ_val is None:
            occ_val = 0

        processed_classrooms.append({
            "id": f"{building_name}-{room_no}",
            "b": building_name,
            "r": room_no,
            "c": item.get("c", item.get("capacity", 120)),
            "t": item.get("t", item.get("type", "多媒体")),
            "occ": int(occ_val)
        })

    return {
        "updated_at": updated_at,
        "buildings": TARGET_BUILDINGS,
        "time_slots": TIME_SLOTS,
        "classrooms": processed_classrooms
    }

if __name__ == "__main__":
    print("Testing 5-Bit Bitmask Parser...")
    mask_1_2 = parse_slot_to_mask([1, 2])
    print(f"Slots 1, 2 mask: {mask_1_2} (Expected: 3)")
    print(f"Is Slot 1 free when occ is {mask_1_2}? {is_classroom_free(mask_1_2, TIME_SLOTS[0]['mask'])}")
    print(f"Is Slot 3 free when occ is {mask_1_2}? {is_classroom_free(mask_1_2, TIME_SLOTS[2]['mask'])}")
