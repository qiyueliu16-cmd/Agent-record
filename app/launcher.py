#!/usr/bin/env python3
"""「Agent执行记录」本地启动器（macOS / Linux 可直接运行，Windows 见 README）。

没有 MCP、没有 kernel、没有后台常驻的分析运行时。
启动后只做四件事：摘代理 → 复用或拉起纯标准库控制台 → 开窗口 → 关窗即走。
服务默认常驻以便秒开，用 --stop 彻底退出。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

try:  # Windows 没有 fcntl，退化为无锁（单机单用户场景可接受）
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

HERE = Path(__file__).resolve().parent


def runtime_logs() -> Path:
    """在 .app 内运行时把状态写到用户目录，避免改动已签名的 bundle。

    直接从仓库运行时仍写 app/logs/（已被 .gitignore 排除）。
    """
    if ".app/Contents/" in str(HERE):
        base = Path.home() / "Library" / "Application Support" / "Agent执行记录" / "logs"
    else:
        base = HERE / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


LOGS = runtime_logs()
STATE = LOGS / "desktop_app.json"
LOCK = LOGS / "desktop_launch.lock"
SERVER = HERE / "server.py"

APP_NAME = "Agent执行记录"
APP_MARK = "agent-execution-log"
LAUNCHER_VERSION = 1
BASE_PORT = int(os.environ.get("AGENT_LOG_PORT") or 58400)
PORT_SPAN = 12

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@contextlib.contextmanager
def locked(handle):
    """Unix 下用 flock 防止多个启动器同时抢端口；其它平台退化为空锁。"""
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_EX)
    try:
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_UN)


def log(message: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / "desktop_launch.log").open("a") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    print(message, file=sys.stderr, flush=True)


def http_json(url: str, timeout: float = 2.0):
    try:
        with _OPENER.open(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (OSError, ValueError, urllib.error.HTTPError):
        return None


def health(port: int) -> dict | None:
    data = http_json(f"http://127.0.0.1:{int(port)}/api/health")
    if isinstance(data, dict) and data.get("app") == APP_MARK and data.get("ok"):
        return data
    return None


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def write_state(state: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(STATE)


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        # Windows 上 os.kill(pid, 0) 会真的终止进程，必须改用 tasklist 查询
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {int(pid)}"], text=True,
                stderr=subprocess.DEVNULL, timeout=5,
            )
            return str(int(pid)) in out
        except (OSError, subprocess.SubprocessError, ValueError):
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def owns_process(pid: int) -> bool:
    ps = shutil.which("ps")
    if not ps:
        return False
    try:
        cmd = subprocess.check_output(
            [ps, "-p", str(int(pid)), "-o", "command="],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return str(SERVER) in cmd


def ensure_console() -> tuple[dict, bool]:
    LOGS.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as lock, locked(lock):
        state = read_state()
        if (state.get("launcher_version") == LAUNCHER_VERSION
                and state.get("port") and health(state["port"])
                and pid_alive(state.get("pid", 0))):
            return state, False

        for offset in range(PORT_SPAN):
            port = BASE_PORT + offset
            seen = health(port)
            if seen:
                state = {"pid": int(seen["pid"]), "port": port,
                         "url": f"http://127.0.0.1:{port}",
                         "launcher_version": LAUNCHER_VERSION, "adopted": True}
                write_state(state)
                return state, False

        if not SERVER.is_file():
            raise RuntimeError(f"找不到控制台服务：{SERVER}")
        port = next((BASE_PORT + o for o in range(PORT_SPAN) if port_free(BASE_PORT + o)), None)
        if port is None:
            raise RuntimeError(f"{BASE_PORT}–{BASE_PORT + PORT_SPAN - 1} 端口全被占用")
        env = os.environ.copy()
        env.update({"PORT": str(port), "HOST": "127.0.0.1", "PYTHONUNBUFFERED": "1"})
        with (LOGS / "desktop_server.log").open("a") as fh:
            fh.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 port={port} ===\n")
            fh.flush()
            child = subprocess.Popen(
                [sys.executable, str(SERVER), "--serve"],
                cwd=str(HERE), env=env, stdin=subprocess.DEVNULL,
                stdout=fh, stderr=subprocess.STDOUT, start_new_session=True,
            )
        state = {"pid": child.pid, "port": port, "url": f"http://127.0.0.1:{port}",
                 "launcher_version": LAUNCHER_VERSION, "adopted": False}
        write_state(state)
        for _ in range(80):
            if child.poll() is not None:
                raise RuntimeError(f"控制台启动失败，详见 {LOGS / 'desktop_server.log'}")
            if health(port):
                return state, True
            time.sleep(0.2)
        raise RuntimeError(f"控制台 16s 内未就绪，详见 {LOGS / 'desktop_server.log'}")


def stop_console(state: dict) -> bool:
    pid = state.get("pid")
    if not pid or not pid_alive(int(pid)):
        return False
    try:
        os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
    except (OSError, ValueError, AttributeError):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            return False
    for _ in range(24):
        if not pid_alive(int(pid)):
            return True
        time.sleep(0.125)
    return False


def chrome_app_window(url: str) -> bool:
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "microsoft-edge", "chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for binary in candidates:
        if not Path(binary).is_file():
            continue
        profile = LOGS / "chrome-profile"
        profile.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [binary, f"--app={url}", "--no-proxy-server", "--no-first-run",
             "--no-default-browser-check", f"--user-data-dir={profile}",
             "--window-size=1520,980"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        log(f"窗口: Chrome 应用模式 pid={proc.pid}")
        try:
            proc.wait()
        except KeyboardInterrupt:
            pass
        return True
    return False


def open_window(url: str) -> str:
    try:
        import webview  # noqa: PLC0415  可选依赖；未安装时自动降级为浏览器窗口
    except Exception:
        webview = None
    if webview is not None:
        try:
            webview.create_window(
                APP_NAME, url, width=1500, height=980, min_size=(1080, 680),
                background_color="#F6F7F4", text_select=True,
            )
            webview.start()
            return "native"
        except Exception as exc:  # noqa: BLE001
            log(f"原生窗口不可用（{type(exc).__name__}: {exc}），改用 Chrome 应用窗口")
    if chrome_app_window(url):
        return "chrome-app"
    webbrowser.open(url)
    return "browser"


def selftest(url: str) -> dict:
    out: dict = {"url": url}
    try:
        with _OPENER.open(url, timeout=5) as resp:
            html = resp.read().decode("utf-8", "replace")
        out["page"] = {"status": 200, "chars": len(html),
                       "has_editor": "btnReport" in html, "has_title": APP_NAME in html}
    except Exception as exc:
        out["page"] = {"error": str(exc)}
    out["health"] = http_json(url + "/api/health", 5)
    ledger = http_json(url + "/api/ledger", 5)
    out["ledger"] = {"records": len((ledger or {}).get("records", [])),
                     "name": (ledger or {}).get("project", {}).get("name")}
    files = http_json(url + "/api/files", 10)
    out["files"] = {"count": len((files or {}).get("files", []))}
    out["ok"] = bool(out["page"].get("has_editor")) and bool(out["health"])
    return out


def alert(message: str) -> None:
    if sys.platform != "darwin" or not Path("/usr/bin/osascript").is_file():
        return
    subprocess.run(
        ["/usr/bin/osascript", "-e", "on run argv",
         "-e", f'display alert "{APP_NAME}" message (item 1 of argv) as critical',
         "-e", "end run", message], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--no-window", action="store_true", help="只起服务，不开窗")
    parser.add_argument("--stop", action="store_true", help="停止控制台")
    parser.add_argument("--status", action="store_true", help="打印后台状态")
    parser.add_argument("--selftest", action="store_true", help="不开窗的端到端验收")
    parser.add_argument("--quit-services", action="store_true", help="关窗时一并停止服务")
    args = parser.parse_args()

    if args.stop:
        state = read_state()
        for offset in range(PORT_SPAN):
            seen = health(BASE_PORT + offset)
            if seen:
                state = {"pid": int(seen["pid"]), "port": BASE_PORT + offset}
                break
        stopped = stop_console(state)
        STATE.unlink(missing_ok=True)
        print(json.dumps({"ok": True, "stopped": stopped}, ensure_ascii=False), flush=True)
        return 0

    if args.status:
        state = read_state()
        seen = health(state.get("port", 0)) if state else None
        if not seen:
            for offset in range(PORT_SPAN):
                seen = health(BASE_PORT + offset)
                if seen:
                    state = {"pid": int(seen["pid"]), "port": BASE_PORT + offset,
                             "url": f"http://127.0.0.1:{BASE_PORT + offset}"}
                    break
        print(json.dumps({**state, "alive": bool(seen)}, ensure_ascii=False), flush=True)
        return 0 if seen else 1

    state = {}
    try:
        state, owned = ensure_console()
        log(f"控制台: {state['url']} pid={state['pid']} 新启动={owned}")
        if args.selftest:
            print(json.dumps(selftest(state["url"]), ensure_ascii=False, indent=2), flush=True)
            return 0
        if args.no_window:
            print(json.dumps({"ok": True, "console": state}, ensure_ascii=False, indent=2), flush=True)
            return 0
        kind = open_window(state["url"])
        log(f"窗口类型: {kind} -> {state['url']}")
        return 0
    except Exception as exc:  # noqa: BLE001
        message = f"{APP_NAME}未能打开：{exc}"
        log(message)
        if not args.no_window and not args.selftest:
            alert(message)
        return 1
    finally:
        if state and args.quit_services and not state.get("adopted"):
            stop_console(state)
            STATE.unlink(missing_ok=True)
            log("关窗退出：已停止本次拉起的服务")


if __name__ == "__main__":
    raise SystemExit(main())
