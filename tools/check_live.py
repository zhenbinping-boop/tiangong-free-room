#!/usr/bin/env python3
"""线上体检：确认 GitHub Pages 上跑的确实是今天的新鲜数据。

为什么要有这一步：抓取和部署都成功，不代表**用户看到的东西**是对的。
部署可能没生效、CDN 可能还在发旧副本、gh-pages 可能停在几天前。
之前那批 42 间伪造数据就是这样在线上躺了很久没人发现——没有任何人在看线上产物。

判断"线上是不是当前这版"不靠硬编码的特征字符串（第一版就是栽在这上面：
`buildingTabs` 这种标记新旧两版都有，检查会假通过），而是拿**本地
web/index.html** 跟线上一一对照：标题必须一致，本地静态 HTML 里的每个
元素 id 都必须出现在线上。发版时它自动跟着走，没有需要手工维护的清单。

用法：
    python tools/check_live.py [base_url]
"""

import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = "https://zhenbinping-boop.github.io/tiangong-free-room/"

# 稳定不变的资源名，用于确认发布目录完整
ASSETS = ("style.css", "app.js", "sw.js", "manifest.json", "icons/icon-192.png")

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_INDEX = os.path.join(os.path.dirname(HERE), "web", "index.html")

RETRIES = 4
TIMEOUT = 30


def shanghai_now():
    """中国没有夏令时，+08:00 是常量偏移。"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def get(url):
    """带重试的 GET，返回 (status, bytes)。4xx/5xx 也返回而不是抛异常。"""
    last = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, headers={
            "User-Agent": "tiangong-healthcheck/1.0",
            "Cache-Control": "no-cache",
        })
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:  # 网络抖动，重试
            last = e
            print(f"  重试 {attempt + 1}/{RETRIES}：{url} -> {e}", file=sys.stderr)
    raise SystemExit(f"无法访问 {url}：{last}")


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else BASE)
    if not base.endswith("/"):
        base += "/"

    problems = []
    today = shanghai_now().strftime("%Y-%m-%d")
    stamp = shanghai_now().strftime("%Y%m%d%H%M%S")

    # 1. 首页可达，且内容确实是当前这一版
    local_html = ""
    if os.path.exists(LOCAL_INDEX):
        with open(LOCAL_INDEX, encoding="utf-8") as f:
            local_html = f.read()
    else:
        problems.append(f"本地缺少 {LOCAL_INDEX}，无法判断线上版本")

    status, body = get(f"{base}?v={stamp}")
    if status != 200:
        problems.append(f"首页返回 HTTP {status}")
    else:
        html = body.decode("utf-8", "replace")
        if local_html:
            local_title = re.search(r"<title>(.*?)</title>", local_html)
            live_title = re.search(r"<title>(.*?)</title>", html)
            if not local_title or not live_title:
                problems.append("读不到 <title>，无法比对版本")
            elif live_title.group(1).strip() != local_title.group(1).strip():
                problems.append(
                    f"线上标题是 {live_title.group(1)!r}，本地是 {local_title.group(1)!r}"
                    "（线上不是当前这版）")

            expected_ids = set(re.findall(r'id="([^"]+)"', local_html))
            missing = sorted(i for i in expected_ids if f'id="{i}"' not in html)
            if missing:
                problems.append(f"线上首页缺少当前版本的元素 id：{missing}（部署未生效）")
            else:
                print(f"[Live] 首页 200，标题与 {len(expected_ids)} 个元素 id 均与本地一致")

    # 2. 静态资源齐全
    for asset in ASSETS:
        status, _ = get(f"{base}{asset}?v={stamp}")
        if status != 200:
            problems.append(f"{asset} 返回 HTTP {status}")

    # 3. 数据是今天的、且是真实抓取的
    status, body = get(f"{base}data/today.json?v={stamp}")
    if status != 200:
        problems.append(f"data/today.json 返回 HTTP {status}")
    else:
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            problems.append(f"data/today.json 不是合法 JSON：{e}")
            data = None

        if data is not None:
            rooms = data.get("classrooms")
            if data.get("source") != "live":
                problems.append(f"source 是 {data.get('source')!r}，应为 'live'")
            if data.get("data_date") != today:
                problems.append(
                    f"data_date 是 {data.get('data_date')!r}，今天应是 {today}（线上数据未更新）")
            if not isinstance(rooms, list) or not rooms:
                problems.append("classrooms 为空或不是数组")
            else:
                buildings = sorted({r.get("b") for r in rooms if isinstance(r, dict)})
                print(f"[Live] 数据：{len(rooms)} 间教室，"
                      f"{len(buildings)} 栋楼，source={data.get('source')}，"
                      f"data_date={data.get('data_date')}")

    if problems:
        print("[Live] 线上体检未通过：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)

    print("[Live] 线上体检通过：数据新鲜、资源齐全、首页是当前版本")


if __name__ == "__main__":
    main()
