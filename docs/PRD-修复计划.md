# 天津工业大学空教室查询网站 — 修复 PRD

| 项目 | 内容 |
|---|---|
| 文档版本 | v1.1 |
| 创建日期 | 2026-09-11 |
| 当前状态 | 待实施 |
| 关联仓库 | `tiangong-free-room` |
| 关联文档 | `docs/代码审查报告`（同目录） |

### 修订记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-11 | 初版 |
| **v1.1** | 2026-09-11 | 用户确认"无常驻机器、每日仅需登录一次即可取整天数据"。据此**大幅简化**：取消会话持久化与心跳保活；确认采用 GitHub Actions 方案（IP 绑定问题消解）；P2/P4 重写；新增验证码识别率风险与重试对策 |

---

## 0. 一句话目标

**让网站每天稳定展示真实的空教室数据；抓不到时必须明确告知用户，绝不展示编造数据。**

---

## 1. 现状与问题

### 1.1 已确认的事实基线（实测取证，作为后续开发的唯一依据）

> 以下结论均于 2026-09-11 通过实际网络请求验证得出，后续开发**无需重新探测**，直接按此实施。

#### A. 目标系统：教务系统（jwxs）

| 项 | 确认值 |
|---|---|
| 系统类型 | 强智 URP 教务系统，Spring Security，校方编号 `schoolId=100018` |
| 未登录访问 | `GET /student/teachingResources/freeClassroom/index` → **302** → `http://jwxs.tiangong.edu.cn/gotoLogin` |
| 登录页 | `gotoLogin` → 302 → **`https://jwxs.tiangong.edu.cn/login`** |
| 登录提交地址 | **`POST https://jwxs.tiangong.edu.cn/j_spring_security_check`** |
| 表单字段 | `lang=zh`、`tokenValue`（每次动态生成）、`j_username`、`j_password`、`j_captcha`、`username`（隐藏，空值） |
| 验证码 | `GET /img/captcha.jpg`，180×60 JPEG，**4 位字符带干扰线**，与会话绑定 |
| 会话 Cookie | `JSESSIONID` + `student.urpSoft.cn`（两者同值），`HttpOnly`，**会话级（无过期时间）** |
| 页面加载的加密库 | `md5.min.js`、`sm3/byteUtil.js`、`sm3/hex.js`、`sm3/sm3.js`；但 `login.js` 中**未见加密调用** |

#### B. CAS（统一身份认证，`pt.tiangong.edu.cn`）

| 项 | 确认值 |
|---|---|
| 结论 | **jwxs 未接入 CAS，CAS 明确拒绝为该 service 签发票据** |
| 实测证据 | `GET https://pt.tiangong.edu.cn/cas/login?service=https%3A%2F%2Fjwxs.tiangong.edu.cn%2F...` → 200，页面内容：**"未认证授权服务 — 不允许使用CAS来认证您访问的目标应用"** |
| CAS 登录页字段 | `username`、`password`（隐藏，由 JS `CreateRatePasswdReq()` 填充）、`authcode`（验证码）、`execution`（超长令牌）、`_eventId`、`uuid`、`rememberMe` |
| CAS 依赖 JS | `login.js`、`pwdYz.js`、`security.js`、`tac.min.js` |

#### C. 其他已确认事实

- **线上数据为伪造**：`public/data/today.json` 的 42 间教室（教室号/容量/类型）与代码中硬编码的 `BUILDING_ROOM_TEMPLATES` **逐字 100% 吻合**，仅"占用节次"由日期种子随机生成。**爬虫从未成功获取过任何真实数据。**
- **时区错误**：`today.json` 的 `updated_at`（如 `2026-09-09 02:54:50`）与该次 commit 时间 `2026-09-09T02:54:50Z` 完全一致，证明是 runner 的 **UTC 时钟**，非北京时间。
- workflow cron 为 `0 19 * * *` UTC = 北京时间**次日 03:00**，此时 runner 的 UTC 日期为北京视角的**前一天** → 查询的是昨天的空教室。

### 1.2 缺陷清单

| 编号 | 级别 | 位置 | 问题 | 影响 |
|---|---|---|---|---|
| BUG-01 | 致命 | `fetch_rooms.py:20,92-143` | 自动登录目标错误：向 CAS 请求 jwxs 的票据，CAS 明确拒绝 | 登录**从未成功过** |
| BUG-02 | 致命 | `fetch_rooms.py:102-107` | 验证码完全未处理（jwxs 的 `j_captcha` / CAS 的 `authcode`） | 自动登录不可能成立 |
| BUG-03 | 致命 | `fetch_rooms.py:138-143` | 登录成功判定假阳性：仅检查响应是否含"登录失败/密码错误" | 失败被误报为成功 |
| BUG-04 | 高 | `fetch_rooms.py:316-318` | 抓取失败静默降级到 `generate_fallback_records()` 伪造数据 | 用户看到假数据且毫不知情 |
| BUG-05 | 高 | `fetch_rooms.py:296-336` | 退出码恒为 0，workflow 永远绿色 | 失败完全不可见 |
| BUG-06 | 高 | `fetch_rooms.py:81` | Cookie 有效性判定用 `"login" not in text`，子串误判率极高 | 有效 cookie 常被误判为失效 |
| BUG-07 | 高 | `fetch_rooms.py:70` | 手写 `Cookie` 请求头，压制服务端 `Set-Cookie` | 服务端续期的新会话永远用不上 |
| ~~BUG-08~~ | ~~高~~ | 全局 | 无 cookie 持久化、无刷新、无回写 | **v1.1：改为每次现场登录，本项无需修复** |
| ~~BUG-09~~ | ~~中~~ | 全局 | 无心跳保活 | **v1.1：会话仅需存活 < 1 分钟，本项无需修复** |
| BUG-10 | 中 | `fetch_rooms.py:156,320` | 日期与时间均为 UTC，未按北京时间计算 | 查的是昨天的数据，展示时间差 8 小时 |
| BUG-11 | 中 | `fetch_rooms.py:159-168` | 对 8 个端点盲试，响应字段名靠猜（`roomName/r/jsmc`） | 从未对齐真实 API，易触发限流 |
| BUG-12 | 中 | `fetch_rooms.py:61-68` | 全局请求头污染：`X-Requested-With: XMLHttpRequest` 与固定 `Referer/Origin` 也发给 CAS | 可能导致 CAS 返回非预期响应 |
| BUG-13 | 低 | `fetch_rooms.py:221` | `int(item.get("capacity"))` 无类型/空值防护 | 脏数据直接抛异常 |
| BUG-14 | 低 | `fetch_rooms.py:27,161-167` | WebVPN 分支为无效噪声（独立认证体系） | 干扰排查 |
| BUG-15 | 中 | `parser.py` / `app.js` | 数据文件无来源标记，前端无法提示"数据非实时" | 用户无法分辨真假 |

### 1.3 根因摘要

**"cookie 失效"是表象。真正的因果链：**

1. 自动登录走错门（CAS 拒绝 jwxs）+ 验证码未处理 → **会话从未建立**（BUG-01/02/03）
2. 只能依赖手工粘贴 cookie → 手工 cookie 天然短命（会话级、IP 绑定、无心跳、不回写）（BUG-06~09）
3. 失败后静默编造数据 + 退出码恒为 0 → **真实原因被系统性隐藏**（BUG-04/05）
4. 于是唯一的可见症状就是"cookie 又失效了"，导致长期在表层症状上打转

---

## 2. 范围

### In Scope（本期要做）

- 修复登录流程，实现对的真实自动登录（每次运行现场登录一次）
- 消除虚假数据，建立"失败可见"机制
- 修正时区，对齐真实数据接口
- 前端增加数据状态提示

### Out of Scope（本期不做）

- WebVPN（`vpn.tiangong.edu.cn`）通道 —— 已确认无效，直接移除
- CAS 分支 —— 待校方将 jwxs 接入 CAS 后再议（届时需补齐验证码与密码加密）
- 新增教学楼/时间段、UI 大改版、用户系统
- 多账号/代理池

---

## 3. 功能需求

### FR-1 数据真实性保障（最高优先级）

- FR-1.1 数据文件必须包含 `source` 字段，取值：`live`（真实抓取成功）| `stale`（保留上一次真实数据）| `mock`（仅本地调试允许）
- FR-1.2 **生产环境禁止生成 mock 数据**。伪造数据生成器仅在显式传入 `--allow-mock` 时可用
- FR-1.3 抓取失败时：保留上一次真实数据并标记 `stale`，**禁止覆盖为编造数据**
- FR-1.4 首次成功获取真实数据前，须清除仓库中现存的假数据文件，避免被误认为真实数据

### FR-2 正确的登录流程

- FR-2.1 删除 CAS 登录分支（`CAS_LOGIN_URL` 相关逻辑）
- FR-2.2 实现 jwxs 原生登录：
  1. `GET https://jwxs.tiangong.edu.cn/login` → 建立会话 + 提取 `tokenValue`
  2. `GET /img/captcha.jpg?<rand>`（同一会话）→ 获取验证码图片
  3. 识别验证码（自动 OCR，失败自动换图重试，上限 N 次）
  4. `POST /j_spring_security_check` 提交全部字段
  5. **登录后必须验证**：访问受保护页面，确认未被重定向回 `/login`
- FR-2.3 密码加密公式已确认（见 §8 D1）：双 md5 复合 + `{Urp602019}` 盐值，按源码实现即可

### FR-3 会话管理（v1.1 已按"每日一次完整登录"简化）

> **前提（用户已确认）**：空教室数据一天内不变化，登录一次即可取整天数据，且无常驻机器。
> 因此**不再需要**跨运行持久化、会话复用与心跳保活 —— 每次运行完整登录一次即可。

- FR-3.1 每次运行执行**一次**完整登录，随后在同一会话内抓取全部数据（两栋楼共用一次登录，不重复登录）
- FR-3.2 使用 `requests.Session` 的 cookie jar，**禁止手写 `Cookie` 请求头**
- FR-3.3 登录失败时重试（含重新拉取验证码），重试次数可配置（默认 10 次）
- FR-3.4 **不实现**会话持久化、**不实现**心跳保活（已无必要）
- FR-3.5 会话有效性校验仅用于**同一次运行内的登录确认**：请求受保护页面判断是否被重定向回 `/login`，**不得使用页面文本匹配**
- FR-3.6 移除 `TIANGONG_COOKIE` 环境变量及其读取逻辑（手工 cookie 模式彻底废弃）

### FR-4 数据解析正确性

- FR-4.1 停止 8 端点盲试，改为针对**抓包确认的单一真实接口**实现解析
- FR-4.2 移除猜测性字段映射（`roomName/r/jsmc` 等），按真实响应 schema 编写
- FR-4.3 解析结果需做类型与空值防护
- FR-4.4 输出结构与现有 `parser.py` 的 5-bit 协议保持一致（前端 `app.js` 依赖此结构，不改动前端数据模型）

### FR-5 时间与调度正确性

- FR-5.1 全链路使用 `Asia/Shanghai` 时区计算"今天"与 `updated_at`
- FR-5.2 workflow 显式设置 `TZ: Asia/Shanghai`
- FR-5.3 调度时间调整为北京时间的合理时段（建议每日 06:00–07:00，避开教务系统高峰）

### FR-6 前端数据状态提示

- FR-6.1 页面读取 `source` 字段，非 `live` 时在顶部显示醒目提示条
  - `stale` → "数据更新失败，当前显示的是 X 月 X 日 XX:XX 的数据"
  - `mock` → "当前为演示数据，非真实课表"
- FR-6.2 `updated_at` 展示为北京时间

### FR-7 可观测性与失败告警

- FR-7.1 抓取失败时进程以非零码退出，workflow 判定为失败
- FR-7.2 关键步骤输出结构化日志（登录成功/失败、验证码重试次数、抓取条数、数据来源）
- FR-7.3 支持失败通知（至少一种：GitHub Actions 邮件 / 钉钉 / Server 酱）

### FR-8 稳健性

- FR-8.1 单线程、单账号，请求间加随机间隔，避免对教务系统造成压力
- FR-8.2 全局请求头不再污染登录流程（登录与数据请求使用不同 header 集合）
- FR-8.3 凭据仅从环境变量/Secrets 读取，禁止写入代码或数据文件

---

## 4. 技术方案要点

### 4.1 登录流程（伪代码）

```python
class JwxsClient:
    BASE = "https://jwxs.tiangong.edu.cn"

    def login(self):
        # 1. 建立会话 + 取 tokenValue
        html = self.session.get(f"{self.BASE}/login").text
        token = re.search(r'name="tokenValue" value="([^"]+)"', html).group(1)

        # 2. 验证码（重试 N 次）
        for attempt in range(MAX_RETRY):
            img = self.session.get(f"{self.BASE}/img/captcha.jpg?{random.randint(0,99)}").content
            code = ocr(img)                      # ddddocr
            if not code:
                continue

            # 3. 提交登录
            r = self.session.post(f"{self.BASE}/j_spring_security_check", data={
                "lang": "zh",
                "tokenValue": token,
                "j_username": self.username,
                "j_password": self.encrypt_password(),  # md5(md5(pwd+"{Urp602019}"))+"*"+md5(md5(pwd))，见 D1
                "j_captcha": code,
                "username": "",
            }, headers={"Referer": f"{self.BASE}/login"}, allow_redirects=True)

            # 4. 真正验证登录结果
            if self.is_logged_in():
                return True
        return False

    def is_logged_in(self):
        r = self.session.get(f"{self.BASE}/student/teachingResources/freeClassroom/index",
                             allow_redirects=False)
        return r.status_code == 200 and "gotoLogin" not in r.headers.get("Location", "")
```

### 4.2 验证码识别

- 首选 `ddddocr`（`pip install ddddocr`），对强智 4 位验证码识别率较高
- 识别失败或长度异常 → 重新拉取验证码重试，上限 5 次
- 备选：本地交互式运行时允许人工输入；或接入第三方打码平台

### 4.3 会话管理（v1.1 简化模型）

**结论：不做持久化、不做心跳。**

理由：一次登录即可取整天数据，每日仅运行一次，取号与用号天然在同一 IP、同一次运行内完成 —— **IP 绑定问题自动消解**。

```
每次运行 = 完整登录一次 → 抓取全部数据 → 结束（会话随进程销毁）
```

- 不落地 `cookies.json`，不读取 `TIANGONG_COOKIE`
- 同一次运行内复用同一个 `requests.Session`
- 登录失败即重试（换验证码重来），不做跨运行恢复

### 4.4 部署架构（v1.1 已确认）

> **D2 已确认**：无常驻机器，且每日仅需运行一次。因此采用**方案 C**。

| 方案 | 说明 | 结论 |
|---|---|---|
| A. 校园网内自建 runner | 需常驻机器 | 不需要 |
| B. 校内机器 + cron | 需常驻机器 | 不需要 |
| **C. GitHub Actions 每日定时一次** | 每次运行现场登录，取号用号同一 IP | **采用** |

**为什么 IP 绑定不再是障碍**：此前担心的"cookie 跨 IP 失效"，只发生在"在一处取号、到另一处用号"的场景。改为每次运行现场登录后，取号与用号同属一次运行、同一出口 IP，会话不存在跨 IP 迁移。

**为什么不需要心跳**：会话只需在单次运行内存活（通常 < 1 分钟），远小于服务端约 30 分钟的空闲超时。

### 4.5 数据schema（保持兼容，仅增字段）

```json
{
  "source": "live",
  "updated_at": "2026-09-12 07:00:03",
  "timezone": "Asia/Shanghai",
  "buildings": ["第一公共教学楼", "第二公共教学楼"],
  "time_slots": [ ... 现有结构不变 ... ],
  "classrooms": [ ... 现有结构不变 ... ]
}
```

---

## 5. 分阶段实施计划

### P0 — 止血：让失败可见（预计 0.5 天）

| # | 任务 | 涉及文件 |
|---|---|---|
| P0-1 | 为输出增加 `source` 字段（`live`/`stale`/`mock`） | `crawler/parser.py` |
| P0-2 | mock 生成器改为显式开关 `--allow-mock`，生产禁用 | `crawler/fetch_rooms.py` |
| P0-3 | 抓取失败时保留上一次真实数据并标记 `stale`，不再编造 | `crawler/fetch_rooms.py` |
| P0-4 | 抓取失败 `sys.exit(1)`，workflow 判定失败 | `crawler/fetch_rooms.py`、`.github/workflows/daily-crawler.yml` |
| P0-5 | 前端读取 `source`，非 `live` 显示提示条 | `web/index.html`、`web/app.js`、`web/style.css` |
| P0-6 | 清除仓库中现有假数据（备份后清空 classrooms 或标记 `mock`） | `public/data/today.json`、`web/data/today.json` |

**验收**：人为让抓取失败 → workflow 变红 → 网站显示"数据更新失败"横幅 → 数据文件 `source=stale`。

### P1 — 正确的登录（核心，预计 1–2 天）

| # | 任务 | 涉及文件 |
|---|---|---|
| P1-1 | 删除 CAS 分支与所有 CAS 常量 | `crawler/fetch_rooms.py` |
| P1-2 | 新建 `JwxsClient`：实现 `/login` 访问 + `tokenValue` 提取 | 新文件 `crawler/jwxs_client.py` |
| P1-3 | 实现验证码拉取 + ddddocr 识别 + 重试 | 同上 |
| P1-4 | 实现 `POST /j_spring_security_check` | 同上 |
| P1-5 | 实现 `is_logged_in()` 真正校验 | 同上 |
| P1-6 | 移除全局请求头污染，按场景设置 header | `crawler/fetch_rooms.py` |
| P1-7 | 本地手工跑通一次完整登录，打印响应摘要 | — |

**验收**：本地运行能成功登录并打印出登录态确认信息；连续 5 次运行登录成功率 ≥ 80%。

### P2 — 登录健壮性（v1.1 简化，预计 0.5 天）

> 原计划的"会话持久化 + 心跳"已确认**不再需要**（每日一次完整登录即可）。

| # | 任务 | 涉及文件 |
|---|---|---|
| P2-1 | 一次登录、多次抓取：两栋楼共用同一会话，不重复登录 | `crawler/jwxs_client.py` |
| P2-2 | 登录重试机制：验证码识别失败或登录失败自动换图重试（默认 10 次） | 同上 |
| P2-3 | 移除手写 `Cookie` 请求头，全面改用 cookie jar | 同上 |
| P2-4 | 移除 `TIANGONG_COOKIE` 环境变量及其读取逻辑 | `crawler/fetch_rooms.py`、`daily-crawler.yml` |
| P2-5 | ~~会话持久化~~ ~~心跳保活~~ —— **已取消** | — |

**验收**：单次运行中两栋楼数据均来自同一次登录；人为注入错误验证码后能自动重试直至成功，或达上限后非零退出。

### P3 — 数据正确性与调度（预计 1 天）

| # | 任务 | 涉及文件 |
|---|---|---|
| P3-1 | 浏览器抓包确认真实数据接口 URL、请求体、响应 schema | 产出 `docs/api-schema.md` |
| P3-2 | 按真实 schema 重写解析器，移除猜测字段映射 | `crawler/parser.py` |
| P3-3 | 确认并修正 `buildingId`、日期/周次语义 | 同上 |
| P3-4 | 全链路改用 `Asia/Shanghai`，workflow 设置 `TZ` | `crawler/fetch_rooms.py`、`daily-crawler.yml` |
| P3-5 | 调整调度时间至北京 06:00–07:00 | `daily-crawler.yml` |
| P3-6 | 移除 WebVPN 分支与 8 端点盲试 | `crawler/fetch_rooms.py` |
| P3-7 | `term` 字段随学期自动推进，不再硬编码 | `crawler/parser.py` |

**验收**：连续 7 天 `source=live`；`updated_at` 为北京时间；教室数量与真实系统一致（不等于 42）。

### P4 — 上线与观察（v1.1 简化，预计 0.5 天）

> 采用方案 C：GitHub Actions 每日运行一次，**无需校园网机器**。

| # | 任务 |
|---|---|
| P4-1 | 确认调度时间为北京时间 06:00–07:00（每日一次，学生起床即可查当天课表） |
| P4-2 | 配置失败通知（Actions 邮件 / 钉钉 / Server 酱 任选其一） |
| P4-3 | README 补充：运行方式、环境变量、验证码识别率与重试说明、故障排查 |
| P4-4 | 观察 7 天，确认 `source=live` 且无人工干预 |

**验收**：连续 7 天全自动运行，`source` 均为 `live`；失败时能收到通知。

---

## 6. 全局验收标准

- [ ] 网站 `today.json` 的教室列表来自真实教务系统（数量与名称不再等于硬编码模板的 42 间）
- [ ] 连续 7 天 `source=live`，`updated_at` 为北京时间
- [ ] 无需人工粘贴任何 cookie；单次运行内自动完成登录与抓取
- [ ] 验证码识别失败时能自动重试（默认 10 次）并输出明确日志；达上限后非零退出
- [ ] 抓取失败时：workflow 变红 + 网站显示明确提示 + 数据保持上一次真实结果（`stale`）
- [ ] 代码库内不存在任何会在生产环境生成伪造数据的路径（除显式 `--allow-mock`）

---

## 7. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| **验证码识别率不足**（v1.1 首要风险） | 每日登录失败 → 当天无数据 | **重试 10 次换图**：即使单次识别率仅 60%，10 次重试后成功率 ≈ 99.99%；连续多日失败触发告警人工介入 |
| 教务系统启用更严风控（滑块/短信） | 自动登录失败 | 提前准备人工介入通道；每日仅 1 次登录，频率极低 |
| ~~会话绑定 IP，云端运行仍失败~~ | — | **v1.1 已消解**：改为每次现场登录，取号与用号同一 IP，无跨 IP 迁移 |
| ~~账号因频繁登录被锁定~~ | — | **v1.1 风险大幅降低**：每日仅 1 次登录，属极低频率 |
| 单会话互斥（他处同时登录互踢） | 偶发失败 | 定时任务排在清晨，与人工登录时段错开；失败自动重试 |
| 接口 schema 与预期不符 | 解析失败 | P3-1 先抓包确认，再写解析器 |
| 合规风险 | 账号/法律问题 | 仅限个人学号查询自用；每日 1 次、单线程；不对外提供批量接口 |

---

## 8. 待确认事项（需决策后进入实施）

> v1.2 状态：D1、D2、D3、D5 已解决，D4 已实测可行。**待确认事项全部关闭。**

| 编号 | 事项 | 说明 | 影响阶段 |
|---|---|---|---|
| **D1** ✅已解决（2026-09-12 用户抓包 + 源码破译） | 加密公式已从登录页 `onclick` 与定制版 `md5.min.js` 源码确认：<br>`j_password = md5( md5(pwd+"{Urp602019}") ) + "*" + md5( md5(pwd) )`<br>说明：① 定制版 `hex_md5(s, ver)` 在 `ver !== "1.8"` 时给原文追加盐值 `{Urp602019}`；② 两段各 32 位十六进制，中间以 `*` 连接，总长 65；③ sm3 库虽被加载但登录时**未使用**（干扰项）；④ 已与用户抓包值（`e299...*25fb...`，A≠B）结构核验一致 | P1 |
| ~~**D2**~~ | ~~运行环境能否提供校园网内常驻机器？~~ | **✅ 已解决**：无常驻机器，且确认每日仅需登录一次即可取整天数据 → 采用方案 C（GitHub Actions 每日一次）。IP 绑定与会话过期问题随之消解，会话持久化与心跳均已取消 | 已解决 |
| **D3** ✅已解决（2026-09-12 用户抓包 + 真实页面样本校准） | ① 数据**无独立 JSON 接口**，由服务器渲染进内嵌 JS 的 `tbody` 字符串（形如 `tbody += "D103 <font...>"` 后紧跟 `if (250 != null) tbody += "(250)"`）；② 页面地址：今天 `GET/POST /student/teachingResources/freeClassroom/today`，明天 `.../freeClassroomQuery/tomrrowDate`（**官方拼写 tomrrow**），后天 `.../freeClassroomQuery/afTomrrowDate`，自定义日期 `.../freeClassroomQuery/custom`；③ **切换楼栋 = POST `/student/teachingResources/freeClassroom/today`，表单 `position="{校区号}_{楼号}" & xqm="{校区名}"`**；<br>⚠️ **关键坑（2026-09-13 破译）**：`position` 不是纯楼号，而是 `校区号_楼号`（如 `01_51`）。只传楼号（20 / 51）服务端**一律 500**，不带 `position` 则 200 —— 曾据此误判"此路不通"。正确值来自楼栋列表接口返回的 `id.campusNumber` + `id.teachingBuildingNumber`；<br>⑦ **校区列表**：`POST /student/teachingResources/freeClassroom/queryCodeCampusList` → `[{campusNumber, campusName}]`（东区 02 / 西区 01 / 北区 03 / 师范大学校区 04）；<br>⑧ **首选数据源**为页面 JS 中隐藏的 JSON 接口 `GET /freeClassroom/today/{小节}?dayplus=0` → `{spareroomObjList:[{acmcBuildingName, claroom:[{classroom, classNumberOfSeats}]}]}`，优点：一次给全楼栋、带座位数、**已过去的小节也返回**（HTML 会省略）。<br>⑨ 已按"遍历校区 → 定位目标楼栋 → select_building 切换 → 逐小节查 JSON"实现，**两栋公共教学楼均已抓到真实数据**（第一公共教学楼 92 间 / 第二公共教学楼 86 间） | P3 |④ 楼栋列表 `GET /student/teachingResources/freeClassroom/queryCodeTeaBuildingList?&xqh=02`（返回 `id.teachingBuildingNumber` / `teachingBuildingName`）；⑤ **服务器不渲染已过去的小节**（如 11 点查当天，第1、2节缺席）→ 解析器对缺席小节按"未知"处理，不误判为占用；⑥ 样本已存 `crawler/fixtures/free_classroom_today.html`（学号已脱敏），解析器据此校准并验证通过（第二公共教学楼 86 间，D103 占用大节 3/4/5） | P3 |
| **D4** ✅已解决（2026-09-12 真机实测） | 已引入 `ddddocr`。真机试跑中验证码**首次尝试即识别通过**，且服务端对错误验证码返回 `badCaptcha`、对 OCR 结果返回 `badCredentials`，证明识别环节被服务端接受。配合 10 次换图重试，登录可靠性满足要求 | P1 |
| ~~**D5**~~ | ~~抓取频率：仅每日一次，还是需要更高时效？~~ | **✅ 已解决**：每日一次即可（数据一天内不变化，无需常驻与心跳） | 已解决 |

---

## 9. 附录

### 9.1 判断一个系统是否接入 CAS 的通用方法

访问其受保护页面，观察 302 跳转目标：

- 跳到 `xxx.edu.cn/cas/login?service=...` → **已接入 CAS**
- 跳到自身域下的 `/login`、`/gotoLogin` → **未接入，需走其原生登录**

本项目实测为后者。

### 9.2 关键命令

```bash
# 本地安装依赖
pip install -r crawler/requirements.txt
pip install ddddocr          # P1 起需要

# 本地调试运行（允许 mock）
python crawler/fetch_rooms.py --allow-mock

# 生产运行（禁止 mock，失败即退出）
python crawler/fetch_rooms.py

# 环境变量
export TIANGONG_USERNAME=学号
export TIANGONG_PASSWORD=密码
```

### 9.3 环境变量

| 变量 | 用途 | 备注 |
|---|---|---|
| `TIANGONG_USERNAME` | 学号 | GitHub Secrets |
| `TIANGONG_PASSWORD` | 密码 | GitHub Secrets |
| `TIANGONG_COOKIE` | （**待废弃**）手工 cookie | P2 完成后移除 |
| `TZ` | 时区 | 设为 `Asia/Shanghai` |
