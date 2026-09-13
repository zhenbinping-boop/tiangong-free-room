# Android 应用（TWA）打包与分发

适用范围：把本网站打包成一个 Android 安装包（APK）。
iOS 不在此列 —— 苹果不允许第三方内核，iOS 用户走「Safari 添加到主屏幕」，
网页端已内置该引导（`web/app.js` 的 `initInstallPrompt()`）。

## 0. 一句话原理

APK 只是一个壳，里面加载的就是 `https://zhenbinping-boop.github.io/tiangong-free-room/`。
**数据与网页实时同源**：每天 06:00 抓取更新后，App 里看到的就是最新的，不需要重新打包。
只有改动壳本身（换图标、换包名）才需要重新出包。

## 1. 已就位的资产

| 文件 | 作用 |
|---|---|
| `android/release.keystore` | 签名密钥（已生成，未入库）。密码见同目录 `release.keystore.txt` |
| `web/.well-known/assetlinks.json` | TWA 验证文件，由 `tools/make_assetlinks.py` 生成 |
| `android/user-site/` | 需要发布到 **主机根** 的同一份验证文件（见 §3） |
| `web/.nojekyll` | 保证 GitHub Pages 原样发布以 `.` 开头的目录 |
| `web/download.html` | 下载页，首页底部有入口 |
| `manifest.json` | standalone + maskable 图标齐备，PWABuilder 可直接识别 |

包名：**`app.tiangong.freeroom`**（一旦发布不可更改）。

重新生成验证文件（换签名后必做）：

```bash
python tools/make_assetlinks.py --package app.tiangong.freeroom --sha256 <新指纹>
```

指纹取自 `keytool -list -v -keystore android/release.keystore -alias tiangong-rooms`
输出里的 `SHA256:` 一行（脚本会自动去掉冒号）。

## 2. ⚠️ 结构约束：验证文件必须在「主机根」

Chrome 校验 TWA 时只认 **主机根路径**：

```
https://zhenbinping-boop.github.io/.well-known/assetlinks.json
```

而本站点是 GitHub Pages 的**项目站**，真实路径带子目录：

```
https://zhenbinping-boop.github.io/tiangong-free-room/.well-known/assetlinks.json   ← 校验器不看这里
```

也就是说，放在 `web/.well-known/` 的那一份对 TWA 校验**无效**（留着是为了将来绑定自定义域名）。
要让验证通过，三选一：

- **A（推荐，零成本）**：新建 `zhenbinping-boop.github.io` 仓库（用户站，发布到主机根），
  把 `android/user-site/` 里的 `.nojekyll` 与 `.well-known/assetlinks.json` 放进去并启用 Pages。
  该仓库只放这一个验证文件，不影响现有站点。
- **B**：给本站点绑定自定义域名（需购买域名 + CNAME），之后 `web/.well-known/` 那份自动生效。
- **C**：不做验证。能装能用，但顶部会常驻一条地址栏。

验证是否生效（任一方式）：

```bash
curl -sI https://zhenbinping-boop.github.io/.well-known/assetlinks.json | head -1
# 期望 200；404 说明还没发布到主机根
```

## 3. 出包步骤（PWABuilder，约 10 分钟，不需要本地 Android SDK）

1. 打开 <https://www.pwabuilder.com>，输入站点地址，回车分析。
2. 右上角 **Package For Stores** → **Android** → **Generate**。
3. 关键一步：在签名选项里选 **「使用我自己的签名密钥」**（Use my own signing key），
   上传 `android/release.keystore`，别名 `tiangong-rooms`，密码见 `android/release.keystore.txt`。
   **不要让它帮你生成新密钥** —— 那样指纹对不上 `assetlinks.json`，验证会失败。
4. 包名确认是 `app.tiangong.freeroom`；其余保持默认，下载 zip。
5. zip 内取 `app-release-signed.apk`，**重命名为 `tiangong-rooms.apk`**
   （下载页链接指向 GitHub Releases 的固定文件名，改名才能对上）。

## 4. 分发：上传到 GitHub Releases

1. 仓库页面 → Releases → **Create a new release**。
2. Tag 填 `app-v1`，标题例如「Android 应用 v1」。
3. 把 `tiangong-rooms.apk` **拖进附件区**（名称必须一致）。
4. 发布。下载页的按钮指向：

   ```
   https://github.com/zhenbinping-boop/tiangong-free-room/releases/latest/download/tiangong-rooms.apk
   ```

   页面加载时会探测该文件是否存在；不存在就自动收起按钮并给出「先添加到主屏幕」的说明，
   不会给用户一个 404 死链。

## 5. 出包后的自检

- [ ] 手机安装后打开是**全屏、无地址栏**（有地址栏说明 §2 的验证没生效）
- [ ] 桌面图标是本站图标，不是浏览器图标
- [ ] 首页显示的抓取时间与网页版一致（验证同源）
- [ ] `python tools/check_live.py` 仍通过（本次改动未影响站点主体）

## 6. 版本更新策略

日常数据更新**不需要**重新出包。只有下列情况才需要重发 APK：

- 换包名、换图标、改 manifest 的 `display` / `start_url`
- 将来要上架 Google Play（届时需要 AAB，PWABuilder 同页面可生成）

重发时**必须用同一把密钥**，否则已安装用户无法覆盖升级。
