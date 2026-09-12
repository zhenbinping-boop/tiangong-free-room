# -*- coding: utf-8 -*-
"""
jwxs.tiangong.edu.cn (强智 URP) 原生登录客户端。

认证流程（依据 2026-09-12 抓包 + 登录页源码破译，详见 docs/PRD-修复计划.md D1/D3）：
  1. GET  /login                    → 取会话 Cookie + 动态隐藏字段 tokenValue
  2. GET  /img/captcha.jpg          → 下载图形验证码（4 位，绑定会话）
  3. POST /j_spring_security_check  → lang / tokenValue / j_username / j_password / j_captcha
     j_password = md5(md5(pwd+"{Urp602019}")) + "*" + md5(md5(pwd))
     （定制版 hex_md5(s, ver)：ver !== "1.8" 时追加盐 "{Urp602019}"）
  4. 成功标志：POST 后 302 跳转到 index?mobile=false；失败则回到登录页。
     最终以"能否 200 取到 /freeClassroom/today 页面"作为会话有效性判据。

注意：页面虽加载了 sm3 相关 JS，但登录时未使用（干扰项）。
"""

import re
import time
import hashlib
from typing import Dict, List, Optional, Tuple  # noqa: F401

import requests

BASE_URL = "https://jwxs.tiangong.edu.cn"
LOGIN_PAGE_URL = f"{BASE_URL}/login"
LOGIN_POST_URL = f"{BASE_URL}/j_spring_security_check"
CAPTCHA_URL = f"{BASE_URL}/img/captcha.jpg"
FREE_TODAY_URL = f"{BASE_URL}/student/teachingResources/freeClassroom/today"
# 官方拼写即为 tomrrow（不是 tomorrow），勿"修正"
FREE_TOMORROW_URL = f"{BASE_URL}/student/teachingResources/freeClassroomQuery/tomrrowDate"
# 楼栋列表（GET，参数形如 ?&xqh=02）；返回 id.campusNumber / id.teachingBuildingNumber / teachingBuildingName
BUILDING_LIST_URL = f"{BASE_URL}/student/teachingResources/freeClassroom/queryCodeTeaBuildingList"
# 校区列表（POST）；返回 [{campusNumber, campusName}]
CAMPUS_LIST_URL = f"{BASE_URL}/student/teachingResources/freeClassroom/queryCodeCampusList"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

TOKEN_VALUE_RE = re.compile(
    r'name=["\']tokenValue["\'][^>]*value=["\']([0-9a-fA-F]{16,64})["\']'
)
XQH_RE = re.compile(r'id=["\']xqh["\'][^>]*value=["\']([^"\']*)["\']')
XQM_RE = re.compile(r'id=["\']xqm["\'][^>]*value=["\']([^"\']*)["\']')
CAPTCHA_MAX_ATTEMPTS = 10


def encrypt_password(pwd: str) -> str:
    """
    复刻登录按钮 onclick 中的密码加密（见 md5.min.js 定制源码）：
      A = md5( md5(pwd + "{Urp602019}") )   # hex_md5(hex_md5(pwd), '1.8')
      B = md5( md5(pwd) )                   # hex_md5(hex_md5(pwd, '1.8'), '1.8')
      j_password = A + "*" + B              # 总长 65 字符
    """
    def md5hex(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    part_a = md5hex(md5hex(pwd + "{Urp602019}"))
    part_b = md5hex(md5hex(pwd))
    return f"{part_a}*{part_b}"


class JwxsError(RuntimeError):
    """jwxs 客户端致命错误（登录失败 / 数据不可达）。"""


class JwxsClient:
    """持有会话的 jwxs 教务系统客户端。凭据来自环境变量 TIANGONG_USERNAME / TIANGONG_PASSWORD。"""

    def __init__(self, username: str, password: str, captcha_attempts: int = CAPTCHA_MAX_ATTEMPTS):
        self.username = (username or "").strip()
        self.password = (password or "").strip()
        self.captcha_attempts = captcha_attempts
        if not self.username or not self.password:
            raise JwxsError("缺少 TIANGONG_USERNAME / TIANGONG_PASSWORD 环境变量（或命令行参数）")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self._ocr = None  # 延迟加载 ddddocr

    # ---------- 验证码识别 ----------

    def _get_ocr(self):
        if self._ocr is None:
            try:
                import ddddocr  # type: ignore
            except ImportError as e:
                raise JwxsError(
                    "未安装 ddddocr，无法识别验证码。请在 crawler/requirements.txt 环境中安装：pip install ddddocr"
                ) from e
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    def _solve_captcha(self) -> str:
        resp = self.session.get(CAPTCHA_URL, timeout=15)
        resp.raise_for_status()
        code = self._get_ocr().classification(resp.content)
        return re.sub(r"[^0-9a-zA-Z]", "", code or "")

    # ---------- 会话有效性判断 ----------

    def is_logged_in(self) -> bool:
        """判据：直接请求受保护页面，200 即有效（不再使用页面文本匹配）。"""
        try:
            resp = self.session.get(FREE_TODAY_URL, allow_redirects=False, timeout=15)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    # ---------- 登录 ----------

    def login(self, verbose: bool = True) -> None:
        """完整登录流程；失败（含验证码重试耗尽）抛 JwxsError。成功后 session 处于已登录状态。"""
        if self.is_logged_in():
            if verbose:
                print("[JwxsClient] 会话仍有效，跳过登录")
            return

        if verbose:
            print("[JwxsClient] 访问登录页获取 tokenValue ...")
        page = self.session.get(LOGIN_PAGE_URL, timeout=15)
        page.raise_for_status()
        m = TOKEN_VALUE_RE.search(page.text)
        if not m:
            raise JwxsError("登录页中未找到 tokenValue，页面结构可能已变更")
        token_value = m.group(1)

        last_err = "未知原因"
        for attempt in range(1, self.captcha_attempts + 1):
            # 每次尝试都重新取登录页：失败后服务端会刷新 tokenValue，沿用旧值只会得到 200 重绘页面
            if attempt > 1:
                page = self.session.get(LOGIN_PAGE_URL, timeout=15)
                page.raise_for_status()
                m = TOKEN_VALUE_RE.search(page.text)
                if not m:
                    continue
                token_value = m.group(1)
            try:
                captcha_code = self._solve_captcha()
            except JwxsError:
                raise
            except Exception as e:
                last_err = f"验证码获取/识别异常: {e}"
                if verbose:
                    print(f"[JwxsClient] 第{attempt}次 {last_err}")
                time.sleep(1)
                continue

            if not captcha_code:
                last_err = "验证码识别结果为空"
                if verbose:
                    print(f"[JwxsClient] 第{attempt}次 {last_err}，换图重试")
                continue

            form = {
                "lang": "zh",
                "tokenValue": token_value,
                "j_username": self.username,
                "j_password": encrypt_password(self.password),
                "j_captcha": captcha_code,
            }
            try:
                resp = self.session.post(
                    LOGIN_POST_URL, data=form, timeout=15, allow_redirects=False
                )
            except requests.RequestException as e:
                last_err = f"登录 POST 异常: {e}"
                if verbose:
                    print(f"[JwxsClient] 第{attempt}次 {last_err}")
                continue

            # 成功 → 302 到 index?mobile=false；失败 → 回登录页(200)或 302 到 login
            location = resp.headers.get("Location", "")
            redirected_ok = resp.status_code in (301, 302, 303) and "login" not in location.lower()
            if redirected_ok and self.is_logged_in():
                if verbose:
                    print(f"[JwxsClient] 登录成功（第{attempt}次尝试，验证码={captcha_code}）")
                return
            last_err = f"HTTP {resp.status_code} Location={location or '-'}"
            if verbose:
                print(f"[JwxsClient] 第{attempt}次登录未通过（验证码可能识别错误），{last_err}")

        raise JwxsError(f"登录失败：验证码重试 {self.captcha_attempts} 次均未成功。最后错误：{last_err}")

    # ---------- 数据获取 ----------

    def fetch_page(self, url: str) -> str:
        """取受保护页面 HTML；被重定向到登录则自动重登一次。"""
        resp = self.session.get(url, timeout=20, allow_redirects=False)
        if resp.status_code in (301, 302, 303):
            self.login(verbose=False)
            resp = self.session.get(url, timeout=20, allow_redirects=False)
        if resp.status_code != 200:
            raise JwxsError(f"获取 {url} 失败：HTTP {resp.status_code}")
        return resp.text

    def fetch_today_html(self) -> str:
        return self.fetch_page(FREE_TODAY_URL)

    # ---------- 楼栋相关 ----------

    def get_default_campus(self) -> Tuple[str, str]:
        """从默认 today 页面读取当前校区：返回 (xqh, xqm)。"""
        html = self.fetch_today_html()
        xqh = XQH_RE.search(html)
        xqm = XQM_RE.search(html)
        return (xqh.group(1).strip() if xqh else "02", xqm.group(1).strip() if xqm else "东区")

    def fetch_campus_list(self) -> List[Dict[str, str]]:
        """
        获取校区列表：返回 [{"number": "02", "name": "东区"}, ...]
        接口：POST /student/teachingResources/freeClassroom/queryCodeCampusList
        """
        try:
            resp = self.session.post(CAMPUS_LIST_URL, timeout=20, allow_redirects=False)
        except requests.RequestException as e:
            raise JwxsError(f"获取校区列表失败：{e}")
        if resp.status_code != 200:
            raise JwxsError(f"获取校区列表失败：HTTP {resp.status_code}")
        try:
            data = resp.json() or []
        except ValueError as e:
            raise JwxsError(f"校区列表非 JSON（可能会话失效）：{e}")
        result = []
        for item in data:
            number = str(item.get("campusNumber") or "").strip()
            name = (item.get("campusName") or "").strip()
            if number and name:
                result.append({"number": number, "name": name})
        if not result:
            raise JwxsError("校区列表为空，接口结构可能已变更")
        return result

    def fetch_building_list(self, xqh: str = "02") -> Dict[str, Dict[str, str]]:
        """
        获取指定校区的楼栋列表：返回 {楼栋名: {"number": 楼号, "campus_number": 校区号}}
        接口：GET /student/teachingResources/freeClassroom/queryCodeTeaBuildingList?&xqh=02
        """
        url = f"{BUILDING_LIST_URL}?&xqh={xqh}"
        try:
            resp = self.session.get(url, timeout=20, allow_redirects=False)
        except requests.RequestException as e:
            raise JwxsError(f"获取楼栋列表失败：{e}")
        if resp.status_code != 200:
            raise JwxsError(f"获取楼栋列表失败：HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise JwxsError(f"楼栋列表非 JSON（可能会话失效）：{e}")
        mapping: Dict[str, Dict[str, str]] = {}
        for item in data or []:
            ident = item.get("id") or {}
            number = ident.get("teachingBuildingNumber") or item.get("teachingBuildingNumber")
            campus_number = ident.get("campusNumber") or item.get("campusNumber") or xqh
            name = item.get("teachingBuildingName")
            if name and number:
                mapping[name.strip()] = {
                    "number": str(number).strip(),
                    "campus_number": str(campus_number).strip(),
                }
        return mapping

    def select_building(self, campus_number: str, building_number: str, campus_name: str) -> None:
        """
        切换"当前楼栋"（会同时把会话校区切到该楼所属校区）。

        关键坑（2026-09-13 抓包破译）：position 不是纯楼号，而是 "{校区号}_{楼号}"。
        只传楼号（如 20 / 51）服务端一律 500。
        接口：POST /student/teachingResources/freeClassroom/today
             表单 position="{campusNumber}_{teachingBuildingNumber}" & xqm="{校区名}"
        """
        if "_" not in str(building_number):
            position = f"{campus_number}_{building_number}"
        else:
            position = str(building_number)
        payload = {"position": position, "xqm": campus_name}
        try:
            resp = self.session.post(FREE_TODAY_URL, data=payload, timeout=20, allow_redirects=False)
        except requests.RequestException as e:
            raise JwxsError(f"切换楼栋 {campus_name}/{building_number} 失败：{e}")
        if resp.status_code in (301, 302, 303):
            self.login(verbose=False)
            resp = self.session.post(FREE_TODAY_URL, data=payload, timeout=20, allow_redirects=False)
        if resp.status_code != 200:
            raise JwxsError(
                f"切换楼栋 {campus_name}/{building_number}（position={position}）失败：HTTP {resp.status_code}"
            )

    def fetch_free_rooms(self, period: int, dayplus: int = 0) -> list:
        """
        JSON 空教室接口（首选数据源）：
            GET /student/teachingResources/freeClassroom/today/{小节}?dayplus=0
        返回 spareroomObjList：[{acmcBuildingName, claroom:[{classroom, classNumberOfSeats}]}]

        该接口返回**当前会话选定的楼栋**（默认楼栋为会话默认校区下的一栋）。
        要查其他楼栋，须先调用 select_building() 切换（position 格式为 "校区号_楼号"）。
        """
        url = f"{FREE_TODAY_URL}/{period}"
        resp = self.session.get(url, params={"dayplus": dayplus}, timeout=20, allow_redirects=False)
        if resp.status_code in (301, 302, 303):
            self.login(verbose=False)
            resp = self.session.get(url, params={"dayplus": dayplus}, timeout=20, allow_redirects=False)
        if resp.status_code != 200:
            raise JwxsError(f"查询第{period}节空教室失败：HTTP {resp.status_code}")
        try:
            return (resp.json() or {}).get("spareroomObjList") or []
        except ValueError as e:
            raise JwxsError(f"第{period}节返回非 JSON（可能会话失效）：{e}")

    def fetch_all_periods(self, periods=range(1, 11), dayplus: int = 0) -> dict:
        """按小节逐个查询，返回 {小节: spareroomObjList}。"""
        result = {}
        for p in periods:
            result[p] = self.fetch_free_rooms(p, dayplus=dayplus)
        return result


if __name__ == "__main__":
    # 自检：密码加密格式（无需真实凭据）
    demo = encrypt_password("test1234")
    a, b = demo.split("*")
    assert len(a) == 32 and len(b) == 32 and a != b, "加密格式异常"
    print("encrypt_password 格式自检通过:", demo)
