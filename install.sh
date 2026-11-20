#!/usr/bin/env bash
# NTK 登录 · Piik 加装包 一键安装
# 用法：在 Piik 源码目录里运行
#   bash install-natsuko-login.sh --client-id nk_xxx --redirect-uri https://你的域名/auth/callback.html
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(pwd)"
CLIENT_ID=""
REDIRECT_URI=""
ORIGIN="https://account.natsuko.online"
REQUIRE_LOGIN="false"
LOCK_NAME="true"
BUILD=1

usage() {
  cat <<'EOF'
用法：bash install-natsuko-login.sh [选项] --client-id <id> --redirect-uri <url>

必填：
  --client-id <id>       开放平台审核通过后拿到的 client_id（nk_ 开头）
  --redirect-uri <url>   回调地址，如 https://piik.example.com/auth/callback.html
选项：
  --origin <url>         账号中心域名，默认 https://account.natsuko.online
  --require-login        登录守卫：访客可正常浏览，点站内功能才在右上角弹登录提示，点提示才跳转（默认关闭，纯可选登录）
  --optional-login       纯可选登录：不弹任何登录提示（默认，等价不传 --require-login）
  --lock-name            登录后昵称锁定为账号昵称（默认开启）
  --no-lock-name         允许用户自行修改房间昵称
  --no-build             只注入代码，不执行 npm run build
  -h, --help             显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --client-id)   CLIENT_ID="${2:-}"; shift 2;;
    --redirect-uri) REDIRECT_URI="${2:-}"; shift 2;;
    --origin)      ORIGIN="${2:-}"; shift 2;;
    --require-login) REQUIRE_LOGIN="true"; shift;;
    --optional-login) REQUIRE_LOGIN="false"; shift;;
    --no-lock-name)  LOCK_NAME="false"; shift;;
    --lock-name)     LOCK_NAME="true"; shift;;
    --no-build)    BUILD=0; shift;;
    -h|--help)     usage; exit 0;;
    *) echo "未知参数: $1" >&2; usage; exit 1;;
  esac
done

if [[ -z "$CLIENT_ID" || -z "$REDIRECT_URI" ]]; then
  echo "错误：必须提供 --client-id 和 --redirect-uri" >&2
  usage
  exit 1
fi

if [[ ! -f "$ROOT/package.json" ]]; then
  echo "错误：当前目录不是 Piik 源码根目录（找不到 package.json）" >&2
  exit 1
fi

echo "==> NTK 登录加装包"
echo "    源码目录 : $ROOT"
echo "    client_id: $CLIENT_ID"
echo "    回调地址 : $REDIRECT_URI"
echo "    账号中心 : $ORIGIN"
echo "    登录守卫 : $REQUIRE_LOGIN  (true=点功能才提示登录；false=纯可选登录)"
echo "    锁定昵称 : $LOCK_NAME"
echo

python3 "$HERE/inject.py" \
  --root "$ROOT" \
  --client-id "$CLIENT_ID" \
  --redirect-uri "$REDIRECT_URI" \
  --origin "$ORIGIN" \
  --require-login "$REQUIRE_LOGIN" \
  --lock-name "$LOCK_NAME" \
  --template-dir "$HERE/template"

if [[ "$BUILD" -eq 1 ]]; then
  echo
  echo "==> 重新构建前端…"
  npm run build
  echo "==> 前端构建完成。"

  # Piik 的前端产物通过 go:embed 打进二进制，只 build 前端不重新编译是不生效的。
  if [[ -f "$ROOT/go.mod" ]]; then
    if command -v go >/dev/null 2>&1; then
      PKG="./cmd/piik-server"
      [[ -d "$ROOT/cmd/piik-server" ]] || PKG="$(ls -d ./cmd/*/ 2>/dev/null | head -1)"
      if [[ -n "$PKG" ]]; then
        echo "==> 检测到 Go 项目，正在重新编译二进制（$PKG）…"
        if CGO_ENABLED=0 GOTOOLCHAIN=auto go build -trimpath -o piik-server.new "$PKG"; then
          echo "    已生成 ./piik-server.new"
          echo "    生效步骤：停止服务 → 用 piik-server.new 替换正在运行的二进制 → 启动服务"
        else
          echo "    ! Go 编译失败。前端产物已更新到 internal/server/webassets/dist/，请手动编译。"
        fi
      else
        echo "    ! 找不到 cmd 入口目录，请自行编译二进制。"
      fi
    else
      echo "    ! 未检测到 go 命令。Piik 的前端资源是打进二进制的，请自行编译后再重启。"
    fi
  fi

  echo "==> 请重启 Piik 服务使新二进制生效。"
  echo "    systemd:  systemctl restart <你的 piik 服务名>"
  echo "    docker :  docker restart <你的容器名>"
else
  echo
  echo "==> 已跳过构建（--no-build），记得手动 npm run build、重新编译二进制并重启服务。"
fi

echo
echo "完成。打开站点首页，右上角应出现「登录 / Sign in with NTK」按钮。"
