import unittest
import sys
import os

# Add current directory to path so parser import works
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser import sections_to_bitmask, is_classroom_free, TIME_SLOTS, format_today_data

class TestBitmaskProtocol(unittest.TestCase):

    def test_sections_to_bitmask(self):
        # Bit0: Section 1 (val 1)
        # Bit1: Section 2 (val 2)
        # Bit2: Section 3 (val 4)
        # Bit3: Section 4 (val 8)
        self.assertEqual(sections_to_bitmask([1]), 1)
        self.assertEqual(sections_to_bitmask([1, 2]), 3)
        self.assertEqual(sections_to_bitmask([3, 4]), 12)
        self.assertEqual(sections_to_bitmask([5]), 16)
        self.assertEqual(sections_to_bitmask([6, 7]), 96)
        self.assertEqual(sections_to_bitmask([8, 9]), 384)
        self.assertEqual(sections_to_bitmask([10, 11]), 1536)
        self.assertEqual(sections_to_bitmask([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]), 2047)

    def test_is_classroom_free(self):
        # Classroom with sections 1, 2 occupied (occ = 3)
        occ = sections_to_bitmask([1, 2])
        
        # Slot 1 (1-2节, mask=3): occupied -> free should be False
        self.assertFalse(is_classroom_free(occ, TIME_SLOTS[0]["mask"]))
        
        # Slot 2 (3-4节, mask=12): free -> free should be True
        self.assertTrue(is_classroom_free(occ, TIME_SLOTS[1]["mask"]))
        
        # Combined check (Slots 1-2 & 3-4, mask = 3 | 12 = 15)
        combined_mask = TIME_SLOTS[0]["mask"] | TIME_SLOTS[1]["mask"]
        self.assertFalse(is_classroom_free(occ, combined_mask))

    def test_full_day_free(self):
        # Classroom with no courses (occ = 0)
        occ = 0
        full_day_mask = 2047
        self.assertTrue(is_classroom_free(occ, full_day_mask))
        for slot in TIME_SLOTS:
            self.assertTrue(is_classroom_free(occ, slot["mask"]))

    def test_full_day_occupied(self):
        # Classroom occupied all day (occ = 2047)
        occ = 2047
        full_day_mask = 2047
        self.assertFalse(is_classroom_free(occ, full_day_mask))
        for slot in TIME_SLOTS:
            self.assertFalse(is_classroom_free(occ, slot["mask"]))

    def test_format_today_data(self):
        raw_data = [
            {
                "id": "GJ1-A101",
                "b": "公教1",
                "r": "A101",
                "c": 120,
                "t": "多媒体",
                "occupied_sections": [1, 2, 6, 7, 10, 11]
            }
        ]
        formatted = format_today_data(raw_data)
        self.assertEqual(formatted["classrooms"][0]["occ"], 3 + 96 + 1536)  # 1635
        self.assertEqual(formatted["buildings"][0], "公教1")
        self.assertEqual(len(formatted["time_slots"]), 6)

if __name__ == "__main__":
    unittest.main()
