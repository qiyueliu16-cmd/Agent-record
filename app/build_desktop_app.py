#!/usr/bin/env python3
"""把「Agent执行记录」打成可双击的 macOS .app。

.app 是**自包含**的：仓库内容（app/、examples/、skill/、scripts/、docs/）会
复制进 Contents/Resources/repo/，启动脚本指向内部 launcher.py。因此下载者
之后即使删除或移动解压目录，双击 .app 仍然可用，与长期安装的体验一致。

图标由 assets/make_icon.py 用纯标准库现场生成，不需要 Pillow 或 iconutil。
核心功能（控制台 + 报告 + 账本）不依赖本脚本；非 macOS 平台直接运行
`python3 app/launcher.py` 即可。

    python3 app/build_desktop_app.py [--no-desktop-link]
"""
from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
APP_NAME = "Agent执行记录"
BUNDLE_ID = "local.agent.execution.log"
VERSION = "1.0.0"
EXECUTABLE = "agent-execution-log"
ICON_SRC = HERE / "assets" / "AppIcon.icns"
ICON_GEN = HERE / "assets" / "make_icon.py"
TARGET = Path.home() / "Applications" / f"{APP_NAME}.app"
DESKTOP_LINK = Path.home() / "Desktop" / f"{APP_NAME}.app"
COPIED_DIRS = ("app", "examples", "skill", "scripts", "docs")
COPIED_FILES = ("README.md", "Makefile", ".gitignore")


def pick_python() -> Path:
    """优先用当前解释器，其次系统 python3；不假设任何私有路径。"""
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
    """已有图标直接用；否则用纯标准库脚本现场生成（不会引入第三方依赖）。"""
    if ICON_SRC.is_file():
        return ICON_SRC
    if ICON_GEN.is_file():
        proc = subprocess.run([sys.executable, str(ICON_GEN)],
                              capture_output=True, text=True, check=False, timeout=180)
        if proc.returncode == 0 and ICON_SRC.is_file():
            print(f"  图标: 已现场生成（{proc.stdout.strip()}）")
            return ICON_SRC
        print(f"  图标: 生成失败，跳过（不影响功能）: {proc.stderr.strip()[:120]}")
    return None


def is_arm64() -> bool:
    if sys.platform != "darwin":
        return False
    return subprocess.run(
        ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"],
        capture_output=True, text=True, check=False,
    ).stdout.strip() == "1"


def copy_repo(dst: Path) -> None:
    """把仓库内容复制进 .app，排除运行时状态与缓存；已存在的状态文件保留。"""
    dst.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(
        "__pycache__", "*.py[cod]", ".DS_Store", "logs", "*.icns", "AppIcon.png",
        "AppIcon.iconset", "Agent执行记录_报告", ".git", "*.tmp",
    )
    for name in COPIED_DIRS:
        src = REPO / name
        if src.is_dir():
            shutil.copytree(src, dst / name, ignore=ignore, dirs_exist_ok=True)
    for name in COPIED_FILES:
        src = REPO / name
        if src.is_file():
            shutil.copy2(src, dst / name)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 macOS 自包含桌面应用")
    parser.add_argument("--no-desktop-link", action="store_true", help="不在桌面创建快捷方式")
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("桌面 .app 仅支持 macOS。当前平台请直接运行：python3 app/launcher.py")
        return 0

    python = pick_python()
    for path, label in ((HERE / "launcher.py", "launcher.py"), (HERE / "server.py", "server.py"),
                        (HERE / "report.py", "report.py"), (HERE / "web" / "index.html", "index.html")):
        if not path.is_file():
            raise SystemExit(f"缺少 {label}: {path}")
    icon = optional_icon()

    # 已有的同名 .app 如果不是本脚本生成的，先备份，避免静默覆盖用户原有应用
    if TARGET.exists() and not (TARGET / "Contents/Resources/repo/app/launcher.py").is_file():
        backup = TARGET.with_name(TARGET.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.move(str(TARGET), str(backup))
        print(f"检测到已有的同名应用，已备份为 {backup}")

    contents = TARGET / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(parents=True, exist_ok=True)
    bundle_repo = contents / "Resources" / "repo"
    copy_repo(bundle_repo)
    bundle_launcher = bundle_repo / "app" / "launcher.py"

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
        f"# {APP_NAME} —— 双击入口。自包含，逻辑在 Resources/repo/app/launcher.py。\n"
        f'cd "{bundle_launcher.parent}"\n'
        f'exec {prefix}"{python}" "{bundle_launcher}" "$@"\n'
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
    if not args.no_desktop_link and (Path.home() / "Desktop").is_dir():
        if DESKTOP_LINK.is_symlink() and DESKTOP_LINK.resolve() == TARGET.resolve():
            link_info = str(DESKTOP_LINK) + "（已存在）"
        elif not DESKTOP_LINK.exists():
            try:
                DESKTOP_LINK.symlink_to(TARGET)
                link_info = str(DESKTOP_LINK)
            except OSError as exc:
                link_info = f"创建失败（不影响 .app）：{exc}"
        else:
            link_info = "桌面已有同名项目，未覆盖"

    print(f"已生成 {TARGET}")
    print(f"  解释器: {python}")
    print(f"  图标: {icon or '未设置（可选，不影响功能）'}")
    print(f"  自包含: {bundle_repo}")
    print(f"  桌面快捷方式: {link_info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
