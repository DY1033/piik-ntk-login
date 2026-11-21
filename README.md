# Piik · NTK 登录加装包

给**已经装好 Piik 的站点**加上 NTK 账号登录，不改 Go 后端，只注入前端代码。

效果：站点右上角出现「Sign in with NTK / 使用 NTK 账号登录」按钮；用户登录后显示账号昵称与头像（无头像时自动用平台默认头像），旁边有「退出」按钮。退出走标准 OIDC 登出：同时清掉 Piik 本地登录态和账号中心会话，并跳回站点。Piik 会定时/切回标签页时探测账号中心会话——**你在 account.natsuko.online 登出后，Piik 会自动同步登出**。

两个可选策略（默认）：**登录可选**（不登录也能用 Piik）、**昵称锁定**（登录后房间昵称统一为账号昵称，不能自行改）。可用参数调整（见第二步）。

---

## 前置条件

1. 你的 Piik 是**源码部署**，能执行 `npm run build`（官方 release / 自行 clone 编译均可）。
2. 你（或站点负责人）在 [NATSUKO 开放平台](https://program.natsuko.online) 注册了**开发者账号**并通过认证。
3. 已在开放平台创建一个 **Piik 登录应用**，并等管理员审核通过。

---

## 第一步：申请 Piik 应用

1. 登录 https://program.natsuko.online → 进入开发者中心。
2. 「2 · 我的应用」→「新建应用」→ 应用模板选 **Piik 站点登录**。
3. 填写：
   - 站点名称 / 简介
   - **站点主页**：如 `https://piik.example.com`
   - **联系人方式**：邮箱或 QQ（审核沟通用）
   - **回调地址**：`https://你的域名/auth/callback.html`
     - 必须是 `https://` 开头、以 `/auth/callback.html` 结尾，且与站点实际域名一致。
4. 提交后等管理员审核。Piik 模板固定使用 `openid profile email` 权限，且为**公开客户端（PKCE，无需密钥）**。
5. 审核通过后，在应用列表复制你的 `client_id`（形如 `nk_xxxxxxxx`）。

> 回调地址绑定在应用上，一个 client_id 只能用于你登记的域名。换域名需要在开发者中心编辑应用并重新审核。

---

## 第二步：安装加装包

把你下载/解压后的本目录传到服务器，然后**进入 Piik 源码根目录**执行：

```bash
cd /path/to/your/Piik

bash /path/to/piik-ntk-login/install.sh \
  --client-id   nk_你的client_id \
  --redirect-uri https://你的域名/auth/callback.html
```

账号中心默认 `https://account.natsuko.online`。如需自托管 IdP，加 `--origin https://你的账号中心`。

可选策略参数：
- `--require-login`：**登录守卫**（默认关闭）。开启后访客可以正常浏览 Piik，不会一进站就被踢去登录；只有点击站内任意功能时，右上角才弹出「请先登录 NTK 账号」提示，用户点提示里的「立即登录」才跳转账号中心。适合希望先展示站点、再引导登录的站点。
- `--optional-login`：纯可选登录（默认），不弹任何登录提示，登录完全自愿。
- `--no-lock-name`：允许登录后仍自行修改房间昵称（默认锁定为账号昵称）。
- 例如「登录守卫 + 锁昵称」：`bash install.sh --client-id nk_xxx --redirect-uri https://你的域名/auth/callback.html --require-login`
- 例如「可选登录 + 允许改名」：`bash install.sh --client-id nk_xxx --redirect-uri https://你的域名/auth/callback.html --no-lock-name`

脚本会做：

1. 备份将修改的文件到 `Piik/.natsuko-backup/<时间戳>/`
2. 写入 `src/client/lib/account.ts` 与 `public/auth/callback.html`（填入你的 client_id / 回调地址）
3. 用锚点在 `Header.tsx`、中英文案、`styles.css` 中插入登录按钮代码（保留你版本里的其它改动）
4. 执行 `npm run build`
5. 提示你重启 Piik 服务

> **老版本加装包升级**：如果之前装过旧版加装包（没有退出按钮），直接重新跑 `install.sh` 即可增量升级——脚本会补上退出按钮、退出会话同步和相关文案/样式，不会重复插入已有代码。

只注入、暂不构建（比如你想自己跑构建）：

```bash
bash install.sh --client-id nk_xxx --redirect-uri https://你的域名/auth/callback.html --no-build
```

先试运行看看会改哪些文件（不写任何文件、不构建，适合第一次在陌生 Piik 版本上评估）：

```bash
bash install.sh --client-id nk_xxx --redirect-uri https://你的域名/auth/callback.html --dry-run
```

> **二进制自动备份**：检测到 Go 项目并编译成功后，脚本会自动把现有的 `piik-server` 备份为 `piik-server.bak-<时间戳>`，替换失败时直接把备份文件改回原名即可回滚。不想要这个行为可加 `--no-backup-binary`。

---

## 第三步：替换二进制并重启

Piik 的前端资源通过 `go:embed` 打进二进制，**只跑 `npm run build` 是不生效的**。`install.sh` 会自动编译出 `piik-server.new`，然后按下面步骤替换（必须先停服，否则报 `Text file busy`）：

```bash
systemctl stop piik
cp -f /path/to/deploy/piik-server /path/to/deploy/piik-server.bak-$(date +%Y%m%d)
cp -f /path/to/your/Piik/piik-server.new /path/to/deploy/piik-server
chmod 755 /path/to/deploy/piik-server
systemctl start piik
```

Docker 部署：`docker cp piik-server.new <容器名>:/app/piik-server && docker restart <容器名>`

没有自动编译出来时手动来一次：

```bash
CGO_ENABLED=0 go build -trimpath -o piik-server.new ./cmd/piik-server
```

打开站点首页，右上角应出现「登录」按钮。点它 → 跳转到账号中心 → 登录/注册后跳回 → 顶部显示昵称与头像。

> 完整的部署步骤、验收清单和排错表见 **GUIDE.md**。

---

## 回滚

```bash
cd /path/to/your/Piik
bash /path/to/piik-ntk-login/rollback.sh
npm run build
CGO_ENABLED=0 go build -trimpath -o piik-server.new ./cmd/piik-server
# 停服 → 用 piik-server.new 替换二进制 → 启服
```

会从最近的 `.natsuko-backup/<时间戳>/` 还原被改的文件，并移除注入的 `account.ts` 与 `callback.html`。

---

## 常见问题

**Q：注入时报「锚点未找到」怎么办？**
说明你的 Piik 版本与加装包基线差异较大，脚本已自动回滚、没有破坏文件。把报错信息反馈给 NTK，或按 `template/` 下的文件手动合入。

**Q：点登录后跳回站点没显示头像？**
- 确认回调地址与应用登记完全一致（含 `https://` 和末尾 `/auth/callback.html`）。
- 确认 Piik 服务重启后加载的是新构建产物（构建产物在 `internal/server/webassets/dist/`）。
- 浏览器 F12 看 `callback.html?code=...` 是否有 CORS 或 token 报错。

**Q：更新了 Piik 版本，登录功能还在吗？**
升级前先 `rollback.sh` 还原；升级完成后重新跑一次 `install.sh`。重复安装是幂等的，不会重复插入代码。

**Q：需要 client_secret 吗？**
不需要。Piik 是浏览器应用，用公开客户端 + PKCE，平台会给 Piik 模板应用自动设为 `client_type=public`。

**Q：点「退出」后会发生什么？**
清除 Piik 本地头像/昵称登录态 → 跳转账号中心结束会话（`end_session`，带 id_token_hint）→ 自动跳回你的 Piik 站点首页。

**Q：我在账号中心登出了，Piik 顶部还显示头像？**
Piik 在页面加载、切回标签页时以及每 30 秒会探测一次账号中心会话。账号中心通过 `nk_seen` 标记区分「从未登录」与「已登出」：已登出会返回明确状态让 Piik 自动清除本地态；若你是跨站部署且浏览器禁用了第三方 Cookie，探测可能拿不到标记，此时手动点「退出」即可。

**Q：想让访客点功能时才提示登录 / 允许用户自己改名？**
安装时加 `--require-login` 开启登录守卫（访客正常浏览，点功能才在右上角提示登录，点提示才跳转）；加 `--no-lock-name` 允许登录后自行改名。两者默认分别是「纯可选登录」「锁定昵称为账号昵称」。已安装的站点重新跑一次 `install.sh` 带新参数即可切换。`--dry-run` 可以在不落盘的前提下预演整个注入过程。

---

## 文件清单

```
piik-ntk-login/
├── GUIDE.md                  完整使用说明（部署 + 验收 + 排错）
├── README.md                 本文档（速查）
├── install.sh                一键安装（注入 + 构建 + 编译）
├── inject.py                 注入器（幂等，支持回滚）
├── rollback.sh               回滚脚本
└── template/                 注入模板
    ├── src/client/lib/account.ts        OIDC 客户端（PKCE）
    └── public/auth/callback.html        静态回调页
```

---

## 说明

- 本加装包只**新增**前端文件并在固定锚点插入少量代码，不改动 Piik 的 Go 后端逻辑；`rollback.sh` 可完整还原。
- 注入基于 Piik 前端现有结构（`Header.tsx`、`main.tsx`、`locales/*`）。若上游大幅重构导致锚点不存在，注入器会明确报错并停止，不会写入半成品。
- 默认对接的账号平台为 [account.natsuko.online](https://account.natsuko.online)。如使用其他兼容 OIDC 的账号中心，用 `--origin` 指定。

## License

[MIT](LICENSE)
