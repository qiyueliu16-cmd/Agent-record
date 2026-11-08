#!/usr/bin/env python3
"""把 skill/ 安装到 WorkBuddy 用户级 skills 目录（幂等、可指定目标）。

    python3 scripts/install_skill.py                    # 安装到 ~/.workbuddy/skills/agent-execution-log
    python3 scripts/install_skill.py --target /path    # 安装到自定义目录
    python3 scripts/install_skill.py --print-path      # 只打印默认安装路径

不依赖任何第三方包；若目标已存在，默认先备份再覆盖，不会静默丢弃已有文件。
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SOURCE = HERE / "skill"
DEFAULT_TARGET = Path.home() / ".workbuddy" / "skills" / "agent-execution-log"


def main() -> int:
    parser = argparse.ArgumentParser(description="安装 Agent执行记录 skill")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="目标目录")
    parser.add_argument("--force", action="store_true", help="目标已存在时直接覆盖，不备份")
    parser.add_argument("--print-path", action="store_true", help="只打印默认安装路径")
    args = parser.parse_args()

    if args.print_path:
        print(DEFAULT_TARGET)
        return 0

    target = Path(args.target).expanduser()
    if not SOURCE.is_dir():
        print(json.dumps({"ok": False, "error": f"找不到 skill 源目录：{SOURCE}"}, ensure_ascii=False))
        return 1

    backup = None
    if target.exists():
        if args.force:
            shutil.rmtree(target)
        else:
            backup = target.with_name(target.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.move(str(target), str(backup))

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, target)
    copied = sorted(str(p.relative_to(target)) for p in target.rglob("*") if p.is_file())
    result = {"ok": True, "target": str(target), "files": copied, "backup": str(backup) if backup else None}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n安装完成。在 Agent 会话中显式点名 agent-execution-log 或说「记一笔」，即可由 Agent 自动写入账本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
