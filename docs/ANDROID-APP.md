# Android 应用打包与分发

适用范围：把本网站打包成一个 Android 安装包（APK）。
iOS 不在此列 —— 苹果不允许第三方内核，iOS 用户走「Safari 添加到主屏幕」，
网页端已内置该引导（`web/app.js` 的 `initInstallPrompt()`）。

> **当前正式方案是文末的「WebView 直壳版」。**
> 前半部分（TWA）是 2026-09-13 的第一版实现，因国内机型会卡在启动屏而弃用，
> 保留仅供追溯（assetlinks 与用户站配置仍然保留，将来绑自定义域名时有用）。

## 0. 一句话原理

APK 只是一个壳，里面加载的就是 `https://zhenbinping-boop.github.io/tiangong-free-room/`。
**数据与网页实时同源**：每天 06:00 抓取更新后，App 里看到的就是最新的，不需要重新打包。
只有改动壳本身（换图标、换包名）才需要重新出包。

---

# 一、WebView 直壳版（当前正式方案，2026-09-13 起）

## 1. 为什么要换掉 TWA

TWA 实测在国内机型上**卡在启动屏**不进入页面，开代理也一样。经核对，配置本身全对：
启动 URL 是 `.../tiangong-free-room/index.html`，归属声明指向主机根且与线上
`assetlinks.json` 同源。问题出在 TWA 的两个运行前提：

1. 渲染依赖手机上装了支持 TWA 的浏览器（通常是 Chrome）—— 国产 ROM 常见禁用或缺失；
2. 隐藏地址栏前要向 Google 归属校验服务（`digitalassetlinks.googleapis.com`）查询，
   该域名在国内不可达，查询挂起即卡死。

这两条都与本项目代码无关，**无法在代码层修复**，所以改用直壳。

## 2. 直壳是什么

`android/webview-shell/` 是一个极小的 Android 工程：只有一个 `MainActivity`，
用**系统自带 WebView** 打开站点首页。不依赖 Chrome、不依赖 Google 服务、不做归属校验。

- 包名：`app.tiangong.freeroom`（与 TWA 版一致）
- 签名：同一把 `android/release.keystore` → **可直接覆盖安装**老版本
- 行为：站内链接在壳内打开，站外链接交系统浏览器；返回键先回退网页历史；
  加载失败显示重试界面，**不显示任何推测数据**
- 桌面图标复用 `web/icons/` 里的 PNG
- `minSdk 21`（Android 5.0+），`targetSdk 34`

## 3. 云端构建（本机无需 Android SDK）

仓库 Secrets 需要四项（只需配一次，Settings → Secrets and variables → Actions）：

| Secret | 值 |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | 密钥文件的 base64（本机 `D:/courses check/_keystore_base64.txt`，未入库） |
| `KEYSTORE_PASSWORD` | 见 `android/release.keystore.txt` |
| `KEY_ALIAS` | `tiangong-rooms` |
| `KEY_PASSWORD` | 与 `KEYSTORE_PASSWORD` 相同 |

出包：Actions → **Build Android Shell APK** → Run workflow（约 3–5 分钟）。
该 workflow 依次：装 JDK/Android SDK/Gradle → 用密钥签名 → `apksigner` 验证签名 →
把 APK 提交到 `web/download/tiangong-rooms.apk` → 自动发布 Pages → 上传构建产物。

改壳再出包时，记得把 `app/build.gradle` 里的 `versionCode` +1。

## 4. 分发与更新

- 主下载源是**站内自托管**：`web/download/tiangong-rooms.apk`（与页面同域名，国内可达）。
  GitHub Release 只作备用直链 —— Release 直链会 302 到 `objects.githubusercontent.com`，
  国内移动网络基本不通，**绝不能当主链**。
- 换 APK 或改 `download.html` 后必须 bump `web/sw.js` 的 `CACHE_VERSION`。
- 只用同一把密钥签名，用户才能覆盖升级；密钥丢失 = 只能换包名重新分发。

---

# 二、TWA 版（已弃用，保留追溯）

## 1. 相关资产

| 文件 | 作用 |
|---|---|
| `android/release.keystore` | 签名密钥（未入库）。密码见同目录 `release.keystore.txt` |
| `web/.well-known/assetlinks.json` | TWA 验证文件，由 `tools/make_assetlinks.py` 生成 |
| `android/user-site/` | 已发布到**主机根**的同一份验证文件（仓库 `zhenbinping-boop.github.io`） |
| `web/.nojekyll` | 保证 Pages 原样发布以 `.` 开头的目录 |
| `web/download.html` | 下载页，首页底部有入口 |

包名 `app.tiangong.freeroom`。重新生成验证文件（换签名后必做）：

```bash
python tools/make_assetlinks.py --package app.tiangong.freeroom --sha256 <新指纹>
```

## 2. 结构约束：验证文件必须在「主机根」

Chrome 校验只认 `https://zhenbinping-boop.github.io/.well-known/assetlinks.json`；
本站点是 Pages **项目站**（带 `/tiangong-free-room/` 子路径），
放在 `web/.well-known/` 的那一份对校验**无效**。
已通过建立用户站仓库 `zhenbinping-boop.github.io` 解决（内容见 `android/user-site/`）。

## 3. 出包步骤（PWABuilder）

1. 输入站点地址 → **Package For Stores** → **Android**；
2. **Package ID 必须手改成 `app.tiangong.freeroom`**（默认是网址倒序 `io.github...twa`，
   不改就与 assetlinks 对不上，验证必然失败）；
3. 签名选「使用我自己的密钥」，上传 `android/release.keystore`，
   别名 `tiangong-rooms`，两个密码相同；
4. 出包后取 `app-release-signed.apk`。

## 4. 出包后自检

- [ ] 能正常进入页面（卡启动屏 = TWA 前提不满足，改走直壳版）
- [ ] 全屏无地址栏（有地址栏 = 归属校验未生效）
- [ ] 首页显示的抓取时间与网页版一致
- [ ] `python tools/check_live.py` 仍通过
