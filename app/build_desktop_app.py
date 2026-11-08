#!/usr/bin/env python3
"""把「Agent执行记录」打成 macOS .app（可选增强，非必需）。

.app 只是一层壳：Contents/MacOS 里的脚本 exec 到本机 Python，真正逻辑在 launcher.py。
核心功能（控制台 + 报告 + 账本）不依赖本脚本，也不依赖任何第三方包。
非 macOS 平台会给出提示并正常退出，直接用 `python3 app/launcher.py` 即可。

    python3 app/build_desktop_app.py [--no-desktop-link]
"""
from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_NAME = "Agent执行记录"
BUNDLE_ID = "local.agent.execution.log"
VERSION = "1.0.0"
EXECUTABLE = "agent-execution-log"
LAUNCHER = HERE / "launcher.py"
ICON_SRC = HERE / "assets" / "AppIcon.icns"
TARGET = Path.home() / "Applications" / f"{APP_NAME}.app"
DESKTOP_LINK = Path.home() / "Desktop" / f"{APP_NAME}.app"


def pick_python() -> Path:
    """优先用当前解释器，其次用系统 python3；不假设任何私有路径。"""
    candidates = [Path(sys.executable)]
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    candidates.append(Path("/usr/bin/python3"))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        probe = subprocess.run(
            [key, "-c", "import sys; print(sys.version_info >= (3, 9))"],
            capture_output=True, text=True, check=False, timeout=20,
        )
        if probe.returncode == 0 and probe.stdout.strip() == "True":
            return candidate
    raise SystemExit("找不到可用的 Python 3.9+ 解释器")


def optional_icon() -> Path | None:
    """图标是可选的：没有 Pillow 也能生成可用的 .app。"""
    return ICON_SRC if ICON_SRC.is_file() else None


def is_arm64() -> bool:
    if sys.platform != "darwin":
        return False
    return subprocess.run(
        ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"],
        capture_output=True, text=True, check=False,
    ).stdout.strip() == "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 macOS 桌面应用壳")
    parser.add_argument("--no-desktop-link", action="store_true", help="不在桌面创建快捷方式")
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("桌面 .app 仅支持 macOS。当前平台请直接运行：python3 app/launcher.py")
        return 0

    python = pick_python()
    for path, label in ((LAUNCHER, "launcher.py"), (HERE / "server.py", "server.py"),
                        (HERE / "report.py", "report.py"), (HERE / "web" / "index.html", "index.html")):
        if not path.is_file():
            raise SystemExit(f"缺少 {label}: {path}")
    icon = optional_icon()

    if TARGET.exists():
        shutil.rmtree(TARGET)
    contents = TARGET / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir(parents=True)

    info = {
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleExecutable": EXECUTABLE,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": "1",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleDevelopmentRegion": "zh_CN",
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "LSUIElement": False,
        "NSSupportsAutomaticTermination": False,
        "NSSupportsSuddenTermination": False,
    }
    if icon:
        info["CFBundleIconFile"] = "AppIcon"
    with (contents / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)

    prefix = "/usr/bin/arch -arm64 " if is_arm64() else ""
    entry = contents / "MacOS" / EXECUTABLE
    entry.write_text(
        "#!/bin/sh\n"
        f"# {APP_NAME} —— 双击入口。真正逻辑在 launcher.py。\n"
        f'cd "{HERE}"\n'
        f'exec {prefix}"{python}" "{LAUNCHER}" "$@"\n'
    )
    entry.chmod(0o755)
    if icon:
        shutil.copy2(icon, contents / "Resources" / "AppIcon.icns")
    (contents / "PkgInfo").write_text("APPL????")

    sign = shutil.which("codesign") or "/usr/bin/codesign"
    if Path(sign).is_file():
        subprocess.run([sign, "--force", "--deep", "--sign", "-", str(TARGET)],
                       check=False, capture_output=True)

    link_info = "未创建"
    if not args.no_desktop_link and (Path.home() / "Desktop").is_dir() and not DESKTOP_LINK.exists():
        try:
            DESKTOP_LINK.symlink_to(TARGET)
            link_info = str(DESKTOP_LINK)
        except OSError as exc:
            link_info = f"创建失败（不影响 .app）：{exc}"

    print(f"已生成 {TARGET}")
    print(f"  解释器: {python}")
    print(f"  图标: {icon or '未设置（可选，不影响功能）'}")
    print(f"  桌面快捷方式: {link_info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
