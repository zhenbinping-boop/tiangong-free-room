import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser import parse_slot_to_mask, is_classroom_free, TIME_SLOTS, format_today_data
from rooms_parser import records_from_spare_rooms, records_from_slot_rooms


def _bld(rooms, name="第一公共教学楼"):
    """构造一个 spareroomObjList 元素。"""
    return {
        "acmcBuildingName": name,
        "claroom": [{"classroom": r, "classNumberOfSeats": "100"} for r in rooms],
    }


def _occ_by_room(records):
    return {r["room"]: sum(1 << (s - 1) for s in r["busy"]) for r in records}

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

class TestMultiPeriodQuery(unittest.TestCase):
    """
    多节合并查询（/today/1,2 取交集）必须等价于此前的逐小节查询。

    实测依据（2026-09-16，西区第一公共教学楼 89 间）：两者 occ 掩码 0 处差异。
    """

    def test_slot_query_matches_period_query(self):
        # 每一节都有非空返回，两种算法应当完全一致
        period_rooms = {
            1: [_bld(["A101", "B201"])], 2: [_bld(["A101"])],
            3: [_bld(["A101"])], 4: [_bld(["A101"])],
            5: [_bld(["B201"])], 6: [_bld(["B201"])],
            7: [_bld(["A101"])], 8: [_bld(["A101"])],
            9: [_bld(["A101"])], 10: [_bld(["A101"])],
        }
        slot_rooms = {
            1: [_bld(["A101"])],          # 第1,2节都空闲 → 只剩 A101
            2: [_bld(["A101"])],          # 第3,4节
            3: [_bld(["B201"])],          # 第5,6节
            4: [_bld(["A101"])],          # 第7,8节
            5: [_bld(["A101"])],          # 第9,10节
        }
        by_period = _occ_by_room(records_from_spare_rooms(period_rooms))
        by_slot = _occ_by_room(records_from_slot_rooms(slot_rooms))
        self.assertEqual(by_period, by_slot)
        # A101 只占用大节3；B201 占用大节 1,2,4,5
        self.assertEqual(by_slot["A101"], 4)
        self.assertEqual(by_slot["B201"], 1 | 2 | 8 | 16)

    def test_full_day_free_has_empty_busy(self):
        slot_rooms = {s: [_bld(["A101"])] for s in range(1, 6)}
        recs = records_from_slot_rooms(slot_rooms)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["busy"], [])
        self.assertEqual(recs[0]["capacity"], 100)

    def test_empty_slot_is_treated_as_occupied(self):
        """
        某个大节的合并查询返回空 = 该大节没有一间教室全程空闲 → 全部记为占用。

        这是与旧逐节实现的**有意差异**：旧实现遇到"整小节无返回"会按未知处理
        （不置位，偏宽松）；合并查询无法区分"整节无空闲"与"接口异常"，
        因此统一按占用处理，更保守，也更接近真实。
        """
        slot_rooms = {
            1: [_bld(["A101"])],
            2: [],                    # 大节2 无空闲
            3: [_bld(["A101"])],
            4: [_bld(["A101"])],
            5: [_bld(["A101"])],
        }
        recs = records_from_slot_rooms(slot_rooms)
        self.assertEqual(recs[0]["busy"], [2])

        # 同一份数据的逐节版本：第3、4节整节无返回 → 旧逻辑按未知处理，不置位
        period_rooms = {
            1: [_bld(["A101"])], 2: [_bld(["A101"])],
            3: [], 4: [],
            5: [_bld(["A101"])], 6: [_bld(["A101"])],
            7: [_bld(["A101"])], 8: [_bld(["A101"])],
            9: [_bld(["A101"])], 10: [_bld(["A101"])],
        }
        old = _occ_by_room(records_from_spare_rooms(period_rooms))
        self.assertNotIn(2, [s for s in range(1, 6) if old["A101"] & (1 << (s - 1))])

    def test_building_and_room_names_preserved(self):
        slot_rooms = {1: [_bld(["A101"], name="教学B")], 2: [], 3: [], 4: [], 5: []}
        recs = records_from_slot_rooms(slot_rooms)
        self.assertEqual(recs[0]["building"], "教学B")
        self.assertEqual(recs[0]["room"], "A101")


if __name__ == "__main__":
    unittest.main()
