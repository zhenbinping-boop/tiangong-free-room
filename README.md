# 天津工业大学空教室查询（非官方）

一个查看**天津工业大学公共教学楼当前空教室**的静态站点 + 自动抓取任务。
数据每日北京时间 04:00 由 GitHub Actions 登录教务系统真实抓取，不人工录入、不估算、不用课表反推。
抓取前会校验教务系统自己的"今天"是否已翻篇，未翻篇则等待重试，绝不把昨天的数据标成今天。

- 线上：https://zhenbinping-boop.github.io/tiangong-free-room/
- Android：站点内「装到手机」页可下载 APK（或直接用 PWA「添加到主屏幕」）
- 范围：**第一公共教学楼 + 第二公共教学楼 + 北区两栋（教学B / 教学C）**
  —— 教室总数随日期浮动（全天占满的教室接口不返回），2026-09-16 实测 192 间

> 学生自建工具，与学校教务系统无隶属关系，不得暗示有关联。

---

## 它是怎么工作的

```
GitHub Actions（北京 04:00）
  └─ 登录教务系统 → 校验服务端"今天"已翻篇（未翻篇则每 30 分钟复查，最多 4 次）
     → 按大节抓取空教室（每栋 1 次切换 + 5 次查询）→ 写 today.json → 提交并发布 Pages
                                  └─ verify_data 门禁：结构/日期/两份一致/source=live，任一不过就红
浏览器 / App ── 读取同域 today.json（同一份代码，天然同步）
```

无后端、无数据库。App 只是一个壳，加载的就是这个站点，**改网页不需要重新发 APK**。

## 目录结构

| 路径 | 内容 |
|---|---|
| `crawler/` | 抓取与解析：`fetch_rooms.py`（入口）、`jwxs_client.py`（登录+接口）、`parser.py`、`rooms_parser.py`、`verify_data.py`（数据门禁）、`test_bitmask.py` |
| `web/` | 发布目录（Pages 发布的就这一个）：`index.html` / `app.js` / `style.css` / `sw.js` / `manifest.json` / `icons/` / `download.html` |
| `public/data/` | `today.json` 源文件（与 `web/data/` 逐字节一致，门禁会查） |
| `tools/` | `check_live.py`（线上体检）、`make_icons.py`（生成 PWA 图标）、`make_assetlinks.py` |
| `docs/` | PRD、代码审查报告、接口真源 `api-schema.md`、Android 打包 `ANDROID-APP.md` |
| `android/` | `webview-shell/`（Android 直壳工程）、`release.keystore`（**未入库**） |

---

## 本地运行

```bash
pip install -r crawler/requirements.txt

export TIANGONG_USERNAME=学号
export TIANGONG_PASSWORD=密码
export TZ=Asia/Shanghai

python crawler/fetch_rooms.py     # 抓取；失败非零退出
python crawler/verify_data.py     # 提交前数据门禁
python crawler/test_bitmask.py    # 位掩码单元测试
python tools/check_live.py        # 线上体检（比对线上与本地 web/index.html）
```

**本机需能访问教务系统**（校外网络可能不通）。运行需要凭据，因为**不存在任何伪造数据的路径** ——
本地没有凭据就是抓不到，这是有意为之：宁可不产出，也不产出无法追溯来源的数据。

### 环境变量

| 变量 | 用途 |
|---|---|
| `TIANGONG_USERNAME` | 学号（本地或 GitHub Secrets） |
| `TIANGONG_PASSWORD` | 密码（本地或 GitHub Secrets） |
| `TZ` | 固定 `Asia/Shanghai`（决定"今天"是哪天） |

`TIANGONG_COOKIE` 已废弃移除 —— 改为每次运行现场登录一次，手工 cookie 模式不再支持。

### 依赖说明

`requests`、`beautifulsoup4`、`python-dotenv`、`ddddocr`。
`ddddocr` 体积较大（含 ONNX 模型），CI 中首次安装约 1–2 分钟，属预期。

---

## 数据可信度约定（本项目的铁律）

1. **绝不生成假数据。** 仓库内不存在 mock 路径；抓取失败即非零退出。
2. `today.json` 带 `source` 与 `data_date`：
   - `live` = 本次实时抓取成功；
   - 其他值 = 保留的上一次真实数据，前端顶部显示"非实时"横幅，用户自行判断。
3. 失败时**保留上一次真实数据**，不覆盖为空、不补全。
4. 提交前 `verify_data.py` 强制校验（`source=live`、`data_date` 为今天、两份文件逐字节一致、位掩码合法）。
   **故意不校验教室数量** —— 178→179 属正常业务变化，硬断言会训练人忽略红灯。

## 验证码与重试

- 教务系统登录强制 4 位图形验证码（绑定会话），用 `ddddocr` 识别。
- 识别失败或登录失败 → **换一张验证码重来，默认最多 10 次**（`CAPTCHA_MAX_ATTEMPTS`），重试之间间隔 1 秒。
- 达上限仍失败 → 抛错并以非零码退出，workflow 变红，**不会写入任何数据**。
- 单次识别率**未做系统性统计**（真机实测样本：首次尝试即通过）。按单次 60% 估算，10 次重试后失败概率约 0.01%，
  但这是概率估算而非实测结论。

## 自动化任务

| Workflow | 触发 | 作用 |
|---|---|---|
| `daily-crawler.yml` | 每日 `0 20 * * *` UTC（北京 04:00） | 测试 → 抓取（含服务端翻篇校验）→ `verify_data` 门禁 → 同步 → 提交 → 发布 Pages |
| `web-healthcheck.yml` | 每日 `0 21 * * *` UTC（北京 05:00） | 线上体检：比对线上与本地 `web/index.html`（标题 + 全部元素 id） |
| `deploy-pages.yml` | push 到 main 且 `web/**` 有改动 | 立即发布前端，不必等次日 04:00 |
| `build-apk.yml` | 手动 / push 改 `android/webview-shell/**` | 云端构建签名 APK → 提交到 `web/download/` → 发布 |

### 需要的 Secrets

| 名称 | 用途 |
|---|---|
| `TIANGONG_USERNAME` / `TIANGONG_PASSWORD` | 教务系统凭据 |
| `ANDROID_KEYSTORE_BASE64` / `KEYSTORE_PASSWORD` / `KEY_ALIAS` / `KEY_PASSWORD` | APK 签名 |

凭据只走 Secrets，**不进入任何文件、提交或文档**。

---

## 故障排查

抓取链路分四段，出问题先定位是哪一段（看 Actions 哪一步红了）：

| 症状 | 段 | 排查方向 |
|---|---|---|
| 登录失败，日志出现 `badCaptcha` | 验证码 | 教务系统换了验证码样式；识别率骤降。短期内重跑一次即可 |
| 登录失败，日志出现 `badCredentials` | 登录 | 密码变更，或密码加密公式失效（见 `docs/api-schema.md` §1.2） |
| 抓取结果为 0 间 / 缺楼栋 | 数据接口 | 接口路径或 `position` 语义变化 —— 注意 `position` 必须是 `"{校区号}_{楼栋号}"`，只传楼号会 500 |
| `verify_data` 报红 | 门禁 | 数据非当日、`source` 不是 `live`、两份文件不一致 |
| 日志出现「服务端还停在…当天课表尚未刷新」 | 翻篇校验 | 教务系统的"今天"还没翻篇（多见于 04:00 那次）。脚本会自动等 30 分钟复查、最多 4 次；**4 次后仍未翻篇则拒绝写入**，当天保留昨天数据并显示「非实时」横幅 —— 这是正确行为，不是 bug。想确认某天数据有没有串天，看该文件里的 `server_day` 与 `data_date` 是否对得上 |
| `git pull --rebase` 失败（exit 128） | 同步 | 工作区有未提交的 `today.json`；workflow 已用 `--autostash`，若仍失败多为远端有并发提交 |
| 线上还是旧版 | 发布 | 跑 `python tools/check_live.py`；前端改动可手动触发 `Deploy Web to Pages` |

**常用命令**

```bash
# 线上当前是哪一版（会与本地 web/index.html 逐项比对）
python tools/check_live.py

# 某天到底跑到哪一步（把 <run-id> 换成实际值）
gh run view <run-id> --log
```

> 判定"线上是不是当前这版"**必须与本地文件比对**，不要用硬编码的特征字符串 ——
> 旧版也可能含有同名元素，会假通过。

## 打包 Android

见 `docs/ANDROID-APP.md`（WebView 直壳方案、云端构建、签名密钥、下载分发）。

改了壳再出包时记得把 `app/build.gradle` 的 `versionCode` +1；
**改了网页不需要重新出包**。

## 合规与边界

- 使用真实学号登录属个人数据查询范畴：**每日 1 次、单线程、单账号**，不提供批量接口。
- 覆盖范围固定为两栋公共教学楼，是产品定位而非临时状态。
- 尚未决定、**也不得编造**的事项：是否需要"明天"查询、是否需要收藏/历史趋势、真实使用量与用户反馈。
