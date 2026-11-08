#!/usr/bin/env python3
"""「Agent执行记录」本地控制台。

只用 Python 标准库。不连 MCP、不起 R/Python kernel、不碰服务器，
只做四件事：打开本地项目目录、扫描可关联文件、读写 JSON 账本、生成报告。
所以没有超时、没有僵死进程、不需要自愈。
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report as report_mod  # noqa: E402

APP_MARK = "agent-execution-log"


def runtime_logs() -> Path:
    """在自包含 .app 内运行时把状态写到用户目录，避免改动已签名的 bundle。"""
    if ".app/Contents/" in str(HERE):
        base = Path.home() / "Library" / "Application Support" / "Agent执行记录" / "logs"
    else:
        base = HERE / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


LOGS = runtime_logs()
STATE = LOGS / "app.json"
LEDGER_DIR = ".agent-log"
LEDGER_NAME = "ledger.json"
# 默认打开仓库自带的合成示例项目；真实项目用 AGENT_LOG_ROOT 或界面切换指定。
DEMO_ROOT = HERE.parent / "examples" / "demo-project"
DEFAULT_ROOT = Path(os.environ.get("AGENT_LOG_ROOT") or DEMO_ROOT).expanduser()
MAX_BODY = 8 * 1024 * 1024
SKIP_DIRS = {".git", ".agent-log", "Agent执行记录_报告", "node_modules",
             "__pycache__", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
MAX_FILES = 3000


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id(prefix: str = "r") -> str:
    import uuid
    return f"{prefix}-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def read_state() -> dict:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"current": str(DEFAULT_ROOT) if DEFAULT_ROOT.is_dir() else str(Path.home()),
            "projects": []}


def write_state(state: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def current_root() -> Path:
    root = Path(read_state().get("current") or Path.home()).expanduser()
    try:
        return root.resolve()
    except OSError:
        return Path.home()


def ledger_path(root: Path) -> Path:
    return root / LEDGER_DIR / LEDGER_NAME


def blank_ledger(root: Path) -> dict:
    return {"schema": 1, "app": APP_MARK,
            "project": {"name": root.name, "root": str(root),
                        "server": {"alias": "", "root": "", "note": "大数据不落本地，此处只登记出处"}},
            "question": "这个课题要回答什么？",
            "updatedAt": now(), "records": []}


def load_ledger(root: Path) -> dict:
    path = ledger_path(root)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("project", {})["root"] = str(root)
            return data
        except (OSError, ValueError):
            pass
    return blank_ledger(root)


def save_ledger(root: Path, ledger: dict) -> dict:
    ledger["app"] = APP_MARK
    ledger["schema"] = 1
    ledger["project"]["root"] = str(root)
    ledger["updatedAt"] = now()
    folder = root / LEDGER_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = ledger_path(root)
    tmp = folder / (LEDGER_NAME + ".tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"ok": True, "path": str(path), "updatedAt": ledger["updatedAt"]}


def scan_files(root: Path) -> list[dict]:
    found: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root)
        for name in filenames:
            if name.startswith("."):
                continue
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            full = root / rel
            try:
                st = full.stat()
            except OSError:
                continue
            kind = report_mod.classify(rel)
            interesting = full.suffix.lower() in report_mod.INTERESTING or kind == "image"
            found.append({"path": rel.replace(os.sep, "/"), "kind": kind,
                          "size": st.st_size, "mtime": time.strftime(
                              "%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                          "interesting": interesting})
            if len(found) >= MAX_FILES:
                return sorted(found, key=lambda x: (not x["interesting"], x["path"]))
    return sorted(found, key=lambda x: (not x["interesting"], x["path"]))


def asset_path(root: Path, rel: str) -> Path | None:
    return report_mod.safe_file(root, rel)


def open_in_os(target: Path, reveal: bool = False) -> bool:
    """跨平台打开文件或在文件管理器中定位。失败只返回 False，不影响主流程。"""
    try:
        if sys.platform == "darwin":
            cmd = ["/usr/bin/open"] + (["-R"] if reveal else []) + [str(target)]
        elif sys.platform.startswith("linux"):
            cmd = ["xdg-open", str(target.parent if reveal else target)]
        elif os.name == "nt":
            if reveal:
                subprocess.Popen(["explorer", "/select,", str(target)])
                return True
            os.startfile(str(target))  # type: ignore[attr-defined]
            return True
        else:
            return False
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def handoff_text(ledger: dict, rid: str) -> dict:
    rec = next((r for r in ledger.get("records", []) if r.get("id") == rid), None)
    if not rec:
        return {"ok": False, "error": f"找不到记录 {rid}"}
    lines = [f"接手锚点：{rid}", f"项目：{ledger['project'].get('name')}",
             f"步骤：{rec.get('title')}", f"这一步回答：{rec.get('question') or ''}", ""]
    if rec.get("provenance"):
        lines += [f"来源：{rec['provenance']}", ""]
    for dec in rec.get("decisions", []):
        lines.append(f"关键选择：{dec.get('question')}")
        for o in dec.get("options", []):
            lines.append(f"  {o.get('key')}. {o.get('label')} —— {o.get('why')}")
        lines.append(f"  拍板：{dec.get('choice') or '待定'}"
                     + (f"（Agent 推荐 {dec.get('recommend')}）" if dec.get("recommend") else ""))
        lines.append("")
    result = rec.get("result") or {}
    if result.get("headline"):
        lines += [f"结果：{result['headline']}", ""]
    for c in rec.get("code", []):
        lines.append(f"代码：{c.get('path') or c.get('label')}")
    for f in rec.get("files", []):
        if f.get("serverPath"):
            lines.append(f"服务器出处：{f['serverPath']}")
    lines += ["", "请按这个锚点继续，不要改动本记录已确定的口径。"]
    return {"ok": True, "id": rid, "text": "\n".join(lines)}


def sync_command(ledger: dict, payload: dict) -> dict:
    """只生成可复制粘贴的同步命令，绝不执行、绝不连服务器。

    默认用通用的 rsync；用户可在账本的服务器别名与根目录里填自己的环境。
    """
    server = ledger.get("project", {}).get("server") or {}
    alias = payload.get("alias") or server.get("alias") or "my-server"
    sroot = (payload.get("serverRoot") or server.get("root") or "/home/user/project").rstrip("/")
    paths = [p for p in (payload.get("paths") or []) if isinstance(p, str) and p.strip()]
    if not paths:
        return {"ok": False, "error": "没有选择要同步的文件"}
    local_dir = payload.get("localDir") or "from_server"
    local = Path(ledger["project"]["root"]) / local_dir
    lines = [
        "# 只把小文件（脚本 / 图 / 结果表）拉回本地项目；大规模数据留在服务器，仅登记出处。",
        f"mkdir -p {shlex.quote(str(local))}",
    ]
    for p in paths:
        remote = p if p.startswith("/") else f"{sroot}/{p}"
        lines.append(f"rsync -avP {shlex.quote(f'{alias}:{remote}')} {shlex.quote(str(local))}/")
    lines += ["", "# 然后在工作台点「重新扫描文件」并勾选这些文件即可关联。"]
    return {"ok": True, "command": "\n".join(lines), "count": len(paths)}


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentLog/1.0"

    def log_message(self, fmt, *args):  # 只留错误，控制台日志不刷屏
        if " 4" in str(args[:1]) or " 5" in str(args[:1]):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8",
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def static(self, rel: str) -> None:
        path = (HERE / "web" / rel).resolve()
        try:
            path.relative_to((HERE / "web").resolve())
        except ValueError:
            self.json({"error": "forbidden"}, 403)
            return
        if not path.is_file():
            self.json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        root = current_root()

        if route in ("/", "/index.html"):
            return self.static("index.html")
        if route.startswith("/web/") and ".." not in route:
            return self.static(route[5:])

        if route == "/api/health":
            return self.json({"ok": True, "app": APP_MARK, "pid": os.getpid(),
                              "root": str(root), "ledger": ledger_path(root).is_file(),
                              "time": now()})
        if route == "/api/state":
            state = read_state()
            state["current"] = str(root)
            state["exists"] = root.is_dir()
            return self.json(state)
        if route == "/api/ledger":
            return self.json(load_ledger(root))
        if route == "/api/files":
            if not root.is_dir():
                return self.json({"ok": False, "error": "项目目录不存在", "files": []})
            return self.json({"ok": True, "root": str(root), "files": scan_files(root)})
        if route == "/api/asset":
            rel = (query.get("path") or [""])[0]
            target = asset_path(root, rel)
            if not target:
                return self.json({"error": "文件不存在或不在项目目录内"}, 404)
            if target.stat().st_size > 30 * 1024 * 1024:
                return self.json({"error": "文件过大，请用 Finder 打开"}, 413)
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            try:
                data = target.read_bytes()
            except OSError as exc:
                return self.json({"error": str(exc)}, 500)
            return self._send(200, data, ctype)
        if route == "/api/handoff":
            return self.json(handoff_text(load_ledger(root), (query.get("id") or [""])[0]))
        if route == "/api/report/open":
            target = root / "Agent执行记录_报告" / "report.html"
            if not target.is_file():
                return self.json({"ok": False, "error": "还没有生成报告"}, 404)
            opened = open_in_os(target)
            return self.json({"ok": True, "path": str(target), "opened": opened})
        return self.json({"error": "unknown route", "route": route}, 404)

    def do_POST(self) -> None:
        route = urllib.parse.urlparse(self.path).path
        payload = self.body()
        root = current_root()

        if route == "/api/project":
            candidate = Path(str(payload.get("root") or "")).expanduser()
            if not candidate.is_dir():
                return self.json({"ok": False, "error": f"目录不存在：{candidate}"}, 400)
            candidate = candidate.resolve()
            state = read_state()
            projects = [p for p in state.get("projects", []) if p.get("root") != str(candidate)]
            projects.insert(0, {"root": str(candidate), "name": candidate.name, "at": now()})
            state.update({"current": str(candidate), "projects": projects[:12]})
            write_state(state)
            return self.json({"ok": True, "root": str(candidate), "ledger": load_ledger(candidate)})

        if route == "/api/ledger":
            ledger = payload.get("ledger")
            if not isinstance(ledger, dict):
                return self.json({"ok": False, "error": "缺少账本内容"}, 400)
            return self.json(save_ledger(root, ledger))

        if route == "/api/report":
            ledger = payload.get("ledger")
            if isinstance(ledger, dict):
                save_ledger(root, ledger)
            try:
                return self.json(report_mod.generate(ledger_path(root)))
            except Exception as exc:  # noqa: BLE001
                return self.json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

        if route == "/api/sync-command":
            return self.json(sync_command(load_ledger(root), payload))

        if route == "/api/reveal":
            rel = str(payload.get("path") or "")
            target = asset_path(root, rel) if rel else root
            if not target:
                return self.json({"ok": False, "error": "路径无效"}, 400)
            opened = open_in_os(target, reveal=True)
            return self.json({"ok": True, "path": str(target), "opened": opened})

        if route == "/api/new-id":
            return self.json({"id": new_id(str(payload.get("prefix") or "r"))})

        return self.json({"error": "unknown route", "route": route}, 404)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Agent执行记录 控制台")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 58400))
    parser.add_argument("--host", default=os.environ.get("HOST") or "127.0.0.1")
    args = parser.parse_args()
    if not args.serve:
        print("用法：server.py --serve [--port 58400]")
        return 0
    LOGS.mkdir(parents=True, exist_ok=True)
    state = read_state()
    env_root = os.environ.get("AGENT_LOG_ROOT")
    if env_root and Path(env_root).expanduser().is_dir():
        state["current"] = str(Path(env_root).expanduser().resolve())
    elif not Path(state.get("current", "")).is_dir():
        state["current"] = str(DEFAULT_ROOT if DEFAULT_ROOT.is_dir() else Path.cwd())
        write_state(state)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    print(f"{APP_MARK} http://{args.host}:{args.port} root={state['current']}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
