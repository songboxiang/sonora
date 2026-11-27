#!/usr/bin/env bash
# Sonora v2 — release 打包脚本
# 流程：analyze/test → release build → 核心校验 → adhoc 签名 → 去 quarantine →
#       staging 改名 Sonora.app → zip + dmg + SHA256SUMS
# 用法：bash tool/package.sh [--no-build]
#   --no-build  跳过 analyze/test/build，仅对现有 Release 产物重新签名归档（调试用）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH=/opt/homebrew/bin:$PATH

SKIP_BUILD=0
for a in "$@"; do [ "$a" = "--no-build" ] && SKIP_BUILD=1; done

VERSION="$(python3 -c 'import re,pathlib; m=re.search(r"^version:\s*([0-9.]+)\+(\d+)", pathlib.Path("pubspec.yaml").read_text(), re.M); print(m.group(1))')"
BUILD_NUM="$(python3 -c 'import re,pathlib; m=re.search(r"^version:\s*([0-9.]+)\+(\d+)", pathlib.Path("pubspec.yaml").read_text(), re.M); print(m.group(2))')"
APP_IN="build/macos/Build/Products/Release/sonora.app"
DIST="$ROOT/dist"
STAGE="$DIST/stage"
APP_OUT="$STAGE/Sonora.app"

step() { echo; echo "=== $1 ==="; }
fail() { echo "FAILED: $1" >&2; exit 1; }

if [ "$SKIP_BUILD" -eq 0 ]; then
  step "1/7 flutter analyze / test / release build"
  flutter analyze || fail "analyze"
  flutter test || fail "test"
  flutter build macos --release || fail "release build"
else
  step "1/7 跳过构建（--no-build）"
fi

[ -d "$APP_IN" ] || fail "找不到 Release 产物：$APP_IN"
CORE_IN="$APP_IN/Contents/Resources/Core/squeezelite"
MANIFEST_IN="$APP_IN/Contents/Resources/Core/core-manifest.json"
[ -x "$CORE_IN" ] || fail "内置核心不存在或不可执行：$CORE_IN"

step "2/7 校验内置核心 sha256 / 自报版本"
ACTUAL="$(shasum -a 256 "$CORE_IN" | awk '{print $1}')"
EXPECT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["binarySha256"])' "$MANIFEST_IN")"
echo "actual=$ACTUAL"
echo "expect=$EXPECT"
[ "$ACTUAL" = "$EXPECT" ] || fail "核心 sha256 不匹配"
CORE_VER="$("$CORE_IN" -t 2>&1 | head -3 | tr '\n' ' ')"
echo "core -t: $CORE_VER"

step "3/7 staging 改名 Sonora.app"
rm -rf "$DIST"
mkdir -p "$STAGE"
cp -R "$APP_IN" "$APP_OUT"
CORE_OUT="$APP_OUT/Contents/Resources/Core/squeezelite"
MANIFEST_OUT="$APP_OUT/Contents/Resources/Core/core-manifest.json"
chmod 755 "$CORE_OUT"

step "4/7 去 quarantine（签名前）"
xattr -dr com.apple.quarantine "$APP_OUT" 2>/dev/null || true

step "5/7 adhoc 签名：核心 → 更新 manifest → 框架 → 整包"
codesign --force --sign - "$CORE_OUT" || fail "签核心失败"
# 签名会改变 Mach-O 的 hash：签名后重算 sha256/size 并写回 staging 的 manifest，
# 使 manifest 与实际分发的核心一致。注意顺序：必须在签整包之前完成，
# 因为 manifest 本身也在 bundle 内，改完再由 --deep 一并纳入签名封印。
SIGNED_SHA="$(shasum -a 256 "$CORE_OUT" | awk '{print $1}')"
SIGNED_SIZE="$(stat -f%z "$CORE_OUT")"
python3 - "$MANIFEST_OUT" "$SIGNED_SHA" "$SIGNED_SIZE" <<'PY'
import json, sys
path, sha, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(path) as f:
    m = json.load(f)
m["binarySha256"] = sha
m["binarySize"] = size
m["signedAfterAdhoc"] = True
with open(path, "w") as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"manifest 已更新为签名后 hash: {sha} ({size} bytes)")
PY
# --deep 会签 Frameworks / MacOS 等嵌套代码；Resources/Core 下的裸二进制已单独签
codesign --force --deep --sign - \
  --entitlements macos/Runner/Release.entitlements \
  "$APP_OUT" || fail "签 app 失败"

step "6/7 验证签名与版本"
codesign --verify --deep --strict "$APP_OUT" || fail "签名验证失败"
FINAL_SHA="$(shasum -a 256 "$CORE_OUT" | awk '{print $1}')"
MANIFEST_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["binarySha256"])' "$MANIFEST_OUT")"
echo "core final sha=$FINAL_SHA"
echo "manifest sha   =$MANIFEST_SHA"
[ "$FINAL_SHA" = "$MANIFEST_SHA" ] || fail "签名后 manifest hash 与实际核心不一致"
echo "--- app signature ---"
codesign -dvv "$APP_OUT" 2>&1 | grep -E "Identifier=|TeamIdentifier=|Signature=|Runtime Version|Flags=" || true
echo "--- core signature ---"
codesign -dvv "$CORE_OUT" 2>&1 | grep -E "Identifier=|TeamIdentifier=|Signature=" || true
echo "--- app entitlements ---"
codesign -d --entitlements - "$APP_OUT" 2>/dev/null | grep -E "app-sandbox|network.client|network.server" || true
BUNDLE_VER="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP_OUT/Contents/Info.plist")"
BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP_OUT/Contents/Info.plist")"
echo "version=$BUNDLE_VER build=$BUILD_NUM bundle=$BUNDLE_ID"
[ "$BUNDLE_VER" = "$VERSION" ] || fail "版本号不一致：$BUNDLE_VER != $VERSION"

step "7/7 生成归档 zip + dmg + SHA256SUMS"
ZIP="$DIST/Sonora-$VERSION.zip"
DMG="$DIST/Sonora-$VERSION.dmg"
ditto -c -k --keepParent "$APP_OUT" "$ZIP" || fail "zip 失败"
hdiutil create -volname "Sonora $VERSION" -srcfolder "$APP_OUT" -ov -format UDZO "$DMG" >/dev/null || fail "dmg 失败"
xattr -d com.apple.quarantine "$ZIP" "$DMG" 2>/dev/null || true
( cd "$DIST" && shasum -a 256 "Sonora-$VERSION.zip" "Sonora-$VERSION.dmg" > SHA256SUMS )
cat "$DIST/SHA256SUMS"

echo
echo "PACKAGING OK"
echo "app:  $APP_OUT"
echo "zip:  $ZIP"
echo "dmg:  $DMG"
echo "sums: $DIST/SHA256SUMS"
