# -*- coding: utf-8 -*-
"""
每日空教室数据抓取主入口（PRD v1.2 修复版）。

核心原则（对应 PRD P0/P1）：
1. 绝不伪造数据：抓取失败立即以非零码退出，绝不回写任何生成/兜底数据；
2. 登录走 jwxs 原生流程（jwxs_client.py），不再触碰 CAS；
3. today.json 带 source 字段（live = 实时抓取），前端据此显示"数据是否可信"横幅；
4. 失败时保留仓库中上一次的真实数据（本轮不 commit，网站继续展示旧真数据）。

用法：
    python fetch_rooms.py                    # 凭据取环境变量 TIANGONG_USERNAME / TIANGONG_PASSWORD
    python fetch_rooms.py -u 学号 -p 密码    # 命令行传入（本地调试用）
"""

import os
import sys
import json
import shutil
import argparse
import datetime
import time
from typing import List, Dict, Any, Optional, Tuple  # noqa: F401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import (  # noqa: E402
    format_today_data,
    parse_server_day,
    server_day_matches_local,
    beijing_today,
    WEEKDAY_CN,
    TIME_SLOTS,
    TARGET_BUILDINGS,
)
from jwxs_client import JwxsClient, JwxsError  # noqa: E402
from rooms_parser import records_from_slot_rooms  # noqa: E402

# 一天的小节数（第1节 ~ 第10节；五大节 = 1-2 / 3-4 / 5-6 / 7-8 / 9-10）
PERIODS_PER_DAY = 10

# 服务端支持逗号分隔的多个小节，并取**交集**返回（实测确认，见 rooms_parser.records_from_slot_rooms）。
# 因此每个大节用一次查询即可，每栋 10 次请求 → 5 次。
SLOT_PERIODS: Dict[int, str] = {
    1: "1,2",
    2: "3,4",
    3: "5,6",
    4: "7,8",
    5: "9,10",
}


# 服务端翻篇校验：04:00 抓取时若服务端还停在昨天，就等一会儿再看。
# 环境变量可覆盖（本地调试用 TIANGONG_DAY_RETRY=0 表示只校验、不等待）。
DAY_CHECK_RETRIES = int(os.environ.get("TIANGONG_DAY_RETRY", "4"))
DAY_CHECK_INTERVAL_SEC = int(os.environ.get("TIANGONG_DAY_RETRY_SEC", "1800"))


def ensure_server_day_rolled(client) -> str:
    """
    确认教务系统页面的"今天"与本地北京时间一致；不一致就等待重试，直到翻篇或次数用尽。

    返回服务端日期原文（如 "2026-2027 秋 第3周 星期三"）；解析不到返回 ""（不阻塞）。

    为什么必须校验：data_date 用的是本地日期。若服务端还没翻篇而我们照抓，
    得到的会是昨天的课表，却被标成今天 —— 页面显示 source=live、日期是今天，
    没有任何报错。这属于"静默给出错误数据"，是本项目最不能接受的一类事故。
    """
    for attempt in range(DAY_CHECK_RETRIES + 1):
        now = beijing_today()
        try:
            html = client.fetch_today_html()
        except Exception as e:
            # 读不到就当作无法校验：警告后继续，不因为一次网络抖动整天没数据
            print(f"[Crawler] 警告：读取服务端日期失败（{e}），本轮不校验", file=sys.stderr)
            return ""

        day = parse_server_day(html)
        if day is None:
            # 页面结构变了（没有那个标记）：警告后继续，避免页面小改动就整天没数据
            print("[Crawler] 警告：页面里找不到「第N周 星期X」标记，无法确认服务端日期，继续抓取",
                  file=sys.stderr)
            return ""

        if server_day_matches_local(day, now):
            print(f"[Crawler] 服务端日期校验通过：{day['raw']}"
                  f"（本地 {now.strftime('%Y-%m-%d')} {WEEKDAY_CN[now.weekday()]}）")
            return day["raw"]

        print(f"[Crawler] 服务端还停在『{day['raw']}』，本地已是 "
              f"{now.strftime('%Y-%m-%d')} {WEEKDAY_CN[now.weekday()]} "
              f"—— 当天课表尚未刷新", file=sys.stderr)
        if attempt >= DAY_CHECK_RETRIES:
            print(f"[Crawler] 错误：等待 {DAY_CHECK_RETRIES} 次后服务端仍未翻篇，"
                  f"拒绝写入 today.json（否则会把昨天的数据标成今天）", file=sys.stderr)
            print("[Crawler] 保留上一次真实数据，本轮不更新 today.json", file=sys.stderr)
            sys.exit(1)
        print(f"[Crawler] {DAY_CHECK_INTERVAL_SEC // 60} 分钟后重试"
              f"（{attempt + 1}/{DAY_CHECK_RETRIES}）…")
        time.sleep(DAY_CHECK_INTERVAL_SEC)

    return ""


def build_today_json(username: str = "", password: str = "") -> None:
    username = (username or "").strip() or os.environ.get("TIANGONG_USERNAME", "").strip()
    password = (password or "").strip() or os.environ.get("TIANGONG_PASSWORD", "").strip()

    if not username or not password:
        print("[Crawler] 错误：未提供 TIANGONG_USERNAME / TIANGONG_PASSWORD", file=sys.stderr)
        sys.exit(2)

    # ---- 登录 ----
    try:
        client = JwxsClient(username=username, password=password)
        client.login()
    except JwxsError as e:
        print(f"[Crawler] 登录失败：{e}", file=sys.stderr)
        print("[Crawler] 保留上一次真实数据，本轮不更新 today.json", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[Crawler] 登录异常：{e}", file=sys.stderr)
        sys.exit(1)

    # ---- 服务端日期校验：确认教务系统的"今天"已经翻篇 ----
    # 抓取在北京 04:00 跑。若教务系统的今天还停在昨天，抓到的就是昨天的课表 ——
    # 而 data_date 仍会写成本地日期，等于把昨天的数据标成今天发出去且不报错（静默错误）。
    # 页面顶部的「第N周 星期X」是服务端自己认为的今天，拿它跟本地北京时间比对。
    server_day_raw = ensure_server_day_rolled(client)

    # ---- 抓取（JSON 接口：按楼栋切换 → 逐小节查询）----
    # 流程：取校区列表 → 按校区取楼栋列表 → 定位目标楼栋 → select_building 切换 → 逐小节查空闲
    records: List[Dict[str, Any]] = []
    try:
        campuses = client.fetch_campus_list()
        print("[Crawler] 校区：" + ", ".join(f"{c['name']}({c['number']})" for c in campuses))

        # {楼栋名: (校区号, 楼号, 校区名)}
        targets: Dict[str, Tuple[str, str, str]] = {}
        for campus in campuses:
            try:
                buildings = client.fetch_building_list(campus["number"])
            except JwxsError as e:
                print(f"[Crawler] 警告：校区『{campus['name']}』楼栋列表获取失败（{e}），跳过", file=sys.stderr)
                continue
            for name in TARGET_BUILDINGS:
                if name in buildings and name not in targets:
                    info = buildings[name]
                    targets[name] = (info["campus_number"], info["number"], campus["name"])
                    print(f"[Crawler] 定位『{name}』→ {campus['name']} "
                          f"position={info['campus_number']}_{info['number']}")

        missed = [n for n in TARGET_BUILDINGS if n not in targets]
        if missed:
            print(f"[Crawler] 警告：目标楼栋未定位到：{missed}", file=sys.stderr)

        if not targets:
            print("[Crawler] 错误：未定位到任何目标楼栋，拒绝写入数据", file=sys.stderr)
            sys.exit(1)

        for name in TARGET_BUILDINGS:
            if name not in targets:
                continue
            campus_number, building_number, campus_name = targets[name]
            client.select_building(campus_number, building_number, campus_name)
            slot_rooms = {slot: client.fetch_free_rooms(expr, dayplus=0)
                          for slot, expr in SLOT_PERIODS.items()}
            recs = records_from_slot_rooms(slot_rooms, verbose=False)
            # 单楼栋视图下 acmcBuildingName 即目标楼栋；为空则补上
            for r in recs:
                if not r.get("building"):
                    r["building"] = name
            print(f"[Crawler] 『{name}』解析到 {len(recs)} 间教室")
            records.extend(recs)
    except JwxsError as e:
        print(f"[Crawler] 抓取失败：{e}", file=sys.stderr)
        print("[Crawler] 保留上一次真实数据，本轮不更新 today.json", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[Crawler] 抓取异常：{e}", file=sys.stderr)
        sys.exit(1)

    if not records:
        print("[Crawler] 错误：所有楼栋解析结果均为空——可能页面结构变更，拒绝写入", file=sys.stderr)
        sys.exit(1)

    # 显式按北京时间取，不再依赖运行机器的本地时区
    # （workflow 里设了 TZ=Asia/Shanghai，两者一致；本机跑在别的时区时这行才是保命的）
    now = beijing_today()
    today_str = now.strftime("%Y-%m-%d")
    output = format_today_data(
        classrooms_raw=records,
        updated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        source="live",
        data_date=today_str,
        server_day=server_day_raw,
    )

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    canonical = os.path.join(base_dir, "public", "data", "today.json")
    published = os.path.join(base_dir, "web", "data", "today.json")

    # 只序列化一次，第二份用文件复制。
    # 分别 dump 两遍是在给自己制造"两份不一致"的机会——同一份数据不该有两次序列化。
    os.makedirs(os.path.dirname(canonical), exist_ok=True)
    with open(canonical, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[Crawler] today.json 已写入 ({len(output['classrooms'])} 间教室, source=live) -> {canonical}")

    # web/data/ 是 GitHub Pages 的发布副本，必须存在（publish_dir: ./web）
    os.makedirs(os.path.dirname(published), exist_ok=True)
    shutil.copyfile(canonical, published)
    print(f"[Crawler] 发布副本已同步 -> {published}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="天津工业大学空教室数据抓取（jwxs 原生登录版）")
    cli.add_argument("-u", "--username", default="", help="学号（默认取环境变量 TIANGONG_USERNAME）")
    cli.add_argument("-p", "--password", default="", help="密码（默认取环境变量 TIANGONG_PASSWORD）")
    args = cli.parse_args()

    build_today_json(username=args.username, password=args.password)
