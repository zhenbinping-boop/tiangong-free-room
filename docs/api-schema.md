# 教务系统接口真源（jwxs）

本文档记录本项目实际依赖的教务系统接口与响应结构，**以抓包与源码破译为唯一依据**。
字段名与语义未确认前不得猜测 —— 曾因猜测导致登录从未成功（见 `docs/代码审查报告.md`）。

- 基址：`https://jwxs.tiangong.edu.cn`
- 系统：强智 URP，Spring Security，校方编号 `schoolId=100018`
- 实现位置：`crawler/jwxs_client.py`（登录与数据获取）、`crawler/parser.py`（结构映射）

---

## 1. 登录流程

| 步骤 | 请求 | 说明 |
|---|---|---|
| 1 | `GET /login` | 建立会话（`JSESSIONID` + `student.urpSoft.cn`，HttpOnly、会话级），提取动态隐藏字段 `tokenValue` |
| 2 | `GET /img/captcha.jpg?<rand>` | 4 位图形验证码，**必须同一会话**；用 ddddocr 识别 |
| 3 | `POST /j_spring_security_check` | 表单见下表 |
| 4 | `GET /student/teachingResources/freeClassroom/today` | 会话有效性判定：`200` 且未被重定向回 `/login` |

### 1.1 登录表单字段

```
lang=zh
tokenValue=<第 1 步提取>
j_username=<学号>
j_password=<见 1.2 加密公式>
j_captcha=<第 2 步识别结果>
username=<隐藏字段，空值>
```

### 1.2 密码加密公式（D1 破译）

```
j_password = md5( md5(pwd + "{Urp602019}") ) + "*" + md5( md5(pwd) )
```

- 定制版 `hex_md5(s, ver)` 在 `ver !== "1.8"` 时给原文追加盐值 `{Urp602019}`
- 两段各 32 位十六进制，中间以 `*` 连接，总长 65
- 页面加载的 `sm3/*.js` 是干扰项，登录**未使用**

### 1.3 已知坑

- **`tokenValue` 每次 `GET /login` 都刷新**，且登录失败后服务端也会刷新 → 重试必须重新 GET `/login`，不能复用旧值
- **不走 CAS**：`pt.tiangong.edu.cn` 明确拒绝为 jwxs 签发票据（返回"未认证授权服务"）
- 服务端错误码：`badCaptcha`（验证码错）、`badCredentials`（账号密码错）；两者可区分，用于决定是否换图重试
- **会话判定禁止使用页面文本匹配**，只能看受保护页的状态码与重定向目标（BUG-03 教训）

---

## 2. 元数据接口

### 2.1 校区列表

```
POST /student/teachingResources/freeClassroom/queryCodeCampusList
→ [{ campusNumber, campusName }]
```

确认值：东区 `02` ｜ 西区 `01` ｜ 北区 `03` ｜ 师范大学校区 `04`

### 2.2 楼栋列表

```
GET /student/teachingResources/freeClassroom/queryCodeTeaBuildingList?&xqh={校区号}
→ [{ id: { campusNumber, teachingBuildingNumber }, teachingBuildingName }]
```

楼栋号做双重兼容读取：优先 `id.teachingBuildingNumber`，回退顶层同名字段。

---

## 3. 数据接口（首选源）

```
GET /student/teachingResources/freeClassroom/today/{小节}?dayplus=0
→ { spareroomObjList: [ { acmcBuildingName, claroom: [ { classroom, classNumberOfSeats } ] } ] }
```

- `{小节}` 为 1–10 的单个小节号，需逐个查询
- `dayplus=0` 今天；明天接口见 §4
- **优点**：一次返回全楼栋、带座位数，且**已过去的小节也会返回**（HTML 版会省略）
- 返回集按 `acmcBuildingName` 过滤出目标楼栋，其余忽略

### 3.1 切换楼栋（关键坑）

```
POST /student/teachingResources/freeClassroom/today
表单：position="{校区号}_{楼栋号}"  &  xqm="{校区名}"
```

- **`position` 不是纯楼号**，而是 `校区号_楼号`（如 `01_51`）。
  只传楼号（`20` / `51`）服务端**一律 500**；不带 `position` 则 200 —— 曾据此误判"此路不通"
- `xqm` 取自页面隐藏字段 `id="xqm"`，默认兜底"东区"
- 取数前必须先切到目标楼栋，否则拿到的是上一次选中的楼栋

---

## 4. 其他日期入口（当前未启用）

`/student/teachingResources/freeClassroomQuery/` 下：

| 路径 | 含义 |
|---|---|
| `tomrrowDate` | 明天（**官方拼写多一个 r，勿"修正"**） |
| `afTomrrowDate` | 后天 |
| `custom` | 自定义日期 |

产品当前只做"今天"，是否需要明天查询尚未决定（见 `PRODUCT.md`），**不得替它编造答案**。

---

## 5. 数据模型映射

`today.json` 一节由 `crawler/parser.py` 产出：

| 字段 | 含义 |
|---|---|
| `source` | `live` = 实时抓取成功；其他值 → 前端显示"非实时"横幅 |
| `data_date` | 数据所属日期（北京时间 `YYYY-MM-DD`） |
| `buildings` | 固定两栋：第一公共教学楼、第二公共教学楼 |
| `classrooms[].room` / `.cap` | 房号 / 座位数 |
| `classrooms[].occ` | **占用位掩码**：1 / 2 / 4 / 8 / 16 = 五大节 |

小节 → 大节映射（`crawler/rooms_parser.py`）：

```
(1,2) → 第1大节   (3,4) → 第2大节   (5,6) → 第3大节   (7,8) → 第4大节   (9,10) → 第5大节
```

### 5.1 已知边界（诚实记录）

- 小节 → 大节是"任一子小节有课即整节占用"（保守判定）
- 若某小节在响应中缺席，该大节按**未知**处理（不计为占用）。
  首选 JSON 接口会返回全部小节，正常不会出现；HTML 版解析器（`rooms_parser.py`）作为兜底保留，
  在响应不完整时可能把"未知"呈现为"空闲" —— 这是**已知的宽松行为**，不是数据伪造，但值得留意
- 教室类型字段 `t` **全空**，不可用于筛选或展示（数据缺失，非本项目可解）
