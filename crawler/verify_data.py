# -*- coding: utf-8 -*-
"""数据门禁：抓取完成后、提交之前，校验 today.json 是不是一份可信的数据。

为什么需要这一步：抓取脚本"退出码 0"只说明它没崩，不说明产物是对的。
历史上最严重的一次事故就是——抓取失败、脚本静默写了假数据、退出码 0、流水线全绿、
线上展示了几个月的伪造空教室。门禁的作用是让"产物不可信"这种事在提交前就拦住。

只校验**能够确定的事实**（结构、字段类型、日期），不校验"看起来合理"的数量区间——
教学楼增减教室是正常业务变化，不该让流水线因为 178 变成 179 而红。

用法：
    python crawler/verify_data.py
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)

CANONICAL = os.path.join(BASE_DIR, "public", "data", "today.json")
PUBLISHED = os.path.join(BASE_DIR, "web", "data", "today.json")

REQUIRED_TOP_KEYS = ("source", "data_date", "updated_at", "time_slots", "classrooms")


def shanghai_now():
    """中国没有夏令时，+08:00 是常量偏移，不需要 tzdata 依赖。"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def fail(problems):
    print("[Gate] 数据校验未通过：", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    print("[Gate] 拒绝提交。上一次的真实数据会保留，网站继续展示旧数据。", file=sys.stderr)
    sys.exit(1)


def check_payload(data, problems):
    for key in REQUIRED_TOP_KEYS:
        if key not in data:
            problems.append(f"缺少顶层字段 {key}")
    if problems:
        return

    if data["source"] != "live":
        problems.append(f"source 必须是 live，实际是 {data['source']!r}")

    today = shanghai_now().strftime("%Y-%m-%d")
    if data["data_date"] != today:
        problems.append(f"data_date 应为今天 {today}，实际是 {data['data_date']!r}")

    if not str(data["updated_at"]).startswith(today):
        problems.append(f"updated_at 的日期部分应为 {today}，实际是 {data['updated_at']!r}")

    slots = data["time_slots"]
    if not isinstance(slots, list) or not slots:
        problems.append("time_slots 必须是非空数组")
        return
    for slot in slots:
        if not isinstance(slot, dict):
            problems.append("time_slots 里存在非对象元素")
            break
        for key in ("slot", "name", "mask"):
            if key not in slot:
                problems.append(f"time_slots 元素缺少 {key}")
                break
        else:
            mask = slot["mask"]
            if not isinstance(mask, int) or mask <= 0 or mask & ~31:
                problems.append(f"time_slots[{slot['slot']}].mask={mask!r} 不是 1..31 的位掩码")

    rooms = data["classrooms"]
    if not isinstance(rooms, list) or not rooms:
        problems.append("classrooms 必须是非空数组（空数组意味着没有一间教室可用，视为抓取失败）")
        return

    seen_buildings = set()
    bad_room = bad_building = bad_seats = bad_occ = 0
    for room in rooms:
        if not isinstance(room, dict):
            bad_room += 1
            continue
        name = str(room.get("r") or "")
        building = str(room.get("b") or "")
        if not name or not any(ch.isdigit() for ch in name):
            bad_room += 1
        if not building:
            bad_building += 1
        else:
            seen_buildings.add(building)
        if not isinstance(room.get("c"), int) or room["c"] <= 0:
            bad_seats += 1
        occ = room.get("occ")
        if not isinstance(occ, int) or occ < 0 or occ & ~31:
            bad_occ += 1

    if bad_room:
        problems.append(f"{bad_room} 条记录缺少可识别房号（r）")
    if bad_building:
        problems.append(f"{bad_building} 条记录缺少楼栋（b）")
    if bad_seats:
        problems.append(f"{bad_seats} 条记录的座位数（c）不是正整数")
    if bad_occ:
        problems.append(f"{bad_occ} 条记录的占用掩码（occ）不是 0..31")

    # 五大节对应 1/2/4/8/16 五位，全集的并集必须是 31。
    # 少于 31 说明有节次段根本没被抓，前端那五格日条会有一格永远是空的。
    union = 0
    for slot in slots:
        if isinstance(slot, dict) and isinstance(slot.get("mask"), int):
            union |= slot["mask"]
    if union != 31:
        problems.append(f"time_slots 掩码并集是 {union}，应为 31（五大节全覆盖）")

    if not problems:
        print(f"[Gate] 结构校验通过：{len(rooms)} 间教室，"
              f"{len(seen_buildings)} 栋楼（{'、'.join(sorted(seen_buildings))}）")


def main():
    for path, label in ((CANONICAL, "仓库源"), (PUBLISHED, "发布副本")):
        if not os.path.exists(path):
            fail([f"{label}文件不存在：{path}"])

    with open(CANONICAL, "rb") as f:
        canonical_bytes = f.read()
    with open(PUBLISHED, "rb") as f:
        published_bytes = f.read()

    if canonical_bytes != published_bytes:
        fail(["两份 today.json 不一致——发布出去的会不是校验过的那一份"])

    try:
        data = json.loads(canonical_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        fail([f"today.json 不是合法 JSON：{e}"])

    problems = []
    check_payload(data, problems)
    if problems:
        fail(problems)

    print(f"[Gate] 两份文件逐字节一致，source=live，data_date={data['data_date']}")


if __name__ == "__main__":
    main()
