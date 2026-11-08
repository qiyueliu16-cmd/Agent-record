#!/usr/bin/env python3
"""「Agent执行记录」账本追加器（opt-in，纯标准库）。

只在用户显式加载 agent-execution-log skill 并要求记录时调用。
直接读写项目目录内的 .agent-log/ledger.json，不依赖 58400 服务，
不连服务器，不执行分析代码，不替研究者拍板。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

LEDGER_DIR = ".agent-log"
LEDGER_NAME = "ledger.json"
APP_MARK = "agent-execution-log"
MAX_BACKUPS = 10


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id(prefix: str = "r") -> str:
    return f"{prefix}-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def short_id(prefix: str = "d") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def blank_ledger(root: Path) -> dict:
    return {
        "schema": 1,
        "app": APP_MARK,
        "project": {
            "name": root.name,
            "root": str(root),
            "server": {"alias": "", "root": "", "note": "大数据不落本地，此处只登记出处"},
        },
        "question": "这个课题要回答什么？",
        "updatedAt": now(),
        "records": [],
    }


def resolve_ledger(root_arg: str | None, ledger_arg: str | None, create: bool) -> Path:
    if ledger_arg:
        return Path(ledger_arg).expanduser().resolve()
    start = Path(root_arg).expanduser().resolve() if root_arg else Path.cwd().resolve()
    direct = start / LEDGER_DIR / LEDGER_NAME
    if direct.is_file():
        return direct
    for parent in [start, *start.parents]:
        candidate = parent / LEDGER_DIR / LEDGER_NAME
        if candidate.is_file():
            return candidate
    if create:
        return direct
    raise FileNotFoundError(
        f"未找到账本：{direct}。用 --root 指定项目目录，或加 --init 新建一份。"
    )


def load_ledger(path: Path, create: bool) -> dict:
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"账本格式不是 JSON 对象：{path}")
    elif create:
        data = blank_ledger(path.parent.parent)
    else:
        raise FileNotFoundError(path)
    data.setdefault("records", [])
    data.setdefault("project", {})
    return data


def backup(path: Path) -> str | None:
    if not path.is_file():
        return None
    folder = path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"ledger-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}.json"
    shutil.copy2(path, out)
    olds = sorted(folder.glob("ledger-*.json"), key=lambda p: p.stat().st_mtime)
    for old in olds[:-MAX_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return str(out)


def save_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger["app"] = APP_MARK
    ledger["schema"] = 1
    ledger.setdefault("project", {})["root"] = str(path.parent.parent)
    ledger["updatedAt"] = now()
    tmp = path.parent / (LEDGER_NAME + f".tmp-{uuid.uuid4().hex[:6]}")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def norm_decision(raw: dict) -> dict:
    d = dict(raw or {})
    d.setdefault("id", short_id())
    d.setdefault("question", "")
    options = []
    for i, item in enumerate(d.get("options") or []):
        o = dict(item or {})
        o.setdefault("key", chr(65 + i) if i < 26 else str(i + 1))
        o.setdefault("label", "")
        o.setdefault("why", "")
        options.append(o)
    d["options"] = options
    d.setdefault("recommend", "")
    d.setdefault("choice", "")
    d.setdefault("note", "")
    d["status"] = "decided" if d.get("choice") else "pending"
    return d


def norm_code(raw: dict) -> dict:
    c = dict(raw or {})
    return {
        "label": c.get("label", ""),
        "path": c.get("path", ""),
        "lang": c.get("lang", "R"),
        "content": "",  # 报告生成时现场读盘，账本不复制代码字节
    }


def norm_file(raw: dict) -> dict:
    f = dict(raw or {})
    return {
        "path": f.get("path", ""),
        "caption": f.get("caption", ""),
        "serverPath": f.get("serverPath", ""),
        "origin": f.get("origin", "local"),
    }


def norm_result(raw: dict) -> dict:
    r = dict(raw or {})
    metrics = []
    for m in r.get("metrics") or []:
        m = dict(m or {})
        metrics.append({
            "label": m.get("label", ""),
            "value": str(m.get("value", "")),
            "note": m.get("note", ""),
        })
    return {"headline": r.get("headline", ""), "body": r.get("body", ""), "metrics": metrics}


def norm_record(raw: dict, *, record_id: str | None = None, created_at: str | None = None) -> dict:
    r = dict(raw or {})
    stamp = now()
    return {
        "id": record_id or r.get("id") or new_id(),
        "title": r.get("title") or "未命名步骤",
        "status": r.get("status") or "done",
        "question": r.get("question", ""),
        "provenance": r.get("provenance", ""),
        "decisions": [norm_decision(d) for d in r.get("decisions") or []],
        "result": norm_result(r.get("result")),
        "technical": r.get("technical", ""),
        "code": [norm_code(c) for c in r.get("code") or []],
        "files": [norm_file(f) for f in r.get("files") or []],
        "createdAt": created_at or r.get("createdAt") or stamp,
        "updatedAt": stamp,
    }


def check_paths(root: Path, record: dict) -> list[str]:
    warnings: list[str] = []
    for kind in ("code", "files"):
        for item in record.get(kind, []):
            rel = str(item.get("path", ""))
            if not rel:
                warnings.append(f"{kind} 条目缺少 path，已保留为空")
                continue
            p = Path(rel)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(
                    f"路径必须是项目目录内的相对路径：{rel}（服务器路径请写进 serverPath）"
                )
            if not (root / p).exists():
                warnings.append(f"文件尚未同步到本地，仅登记路径：{rel}")
    return warnings


def load_payload(args: argparse.Namespace) -> dict:
    if args.payload_file == "-":
        text = sys.stdin.read()
    elif args.payload_file:
        text = Path(args.payload_file).expanduser().read_text(encoding="utf-8")
    elif args.payload:
        text = args.payload
    else:
        raise ValueError("需要 --payload-file / --payload，或用 --payload-file - 从 stdin 读入")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("payload 必须是 JSON 对象")
    return data


def find_record(ledger: dict, record_id: str) -> tuple[int, dict]:
    for i, rec in enumerate(ledger["records"]):
        if rec.get("id") == record_id:
            return i, rec
    raise KeyError(f"找不到记录锚点：{record_id}")


def merge_record(old: dict, payload: dict) -> dict:
    """顶层字段覆盖；decisions 按 id 合并，未提及的决策保持原样。"""
    merged = dict(old)
    incoming_decisions = payload.pop("decisions", None) if isinstance(payload, dict) else None
    payload = dict(payload)
    for key, value in payload.items():
        if key in ("id", "createdAt", "updatedAt"):
            continue
        merged[key] = value
    if incoming_decisions is not None:
        by_id = {d.get("id"): d for d in merged.get("decisions") or []}
        for d in incoming_decisions:
            did = d.get("id")
            if did and did in by_id:
                combined = dict(by_id[did])
                combined.update(d)
                by_id[did] = combined
            else:
                by_id[did or short_id()] = d
        merged["decisions"] = list(by_id.values())
    return norm_record(merged, record_id=old.get("id"), created_at=old.get("createdAt"))


def cmd_list(ledger: dict, path: Path, args) -> dict:
    rows = []
    for rec in ledger["records"]:
        rows.append({
            "id": rec.get("id"),
            "title": rec.get("title"),
            "status": rec.get("status"),
            "pending": sum(1 for d in rec.get("decisions") or [] if not d.get("choice")),
            "code": len(rec.get("code") or []),
            "files": len(rec.get("files") or []),
            "updatedAt": rec.get("updatedAt"),
        })
    return {"ok": True, "ledger": str(path), "project": ledger.get("project", {}).get("name"),
            "question": ledger.get("question"), "records": rows}


def cmd_show(ledger: dict, path: Path, args) -> dict:
    _, rec = find_record(ledger, args.id)
    return {"ok": True, "ledger": str(path), "record": rec}


def cmd_append(ledger: dict, path: Path, args) -> dict:
    payload = load_payload(args)
    rec = norm_record(payload)
    if any(r.get("id") == rec["id"] for r in ledger["records"]):
        raise ValueError(f"记录 id 重复：{rec['id']}")
    warnings = check_paths(path.parent.parent, rec)
    if not args.dry_run:
        ledger["records"].append(rec)
    return {"ok": True, "action": "append", "dryRun": args.dry_run,
            "record": rec, "warnings": warnings,
            "total": len(ledger["records"]) + (1 if args.dry_run else 0)}


def cmd_update(ledger: dict, path: Path, args) -> dict:
    payload = load_payload(args)
    idx, old = find_record(ledger, args.id)
    merged = merge_record(old, payload)
    warnings = check_paths(path.parent.parent, merged)
    if not args.dry_run:
        ledger["records"][idx] = merged
    return {"ok": True, "action": "update", "dryRun": args.dry_run,
            "record": merged, "warnings": warnings}


def cmd_decide(ledger: dict, path: Path, args) -> dict:
    found = False
    for rec in ledger["records"]:
        for d in rec.get("decisions") or []:
            if d.get("id") == args.decision:
                if not args.dry_run:
                    d["choice"] = args.choice
                    d["note"] = args.note or d.get("note", "")
                    d["status"] = "decided"
                    rec["updatedAt"] = now()
                found = True
    if not found:
        raise KeyError(f"找不到决策 id：{args.decision}")
    return {"ok": True, "action": "decide", "dryRun": args.dry_run,
            "decision": args.decision, "choice": args.choice, "note": args.note}


COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "append": cmd_append,
    "update": cmd_update,
    "decide": cmd_decide,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Agent执行记录 · 账本追加器（仅在显式要求记录时使用）")
    p.add_argument("--root", help="项目根目录；默认从当前目录向上找 .agent-log/ledger.json")
    p.add_argument("--ledger", help="直接指定 ledger.json 路径，优先于 --root")
    p.add_argument("--init", action="store_true", help="账本不存在时新建一份（默认不新建）")
    p.add_argument("--dry-run", action="store_true", help="只预览，不写盘、不备份")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出记录摘要")
    show = sub.add_parser("show", help="查看某条记录全文")
    show.add_argument("--id", required=True)
    for name in ("append", "update"):
        s = sub.add_parser(name, help="追加一条记录 / 按锚点更新")
        if name == "update":
            s.add_argument("--id", required=True)
        s.add_argument("--payload-file", help="JSON 文件路径；- 表示从 stdin 读")
        s.add_argument("--payload", help="内联 JSON 字符串（不推荐，中文与换行易被 shell 转义）")
    decide = sub.add_parser("decide", help="为某个决策填上研究者的拍板")
    decide.add_argument("--decision", required=True)
    decide.add_argument("--choice", required=True)
    decide.add_argument("--note", default="")
    return p


def main() -> int:
    args = build_parser().parse_args()
    needs_write = args.command in ("append", "update", "decide")
    try:
        path = resolve_ledger(args.root, args.ledger, args.init)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.parent / ".lock"
        with lock.open("a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            ledger = load_ledger(path, args.init)
            root = path.parent.parent
            ledger.setdefault("project", {})["root"] = str(root)
            result = COMMANDS[args.command](ledger, path, args)
            if needs_write and not args.dry_run:
                result["backup"] = backup(path)
                save_ledger(path, ledger)
                result["ledger"] = str(path)
                result["updatedAt"] = ledger["updatedAt"]
            elif args.dry_run:
                result["ledger"] = str(path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI 需要把错误以 JSON 返回
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False, indent=2), file=sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
