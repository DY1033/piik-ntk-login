#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NTK 登录加装包 · 注入器
在已安装的 Piik 源码目录里，幂等地注入账号登录代码。

用法：
  python3 inject.py --root /path/to/Piik --client-id nk_xxx \
      --redirect-uri https://your.domain/auth/callback.html [--origin https://account.natsuko.online]

行为：
  - 先备份会被修改的 6 个文件到 .natsuko-backup/
  - account.ts / callback.html 整文件写入（用你的 client_id / redirect_uri 渲染）
  - Header.tsx / locales / styles.css 用锚点插入片段（保留对方版本其它内容）
  - 已注入过会跳过（幂等）；锚点找不到会报错并自动回滚，不破坏原文件
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

MARK = "// NATSUKO_OIDC_ADDON"

HEADER_IMPORT_OLD = 'import { useId, useLayoutEffect, useRef, useState, useSyncExternalStore, type ComponentProps } from "react";'
HEADER_IMPORT_NEW = 'import { useId, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type ComponentProps } from "react";'
HEADER_ACCOUNT_IMPORT = 'import { getAccount, login, logout, subscribeAccount } from "../../lib/account";'

ACCOUNT_BUTTON = '''
/** Optional NTK account sign-in. Shows avatar + name when signed in. */
function AccountButton() {
  const { t } = useCopy();
  const [account, setAccount] = useState(getAccount());
  useEffect(() => subscribeAccount(() => setAccount(getAccount())), []);
  if (!account) {
    return (
      <button type="button" className="lr-btn is-compact nk-account-btn nk-account-guest"
        title={t("account.signIn")} onClick={() => void login()}>
        <span className="nk-account-dot" aria-hidden="true">N</span>
        <span className="lr-cap">{t("account.signIn.short")}</span>
      </button>
    );
  }
  return (
    <span className="nk-account-group">
      <a className="lr-btn is-compact nk-account-btn nk-account-user"
        href="https://account.natsuko.online/profile" target="_blank" rel="noopener noreferrer"
        title={(account.name || account.sub) + " · " + t("account.manage")}>
        {account.picture
          ? <img className="nk-account-avatar" src={account.picture} alt="" referrerPolicy="no-referrer" />
          : <span className="nk-account-dot" aria-hidden="true">{(account.name || "N").slice(0, 1).toUpperCase()}</span>}
        <span className="lr-cap nk-account-name">{account.name || account.sub}</span>
      </a>
      <button type="button" className="lr-btn is-compact nk-account-btn nk-account-signout"
        title={t("account.signOut")} onClick={() => logout()}>
        <span className="nk-account-signout-icon" aria-hidden="true">↗</span>
        <span className="lr-cap">{t("account.signOut.short")}</span>
      </button>
    </span>
  );
}
'''

HEADER_SETTINGS_OLD = '<div className="lr-header-settings">\n          <LanguageControl />'
HEADER_SETTINGS_NEW = '<div className="lr-header-settings">\n          <AccountButton />\n          <LanguageControl />'

# 老版本加装包注入的「登录态」按钮块（无退出按钮），用于增量升级。
OLD_USER_RETURN = '''  return (
    <a className="lr-btn is-compact nk-account-btn nk-account-user"
      href="https://account.natsuko.online/profile" target="_blank" rel="noopener noreferrer"
      title={(account.name || account.sub) + " · " + t("account.manage")}>
      {account.picture
        ? <img className="nk-account-avatar" src={account.picture} alt="" referrerPolicy="no-referrer" />
        : <span className="nk-account-dot" aria-hidden="true">{(account.name || "N").slice(0, 1).toUpperCase()}</span>}
      <span className="lr-cap nk-account-name">{account.name || account.sub}</span>
    </a>
  );'''
NEW_USER_RETURN = '''  return (
    <span className="nk-account-group">
      <a className="lr-btn is-compact nk-account-btn nk-account-user"
        href="https://account.natsuko.online/profile" target="_blank" rel="noopener noreferrer"
        title={(account.name || account.sub) + " · " + t("account.manage")}>
        {account.picture
          ? <img className="nk-account-avatar" src={account.picture} alt="" referrerPolicy="no-referrer" />
          : <span className="nk-account-dot" aria-hidden="true">{(account.name || "N").slice(0, 1).toUpperCase()}</span>}
        <span className="lr-cap nk-account-name">{account.name || account.sub}</span>
      </a>
      <button type="button" className="lr-btn is-compact nk-account-btn nk-account-signout"
        title={t("account.signOut")} onClick={() => logout()}>
        <span className="nk-account-signout-icon" aria-hidden="true">↗</span>
        <span className="lr-cap">{t("account.signOut.short")}</span>
      </button>
    </span>
  );'''

ZH_LINES = '''  "account.signIn": "使用 NTK 账号登录",
  "account.signIn.short": "登录",
  "account.manage": "管理我的账户",
  "account.signOut": "退出 NTK 账号",
  "account.signOut.short": "退出",
'''
EN_LINES = '''  "account.signIn": "Sign in with NTK",
  "account.signIn.short": "Sign in",
  "account.manage": "Manage my account",
  "account.signOut": "Sign out of NTK",
  "account.signOut.short": "Sign out",
'''
MAIN_IMPORT_OLD = 'import "./styles.css";'
MAIN_IMPORT_NEW = 'import "./styles.css";\nimport { initAccount } from "./lib/account";'
MAIN_CALL_ANCHOR = 'async function main() {'
MAIN_CALL_ADD = '  // NTK account init: restore state, install the login gate, sync session.\n  void initAccount();\n'

CSS_BLOCK = '''
/* NTK account sign-in button (optional OIDC) */
.nk-account-btn{display:inline-flex;align-items:center;gap:6px;cursor:pointer;text-decoration:none}
.nk-account-dot{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#5ef2a0;color:#08120c;font-size:12px;font-weight:800;line-height:1;flex:none}
.nk-account-avatar{width:22px;height:22px;border-radius:50%;object-fit:cover;border:1px solid var(--line-hi,#3a4a40);flex:none}
.nk-account-name{max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nk-account-user{border-color:rgba(94,242,160,.45)}
'''

BACKUP_FILES = [
    "src/client/main.tsx",
    "src/client/components/living/Header.tsx",
    "src/client/locales/zh.ts",
    "src/client/locales/en.ts",
    "src/client/styles.css",
]


def fail(msg):
    print("[ERROR] " + msg, file=sys.stderr)
    sys.exit(1)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def insert_after_once(text, anchor, addition, label):
    if addition.strip() and addition.strip() in text:
        return text, True  # already injected
    if anchor not in text:
        fail("锚点未找到：" + label + "。Piik 版本可能不同，未做改动。")
    return text.replace(anchor, anchor + "\n" + addition, 1), False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Piik 源码根目录")
    ap.add_argument("--client-id", required=True, help="开放平台审核通过后拿到的 client_id")
    ap.add_argument("--redirect-uri", required=True, help="回调地址，如 https://piik.example.com/auth/callback.html")
    ap.add_argument("--origin", default="https://account.natsuko.online", help="账号中心域名")
    ap.add_argument("--require-login", choices=["true", "false"], default="false",
                    help="true=登录守卫：访客可正常浏览，点站内功能才在右上角提示登录（默认 false，纯可选登录）")
    ap.add_argument("--lock-name", choices=["true", "false"], default="true",
                    help="登录后是否把房间昵称锁定为账号昵称（默认 true）")
    ap.add_argument("--template-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "template"),
                    help="加装包模板目录")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    tpl = os.path.abspath(args.template_dir)
    if not os.path.isfile(os.path.join(root, "package.json")):
        fail("根目录找不到 package.json，确认这是 Piik 源码目录：" + root)
    for sub in ("src/client/lib", "public", "src/client/components/living", "src/client/locales"):
        if not os.path.isdir(os.path.join(root, sub)):
            fail("目录结构不符，缺少 " + sub)

    client_id, redirect_uri, origin = args.client_id.strip(), args.redirect_uri.strip(), args.origin.strip().rstrip("/")
    if not client_id.startswith("nk_"):
        fail("client_id 格式不对，应以 nk_ 开头")
    if not redirect_uri.startswith("https://") or not redirect_uri.endswith("/auth/callback.html"):
        fail("redirect_uri 应为 https://你的域名/auth/callback.html")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(root, ".natsuko-backup", stamp)
    os.makedirs(backup_dir, exist_ok=True)
    print("[1/6] 备份原文件到 " + backup_dir)
    for rel in BACKUP_FILES:
        src = os.path.join(root, rel)
        if os.path.isfile(src):
            dst = os.path.join(backup_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    try:
        print("[2/6] 写入 account.ts 与回调页")
        for rel in ("src/client/lib/account.ts", "public/auth/callback.html"):
            content = read(os.path.join(tpl, rel))
            content = (content.replace("__NATSUKO_CLIENT_ID__", client_id)
                              .replace("__NATSUKO_REDIRECT_URI__", redirect_uri)
                              .replace("__NATSUKO_REQUIRE_LOGIN__", args.require_login)
                              .replace("__NATSUKO_LOCK_NAME__", args.lock_name)
                              .replace("https://account.natsuko.online", origin))
            write(os.path.join(root, rel), content)

        print("[3/6] 注入 main.tsx（初始化账号模块）")
        mp = os.path.join(root, "src/client/main.tsx")
        m = read(mp)
        if "initAccount" not in m:
            if MAIN_IMPORT_OLD not in m or MAIN_CALL_ANCHOR not in m:
                fail("main.tsx 的注入锚点未找到，未做改动。")
            m = m.replace(MAIN_IMPORT_OLD, MAIN_IMPORT_NEW, 1)
            m = m.replace(MAIN_CALL_ANCHOR, MAIN_CALL_ANCHOR + "\n" + MAIN_CALL_ADD.rstrip(), 1)
            write(mp, m)
        else:
            print("      已注入过，跳过")

        print("[4/6] 注入 Header.tsx")
        hp = os.path.join(root, "src/client/components/living/Header.tsx")
        h = read(hp)
        if MARK not in h:
            # 全新注入
            if HEADER_IMPORT_OLD in h:
                h = h.replace(HEADER_IMPORT_OLD, HEADER_IMPORT_NEW, 1)
            elif "useEffect" not in h.split("\n")[1]:
                fail("Header.tsx 的 React import 锚点未找到，未做改动。")
            if HEADER_ACCOUNT_IMPORT not in h:
                if 'import { Btn } from "./primitives";' not in h:
                    fail("Header.tsx 的 Btn import 锚点未找到，未做改动。")
                h = h.replace('import { Btn } from "./primitives";',
                              'import { Btn } from "./primitives";\n' + HEADER_ACCOUNT_IMPORT, 1)
            if "export function HeaderControls(" not in h:
                fail("Header.tsx 的 HeaderControls 锚点未找到，未做改动。")
            h = h.replace("export function HeaderControls(",
                          MARK + "\n" + ACCOUNT_BUTTON.strip() + "\n\nexport function HeaderControls(", 1)
            if HEADER_SETTINGS_OLD not in h:
                fail("Header.tsx 的 header-settings 锚点未找到，未做改动。")
            h = h.replace(HEADER_SETTINGS_OLD, HEADER_SETTINGS_NEW, 1)
            write(hp, h)
        elif "nk-account-signout" not in h and OLD_USER_RETURN in h:
            # 增量升级：老版本加装包有 MARK 但没有退出按钮 —— 替换登录态按钮块
            h = h.replace(OLD_USER_RETURN, NEW_USER_RETURN, 1)
            write(hp, h)
            print("      老版本升级：已补充退出按钮")
        else:
            print("      已注入过（含退出按钮），跳过")

        print("[5/6] 注入本地化文案")
        # 支持老版本加装包的增量升级：旧文案已存在但缺 signOut 时，只补缺失的键。
        for path, anchor, lines in (
            (os.path.join(root, "src/client/locales/zh.ts"), "export const zh = {", ZH_LINES),
            (os.path.join(root, "src/client/locales/en.ts"), "export const en: Record<CopyKey, string> = {", EN_LINES),
        ):
            txt = read(path)
            add = ""
            for line in lines.splitlines():
                if line.strip() and ("\"" + line.strip().split("\"")[1] + "\"") not in txt:
                    add += line + "\n"
            if add.strip():
                txt = txt.replace(anchor, anchor + "\n" + add.rstrip(), 1)
                write(path, txt)

        print("[6/6] 注入样式")
        cp = os.path.join(root, "src/client/styles.css")
        css = read(cp)
        add_css = ""
        if "nk-account-btn" not in css:
            add_css += CSS_BLOCK.strip()
        # 老版本缺退出按钮样式时增量补齐
        if "nk-account-signout" not in css:
            add_css += "\n" + "\n".join([
                ".nk-account-group{display:inline-flex;align-items:center;gap:4px}",
                ".nk-account-signout{opacity:.72}",
                ".nk-account-signout:hover{opacity:1;border-color:rgba(94,242,160,.45)}",
                ".nk-account-signout-icon{font-size:13px;line-height:1;transform:rotate(45deg)}",
            ])
        if add_css.strip():
            sink = "/* append-sink:"
            if sink in css:
                css = css.replace(sink, add_css.strip() + "\n\n" + sink, 1)
            else:
                css = css.rstrip() + "\n\n" + add_css.strip()
            write(cp, css)

        print("\n[DONE] 注入完成。client_id=%s redirect_uri=%s" % (client_id, redirect_uri))
        print("      下一步：npm run build，然后重启 Piik 服务。")
        print("      如需回滚：cp -a %s/. .  （从备份目录还原）" % backup_dir)
    except SystemExit:
        # 出错时还原已备份文件
        print("[ROLLBACK] 还原原文件…", file=sys.stderr)
        for rel in BACKUP_FILES:
            b = os.path.join(backup_dir, rel)
            if os.path.isfile(b):
                shutil.copy2(b, os.path.join(root, rel))
        raise
    except Exception as e:
        print("[ROLLBACK] 出错，还原原文件：%s" % e, file=sys.stderr)
        for rel in BACKUP_FILES:
            b = os.path.join(backup_dir, rel)
            if os.path.isfile(b):
                shutil.copy2(b, os.path.join(root, rel))
        sys.exit(1)


if __name__ == "__main__":
    main()
