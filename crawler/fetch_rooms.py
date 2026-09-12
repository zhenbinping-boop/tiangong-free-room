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
from typing import List, Dict, Any, Optional, Tuple  # noqa: F401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import format_today_data, TIME_SLOTS, TARGET_BUILDINGS  # noqa: E402
from jwxs_client import JwxsClient, JwxsError  # noqa: E402
from rooms_parser import records_from_spare_rooms  # noqa: E402

# 一天的小节数（第1节 ~ 第10节；五大节 = 1-2 / 3-4 / 5-6 / 7-8 / 9-10）
PERIODS_PER_DAY = 10


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
            period_rooms = client.fetch_all_periods(range(1, PERIODS_PER_DAY + 1), dayplus=0)
            recs = records_from_spare_rooms(period_rooms, verbose=False)
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

    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    output = format_today_data(
        classrooms_raw=records,
        updated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        source="live",
        data_date=today_str,
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
