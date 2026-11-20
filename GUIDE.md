# Piik 接入 NTK 账号 · 使用说明

这个包给**已经在跑 Piik 的站点**加上 NTK 账号登录。不改 Go 后端、不 fork 代码、不动数据库，只往你的前端源码里注入几个文件，然后重新构建。

装完的效果：

- 右上角出现「Sign in with NTK / 使用 NTK 账号登录」按钮
- 登录后显示账号头像和昵称，旁边有「退出」
- 退出会同时清掉 Piik 本地登录态和账号中心会话，然后跳回你的站点
- 用户在账号中心登出后，Piik 会自动同步登出（页面加载、切回标签页、每 30 秒各探测一次）

两个可调策略：

| 策略 | 默认 | 说明 |
|---|---|---|
| 登录方式 | 可选登录 | 不登录也能正常用 Piik，登录完全自愿 |
| 昵称 | 锁定 | 登录后房间昵称固定为账号昵称，用户不能自己改 |

开启「登录守卫」后，访客进站不会被拦，只有点站内功能时才在右上角弹出「请先登录 NTK 账号」，点「立即登录」才跳转，点「稍后」就关掉。

---

## 一、动手之前先自查

| 条件 | 怎么确认 |
|---|---|
| Piik 是源码部署 | 源码根目录有 `package.json` |
| 能构建前端 | `npm run build` 原本就能成功跑完 |
| 能编译 Go | 有 `go.mod` 和 `cmd/` 目录，`go` 命令可用 |
| 有 HTTPS 域名 | 回调地址必须是 `https://`，不能用 IP 或 http |
| 有开发者账号 | 在开放平台注册并通过认证 |

建议先跑一遍，确认原项目本来是好的，出问题好定位：

```bash
cd /path/to/your/Piik
node -v
npm -v
npm run build
```

> Piik 的前端资源是 `go:embed` 打进二进制的。只跑 `npm run build` 页面不会有任何变化，必须重新编译 Go 二进制。这一点最容易踩坑，安装脚本会自动帮你编译并提示替换。

---

## 二、第一步：申请应用，拿到 client_id

1. 打开 <https://program.natsuko.online>，登录后进入开发者中心。
2. 完成开发者认证（未认证不能创建应用）。
3. 「我的应用」→ 新建应用 → 应用模板选 **Piik 站点登录**。
4. 填写：

| 字段 | 填什么 |
|---|---|
| 站点名称 | 你的 Piik 站名字，审核时用来辨认 |
| 简介 | 一句话说明站点用途 |
| 站点主页 | `https://piik.example.com` |
| 回调地址 | `https://piik.example.com/auth/callback.html` |
| 联系人 | 邮箱或 QQ，审核有疑问会联系你 |

**回调地址有硬性要求，写错会登录失败：**

- 必须是 `https://` 开头
- 必须以 `/auth/callback.html` 结尾
- 域名要和实际访问的域名完全一致（含子域名）
- 不能带查询参数

正确：`https://piik.example.com/auth/callback.html`

错误：`http://piik.example.com/auth/callback.html`（非 https）、`https://piik.example.com/`（不是回调页）、`https://piik.example.com/auth/callback.html?x=1`（带参数）

5. 提交后等管理员审核。审核通过后，在应用列表复制 `client_id`（形如 `nk_xxxxxxxx`）。

> 一个 `client_id` 只对应一个域名。换域名需要回开发者中心改回调地址并重新审核。

---

## 三、第二步：安装

把压缩包传到服务器并解压：

```bash
unzip piik-ntk-login.zip -d /root/
```

**进入 Piik 源码根目录**（脚本用当前目录作为注入目标，必须在源码根目录执行）：

```bash
cd /path/to/your/Piik

bash /root/piik-ntk-login/install.sh \
  --client-id nk_你的client_id \
  --redirect-uri https://piik.example.com/auth/callback.html
```

### 参数一览

| 参数 | 必填 | 默认 | 作用 |
|---|---|---|---|
| `--client-id` | 是 | 无 | 审核通过后拿到的 `nk_` 开头 ID |
| `--redirect-uri` | 是 | 无 | 与应用登记完全一致的回调地址 |
| `--origin` | 否 | `https://account.natsuko.online` | 账号中心地址，只有自托管才需要改 |
| `--require-login` | 否 | 关 | 登录守卫：点站内功能才提示登录 |
| `--optional-login` | 否 | 开 | 纯可选登录，不弹任何提示 |
| `--no-lock-name` | 否 | 锁 | 允许登录后自行修改房间昵称 |
| `--no-build` | 否 | 构建 | 只注入代码，构建和编译自己来 |

常见组合：

```bash
# 展示型站点：先让人逛，点功能再引导登录
bash install.sh --client-id nk_xxx --redirect-uri https://piik.example.com/auth/callback.html --require-login

# 内部/会员站：昵称也要固定
bash install.sh --client-id nk_xxx --redirect-uri https://piik.example.com/auth/callback.html --require-login

# 允许用户自己改昵称
bash install.sh --client-id nk_xxx --redirect-uri https://piik.example.com/auth/callback.html --no-lock-name

# 自己控制构建时机
bash install.sh --client-id nk_xxx --redirect-uri https://piik.example.com/auth/callback.html --no-build
```

### 脚本做了什么

1. 把要改的文件备份到 `Piik/.natsuko-backup/<时间戳>/`
2. 写入 `src/client/lib/account.ts` 和 `public/auth/callback.html`，填入你的 client_id 和回调地址
3. 在 `main.tsx` 里挂上账号模块初始化
4. 用锚点往 `Header.tsx` 插入登录按钮和头像菜单（保留你版本里的其它改动）
5. 补中英文案和样式
6. 执行 `npm run build`
7. 检测到 `go.mod` 时自动编译出 `piik-server.new`

脚本是幂等的：重复跑不会重复插入代码，之前装过旧版也可以直接覆盖升级。

---

## 四、第三步：替换二进制并重启

脚本编译出 `piik-server.new` 后，先停服务再替换，否则会遇到 `Text file busy`：

```bash
# 1. 停服务
systemctl stop piik

# 2. 备份旧二进制
cp -f /path/to/deploy/piik-server /path/to/deploy/piik-server.bak-$(date +%Y%m%d)

# 3. 替换
cp -f /path/to/your/Piik/piik-server.new /path/to/deploy/piik-server
chmod 755 /path/to/deploy/piik-server

# 4. 启动
systemctl start piik
systemctl is-active piik
```

Docker 部署：

```bash
docker cp /path/to/your/Piik/piik-server.new <容器名>:/app/piik-server
docker restart <容器名>
```

如果脚本没有编译出二进制（没装 go 或找不到入口），手动来一次：

```bash
CGO_ENABLED=0 go build -trimpath -o piik-server.new ./cmd/piik-server
```

---

## 五、验收清单

按顺序点一遍，全部通过就算接入成功：

- [ ] 未登录访问首页，页面正常显示，**没有**被强制跳去登录页
- [ ] 右上角能看到「登录 / Sign in with NTK」按钮
- [ ] 点登录 → 跳到 `account.natsuko.online` → 登录/注册 → 自动跳回站点
- [ ] 跳回后右上角显示你的账号头像和昵称
- [ ] 开启 `--require-login` 时：点任意站内功能，右上角弹「请先登录 NTK 账号」，点「稍后」能关掉
- [ ] 点「退出」→ 回到站点首页，右上角变回登录按钮
- [ ] 在账号中心点退出，再切回 Piik 标签页，几秒内自动变成未登录状态

---

## 六、日常行为说明

**登录**：点按钮跳转账号中心，用 PKCE 授权码流程换 token，token 存在浏览器 `localStorage`，不上传到任何服务器。

**退出**：清掉 Piik 本地的头像昵称和 token，跳转账号中心的 `end_session` 结束会话，然后回到你的站点首页。

**会话同步**：Piik 在页面加载、切回标签页、每 30 秒各探测一次账号中心会话状态。账号中心用 `nk_seen` 标记区分「从来没登录过」和「登录过但已登出」，后者会明确告诉 Piik 清掉本地登录态。

**昵称**：默认登录后昵称锁定为账号昵称，用户不能在房间设置里改。用 `--no-lock-name` 可以放开。

**头像**：账号没设置头像时，自动使用平台默认头像，不会出现空白或裂图。

---

## 七、升级与重装

Piik 升级了新版本后，按这个顺序来：

```bash
# 1. 先回滚，还原干净源码
bash /root/piik-ntk-login/rollback.sh

# 2. 升级 Piik 本体
# 3. 重新接入
bash /root/piik-ntk-login/install.sh --client-id nk_xxx --redirect-uri https://piik.example.com/auth/callback.html
```

只想改策略（比如从可选登录改成登录守卫），不用回滚，直接带新参数重跑 `install.sh` 即可。

---

## 八、回滚

```bash
cd /path/to/your/Piik
bash /root/piik-ntk-login/rollback.sh
npm run build
CGO_ENABLED=0 go build -trimpath -o piik-server.new ./cmd/piik-server
# 停服 → 替换二进制 → 启服
```

回滚会从最近一次 `.natsuko-backup/<时间戳>/` 还原被修改的文件，并删掉注入的 `account.ts` 和 `callback.html`。

> 回滚只还原**最近一次**备份。如果你连续装了两次，回滚回到的是第一次装完的状态。要完全还原，先升到最新备份不覆盖的干净版本，或者用 git 恢复。

---

## 九、排错

| 现象 | 原因 | 处理 |
|---|---|---|
| 右上角没有登录按钮 | 注入没生效，或没重新编译 | `grep NATSUKO_OIDC_ADDON src/client/components/living/Header.tsx` 应有输出；确认重新 build 并替换了二进制 |
| `npm run build` 成功但页面没变化 | 只构建了前端，二进制还是旧的 embed | 重新 `go build` 并替换正在运行的二进制 |
| 点登录报 `redirect_uri` 不匹配 | 回调地址与应用登记不一致 | 两边改成完全一样的字符串，注意 https 和末尾路径 |
| 登录跳回来了但没头像 | 回调页处理失败 | F12 打开控制台，看 `auth/callback.html` 的报错 |
| 注入时报「锚点未找到」 | 你的 Piik 版本改动较大 | 脚本已自动回滚，文件没被破坏；对照 `template/` 手动合入 |
| 退出后又变回已登录 | 浏览器残留同名旧 cookie | 清除该站点的 Cookie 和网站数据，再退出一次 |
| 账号中心登出了，Piik 还显示头像 | 浏览器禁用了第三方 Cookie | 手动点 Piik 里的「退出」；或把两个域名放在同一主域下 |
| `Text file busy` | 直接覆盖了正在运行的二进制 | 先 `systemctl stop`，替换后再启动 |
| 重启后 502 | 二进制没起来 | `systemctl status piik` 看日志，检查文件权限是不是 `www` |

---

## 附录 A：文件清单

```
piik-ntk-login/
├── GUIDE.md                  本说明（完整版）
├── README.md                 速查版
├── install.sh                一键安装：注入 + 构建 + 编译
├── inject.py                 注入器（幂等）
├── rollback.sh               回滚脚本
└── template/
    ├── src/client/lib/account.ts     OIDC 客户端（PKCE、会话同步、登录守卫）
    └── public/auth/callback.html     静态回调页
```

## 附录 B：会改动你源码的哪些位置

| 文件 | 改动方式 |
|---|---|
| `src/client/lib/account.ts` | 新增 |
| `public/auth/callback.html` | 新增 |
| `src/client/main.tsx` | 插入 import 和 `initAccount()` 调用 |
| `src/client/components/living/Header.tsx` | 插入登录按钮与账号菜单 |
| `src/client/locales/zh.ts` / `en.ts` | 补登录相关文案 |
| `src/client/styles.css` | 补按钮与提示浮层样式 |

所有改动都有 `NATSUKO_OIDC_ADDON` 标记，方便你在 diff 里认出来，也方便回滚时定位。

## 附录 C：命令速查

```bash
# 安装
cd /path/to/Piik && bash /root/piik-ntk-login/install.sh \
  --client-id nk_xxx --redirect-uri https://piik.example.com/auth/callback.html

# 只注入不构建
... --no-build

# 回滚
cd /path/to/Piik && bash /root/piik-ntk-login/rollback.sh

# 检查注入是否在位
grep -c NATSUKO_OIDC_ADDON src/client/components/living/Header.tsx

# 检查回调地址是否写对
grep -n "REDIRECT_URI" src/client/lib/account.ts

# 手动编译
CGO_ENABLED=0 go build -trimpath -o piik-server.new ./cmd/piik-server
```
