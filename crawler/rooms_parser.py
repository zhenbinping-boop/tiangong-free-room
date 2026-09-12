# -*- coding: utf-8 -*-
"""
解析 /student/teachingResources/freeClassroom/today 页面 HTML 中的空教室数据
（依据 2026-09-12 真实页面样本 crawler/fixtures/free_classroom_today.html 校准）。

页面真实结构（服务端渲染进内嵌 JS，靠 tbody 字符串拼接输出）：
    tbody += "<tr id='3'>";                                   // tr id = 小节序号
    tbody += "<td ...>第3节<br />"; //10:20-11:05
    ...
    tbody += "D103 <font color='#ADADAD' size='2'>";
    if (250 != null) { tbody += "(250)"; }                    // 容量在紧随其后的 if 里

要点：
- 列表给出的是**每小节的空闲教室**（非空闲的不出现）；
- 服务器**不渲染已经过去的小节**（如 11 点后查当天，第1、2节不会出现在页面里）；
  因此"未出现的小节"一律按"未知"处理，不据此判定占用。

小节 → 五大节映射（与 parser.py TIME_SLOTS 一致）：
  大节1 = 小节1-2, 大节2 = 小节3-4, 大节3 = 小节5-6, 大节4 = 小节7-8, 大节5 = 小节9-10
某大节空闲 = 该大节内的**所有小节都出现在空闲列表中**。
"""

import re
from typing import Any, Dict, List

# 小节行：<tr id='3'>
ROW_RE = re.compile(r"tbody\s*\+=\s*[\"']<tr\s+id=['\"](\d+)['\"]>", re.S)
# 教室条目：tbody += "D103 <font ...>" ... (250)
ROOM_RE = re.compile(
    r"tbody\s*\+=\s*[\"']([A-Za-z]?\d+[A-Za-z]?)\s*<font[^>]*>[\"'](.{0,200}?)\((\d+)\)",
    re.S,
)
# 小节 → 五大节
PERIOD_TO_SLOT: Dict[int, int] = {}
for _slot, _periods in enumerate([(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)], start=1):
    for _p in _periods:
        PERIOD_TO_SLOT[_p] = _slot

FULL_DAY_PERIODS = 10  # 完整一天应覆盖的小节数（1-10）


def parse_free_classroom_html(html: str) -> Dict[str, Any]:
    """
    解析单个教学楼页面。
    返回 {"rooms": {room: {"room","capacity","free_periods":[...]}},
          "observed_periods": [...], "complete": bool}
    """
    marks = list(ROW_RE.finditer(html))
    rooms: Dict[str, Dict[str, Any]] = {}
    observed: List[int] = []

    for idx, m in enumerate(marks):
        period = int(m.group(1))
        observed.append(period)
        end = marks[idx + 1].start() if idx + 1 < len(marks) else len(html)
        segment = html[m.end():end]
        for rm in ROOM_RE.finditer(segment):
            name, cap = rm.group(1).strip(), int(rm.group(3))
            key = name.upper()
            entry = rooms.setdefault(key, {"room": name, "capacity": cap, "free_periods": []})
            if period not in entry["free_periods"]:
                entry["free_periods"].append(period)

    missing = [p for p in range(1, FULL_DAY_PERIODS + 1) if p not in observed]
    return {
        "rooms": rooms,
        "observed_periods": sorted(observed),
        "missing_periods": missing,
        "complete": len(missing) == 0,
    }


def slot_busy_mask(free_periods: List[int], observed_periods: List[int]) -> int:
    """
    计算 5-bit 占用掩码。
    - 小节出现在空闲列表 → 该小节空闲；
    - 小节被渲染但教室未出现 → 该小节占用；
    - 小节未被渲染（已过去等）→ 视为未知，不置位。
    某大节占用 = 其包含的小节中，至少有一个"已渲染但教室未出现"。
    """
    mask = 0
    for slot in range(1, 6):
        periods = [p for p, s in PERIOD_TO_SLOT.items() if s == slot]
        rendered = [p for p in periods if p in observed_periods]
        busy = any(p not in free_periods for p in rendered)
        if busy:
            mask |= (1 << (slot - 1))
    return mask


def records_from_spare_rooms(period_rooms: Dict[int, List[dict]], verbose: bool = False) -> List[Dict[str, Any]]:
    """
    首选数据源：JSON 接口
        GET /student/teachingResources/freeClassroom/today/{小节}?dayplus=0
        → {"spareroomObjList":[{"acmcBuildingName":"第二公共教学楼",
                                "claroom":[{"classroom":"D103","classNumberOfSeats":"250"}]}]}

    period_rooms: {小节号: spareroomObjList}
    返回按 (楼栋, 教室) 聚合的记录，busy 为五大节占用列表。
    """
    info: Dict[tuple, Dict[str, Any]] = {}
    for period, buildings in sorted(period_rooms.items()):
        for b in buildings or []:
            bname = (b.get("acmcBuildingName") or "").strip()
            for room in (b.get("claroom") or []):
                name = (room.get("classroom") or "").strip()
                if not name:
                    continue
                key = (bname, name.upper())
                try:
                    cap = int(str(room.get("classNumberOfSeats") or "0").strip())
                except ValueError:
                    cap = 0
                entry = info.setdefault(key, {
                    "building": bname, "room": name, "capacity": cap, "free_periods": []
                })
                if period not in entry["free_periods"]:
                    entry["free_periods"].append(period)

    # 判定"已观测"的小节：有返回教室的小节才算数（过去的小节可能整节为空）
    observed = [p for p, bl in period_rooms.items() if any((b.get("claroom") or []) for b in (bl or []))]
    missing = [p for p in range(1, FULL_DAY_PERIODS + 1) if p not in observed]
    if verbose:
        print(f"[rooms_parser] JSON 覆盖小节 {sorted(observed)}"
              + (f"，缺失 {missing}（按未知处理）" if missing else ""))
        print(f"[rooms_parser] 共 {len(info)} 间教室")

    records = []
    for entry in info.values():
        mask = slot_busy_mask(entry["free_periods"], observed)
        records.append({
            "building": entry["building"],
            "room": entry["room"],
            "capacity": entry["capacity"],
            "type": "",
            "busy": [s for s in range(1, 6) if mask & (1 << (s - 1))],
        })
    return records


def to_records(html: str, building: str = "", verbose: bool = False) -> List[Dict[str, Any]]:
    """（备用）从单楼栋 HTML 页面解析。HTTP 接口不可用时才走这条路。"""
    parsed = parse_free_classroom_html(html)
    if verbose and not parsed["complete"]:
        print(f"[rooms_parser] 警告：{building or '本楼'} 缺少小节 {parsed['missing_periods']}（通常因这些节次已过去），相关大节按未知处理")
    if verbose:
        print(f"[rooms_parser] {building or '本楼'} 解析到 {len(parsed['rooms'])} 间教室，覆盖小节 {parsed['observed_periods']}")

    records = []
    for entry in parsed["rooms"].values():
        mask = slot_busy_mask(entry["free_periods"], parsed["observed_periods"])
        busy = [s for s in range(1, 6) if mask & (1 << (s - 1))]
        records.append({
            "building": building,
            "room": entry["room"],
            "capacity": entry["capacity"],
            "type": "",
            "busy": busy,
        })
    return records


if __name__ == "__main__":
    import os
    import sys

    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "free_classroom_today.html")
    if len(sys.argv) > 1:
        fixture = sys.argv[1]
    if not os.path.exists(fixture):
        print(f"[rooms_parser] 未找到样本: {fixture}")
        sys.exit(1)

    html = open(fixture, encoding="utf-8", errors="replace").read()
    recs = to_records(html, building="第二公共教学楼", verbose=True)
    print(f"\n共 {len(recs)} 间教室，示例：")
    for r in recs[:12]:
        print("  ", r["room"], f"{r['capacity']}座", "占用大节:", r["busy"] or "无(全天空闲)")
