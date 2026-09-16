import json
import re
import datetime
from typing import List, Dict, Any, Optional

# Bitmask slot definitions according to PRD v2.0 (5-bit protocol)
TIME_SLOTS = [
    { "slot": 1, "name": "第1大节", "time": "08:20-10:00", "mask": 1 },
    { "slot": 2, "name": "第2大节", "time": "10:20-12:00", "mask": 2 },
    { "slot": 3, "name": "第3大节", "time": "14:00-15:40", "mask": 4 },
    { "slot": 4, "name": "第4大节", "time": "16:00-17:40", "mask": 8 },
    { "slot": 5, "name": "第5大节", "time": "18:30-20:10", "mask": 16 }
]

# 北区这两栋在教务系统里各自独立（每栋都要单独 select_building 再查五大节），
# 界面上归入「北区」这一级，与两栋公教平级。
# 实训A / 实训B 曾一并纳入，2026-09-16 剔除：实测各仅 1 间空闲教室，收益不抵请求成本。
# 覆盖范围到此定稿，此后不再新增楼栋。
NORTH_BUILDINGS = ["教学B", "教学C"]

TARGET_BUILDINGS = ["第一公共教学楼", "第二公共教学楼"] + NORTH_BUILDINGS

# 楼栋 → 界面分组（today.json 里的 g 字段）。未列出的楼栋自成一组（g = 楼栋名）。
# 注意：TARGET_BUILDINGS 按楼栋名精确匹配教务系统返回的楼栋字典，
# 名字对不上只会打一行警告然后安静地少数据，改名时务必同步这里。
BUILDING_GROUPS = {name: "北区" for name in NORTH_BUILDINGS}

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

# ---------- 服务端日期校验 ----------
# 教务系统页面顶部会渲染学期信息，形如：
#   <span class='span_bbzx'> 2026-2027 秋 第3周 星期三</span>
# 这是**服务端自己认为的今天**。抓取时间提前到北京 04:00 后，必须拿它跟本地北京时间对一下：
# 若服务端还停在昨天（页面显示星期二、本地已是星期三），说明当天课表还没翻篇，
# 此时抓到的是昨天的数据 —— 绝不能写进 today.json（那等于把昨天的数据标成今天，且不会报错）。
SERVER_DAY_RE = re.compile(r"<span class=[\"']span_bbzx[\"']>\s*([^<]+?)\s*</span>")
SERVER_WEEKDAY_RE = re.compile(r"第\s*(\d+)\s*周\s*(星期[一二三四五六日天])")

# 与 datetime.weekday() 顺序一致（0=周一）
WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def parse_server_day(html: str) -> Optional[Dict[str, Any]]:
    """
    从页面里解析服务端日期。返回 {"week": int, "weekday": "星期三", "raw": "..."}，
    解析不到返回 None（页面结构变了）—— 调用方据此决定"警告继续"还是"硬失败"。

    注意：这里只能拿到**星期几**和**周次**，拿不到完整日期。星期几已足够发现"差一天"，
    而"差一天"正是我们担心的场景（服务端翻篇比本地晚）。
    """
    if not html:
        return None
    m = SERVER_DAY_RE.search(html)
    if not m:
        return None
    # 页面里周次与星期之间常有多个空格，规范化后留痕更好看
    raw = re.sub(r"\s+", " ", m.group(1)).strip()
    w = SERVER_WEEKDAY_RE.search(raw)
    if not w:
        return None
    weekday = w.group(2).replace("星期天", "星期日")
    return {"week": int(w.group(1)), "weekday": weekday, "raw": raw}


def beijing_today() -> datetime.datetime:
    """当前北京时间（与 workflow 的 TZ=Asia/Shanghai 一致）。"""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:  # 老 Python 无 zoneinfo 时退回 UTC+8
        return datetime.datetime.utcnow() + datetime.timedelta(hours=8)


def server_day_matches_local(server_day: Optional[Dict[str, Any]],
                             now: datetime.datetime = None) -> bool:
    """服务端星期 == 本地（北京）星期。server_day 为 None 时无法判定，按 True 处理（不阻塞）。"""
    if not server_day:
        return True
    if now is None:
        now = beijing_today()
    return server_day.get("weekday") == WEEKDAY_CN[now.weekday()]


def format_today_data(
    classrooms_raw: List[Dict[str, Any]],
    term: str = "2026-2027-1",
    updated_at: str = None,
    source: str = "live",
    data_date: str = None,
    server_day: str = None,
) -> Dict[str, Any]:
    """
    Cleans raw classroom data and generates standardized JSON structure matching PRD v2.0.

    source: "live" = 实时抓取的真实数据；其他值（如 "reset"）表示非实时，前端据此显示提示横幅。
    data_date: 数据所属日期（北京时间 YYYY-MM-DD），前端据此判断"数据是不是今天的"。
    server_day: 抓取时服务端页面上的「第N周 星期X」原文，留痕用。事后怀疑串天可直接查这个文件，
                不必重新登录教务系统。
    """
    if updated_at is None:
        updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if data_date is None:
        data_date = datetime.datetime.now().strftime("%Y-%m-%d")

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
            "g": BUILDING_GROUPS.get(building_name, building_name),
            "r": room_no,
            "c": item.get("c", item.get("capacity", 120)),
            "t": item.get("t", item.get("type", "多媒体")),
            "occ": int(occ_val)
        })

    result = {
        "updated_at": updated_at,
        "data_date": data_date,
        "source": source,
        "buildings": TARGET_BUILDINGS,
        "time_slots": TIME_SLOTS,
        "classrooms": processed_classrooms
    }
    if server_day:
        result["server_day"] = server_day
    return result

if __name__ == "__main__":
    print("Testing 5-Bit Bitmask Parser...")
    mask_1_2 = parse_slot_to_mask([1, 2])
    print(f"Slots 1, 2 mask: {mask_1_2} (Expected: 3)")
    print(f"Is Slot 1 free when occ is {mask_1_2}? {is_classroom_free(mask_1_2, TIME_SLOTS[0]['mask'])}")
    print(f"Is Slot 3 free when occ is {mask_1_2}? {is_classroom_free(mask_1_2, TIME_SLOTS[2]['mask'])}")
