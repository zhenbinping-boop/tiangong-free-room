import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser import parse_slot_to_mask, is_classroom_free, TIME_SLOTS, format_today_data

class Test5BitBitmaskProtocol(unittest.TestCase):

    def test_parse_slot_to_mask(self):
        # 5-bit protocol:
        # Slot 1: Bit0 (val 1)
        # Slot 2: Bit1 (val 2)
        # Slot 3: Bit2 (val 4)
        # Slot 4: Bit3 (val 8)
        # Slot 5: Bit4 (val 16)
        self.assertEqual(parse_slot_to_mask([1]), 1)
        self.assertEqual(parse_slot_to_mask([2]), 2)
        self.assertEqual(parse_slot_to_mask([1, 2]), 3)
        self.assertEqual(parse_slot_to_mask([3]), 4)
        self.assertEqual(parse_slot_to_mask([4]), 8)
        self.assertEqual(parse_slot_to_mask([5]), 16)
        self.assertEqual(parse_slot_to_mask([1, 2, 3, 4, 5]), 31)

    def test_is_classroom_free(self):
        # Classroom with Slots 1, 2 occupied (occ = 3)
        occ = parse_slot_to_mask([1, 2])
        
        # Slot 1 (mask=1): occupied -> free is False
        self.assertFalse(is_classroom_free(occ, TIME_SLOTS[0]["mask"]))
        # Slot 2 (mask=2): occupied -> free is False
        self.assertFalse(is_classroom_free(occ, TIME_SLOTS[1]["mask"]))
        # Slot 3 (mask=4): free -> free is True
        self.assertTrue(is_classroom_free(occ, TIME_SLOTS[2]["mask"]))
        # Slot 4 (mask=8): free -> free is True
        self.assertTrue(is_classroom_free(occ, TIME_SLOTS[3]["mask"]))
        # Slot 5 (mask=16): free -> free is True
        self.assertTrue(is_classroom_free(occ, TIME_SLOTS[4]["mask"]))

    def test_full_day_free(self):
        occ = 0
        full_day_mask = 31
        self.assertTrue(is_classroom_free(occ, full_day_mask))
        for slot in TIME_SLOTS:
            self.assertTrue(is_classroom_free(occ, slot["mask"]))

    def test_full_day_occupied(self):
        occ = 31
        full_day_mask = 31
        self.assertFalse(is_classroom_free(occ, full_day_mask))
        for slot in TIME_SLOTS:
            self.assertFalse(is_classroom_free(occ, slot["mask"]))

    def test_format_today_data(self):
        raw_data = [
            {
                "building": "第一公共教学楼",
                "room": "A101",
                "capacity": 120,
                "type": "智慧多媒体",
                "busy": [1, 2]
            },
            {
                "building": "博雅书院", # Out of target scope
                "room": "101",
                "capacity": 60,
                "type": "研讨室",
                "busy": []
            }
        ]
        formatted = format_today_data(raw_data)
        self.assertEqual(len(formatted["classrooms"]), 1)
        self.assertEqual(formatted["classrooms"][0]["b"], "第一公共教学楼")
        self.assertEqual(formatted["classrooms"][0]["occ"], 3)
        self.assertEqual(len(formatted["time_slots"]), 5)

if __name__ == "__main__":
    unittest.main()
