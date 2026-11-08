#!/usr/bin/env python3
"""「Agent执行记录」报告生成器。

输入是项目目录里的 .agent-log/ledger.json，输出两份：
  - <项目根>/Agent执行记录_报告/report.html  单文件自包含，图片 base64 内嵌，可直接打印成 PDF
  - <项目根>/Agent执行记录_报告/report.md    Markdown，图片用相对路径，便于转 Word / 论文附录

设计要点：账本只存相对路径，不复制代码全文和图片字节。生成时现场读磁盘，
所以服务器上的脚本同步下来、改过之后，报告自动跟着变。
"""
from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
CODE_EXT = {".R", ".r", ".py", ".sh", ".jl", ".m", ".sql", ".js", ".ts", ".cpp", ".c", ".pl"}
DOC_EXT = {".md", ".txt", ".log", ".csv", ".tsv", ".json", ".yaml", ".yml", ".pdf", ".xlsx", ".xls"}
INTERESTING = IMAGE_EXT | CODE_EXT | DOC_EXT | {".html", ".htm", ".rds", ".RData", ".h5ad", ".loom"}

LANG_BY_EXT = {
    ".R": "R", ".r": "R", ".py": "Python", ".sh": "Shell", ".jl": "Julia",
    ".m": "MATLAB", ".sql": "SQL", ".js": "JavaScript", ".ts": "TypeScript",
}


def classify(path: str) -> str:
    ext = Path(path).suffix
    if ext in IMAGE_EXT:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in CODE_EXT:
        return "script"
    if ext in {".csv", ".tsv", ".xlsx", ".xls"}:
        return "data"
    return "doc"


def safe_file(root: Path, rel: str) -> Path | None:
    """目录穿越防护：任何引用都必须落在项目根目录内。"""
    if not rel or not isinstance(rel, str):
        return None
    try:
        target = (root / rel).resolve()
        target.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return target if target.is_file() else None


def read_text(path: Path, limit: int = 200_000) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def image_data_uri(path: Path) -> str | None:
    ext = path.suffix.lower()
    mime = "image/svg+xml" if ext == ".svg" else (mimetypes.guess_type(path.name)[0] or "image/png")
    try:
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None


# ---- 极简 Markdown：够写结果介绍与技术细节，不引第三方依赖 ----
def md_inline(text: str) -> str:
    out = html.escape(str(text or ""))
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


def md_blocks(text: str) -> str:
    """按行分组：连续普通行成段落，连续列表行成一个 ul，避免漏掉开标签。"""
    parts: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            parts.append("<p>" + "<br>".join(md_inline(x) for x in paragraph) + "</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{md_inline(x)}</li>" for x in bullets) + "</ul>")
            bullets.clear()

    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_bullets()
        elif stripped.startswith(("- ", "* ", "· ")):
            flush_paragraph()
            bullets.append(stripped[2:])
        elif re.match(r"^\d+[\.、]\s*", stripped):
            flush_paragraph()
            bullets.append(re.sub(r"^\d+[\.、]\s*", "", stripped))
        else:
            flush_bullets()
            paragraph.append(stripped)
    flush_paragraph()
    flush_bullets()
    return "\n".join(parts)


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def decision_html(dec: dict) -> str:
    options = "".join(
        f'<li><span class="key">{esc(o.get("key"))}</span>'
        f'<span class="opt-label">{esc(o.get("label"))}</span>'
        f'<span class="why">{esc(o.get("why"))}</span></li>'
        for o in dec.get("options", [])
    )
    choice = dec.get("choice")
    picked = next((o for o in dec.get("options", []) if o.get("key") == choice), None)
    if choice:
        verdict = (f'<div class="verdict decided">研究者拍板 <b>{esc(choice)}</b>'
                   + (f' · {esc(picked.get("label"))}' if picked else "")
                   + (f' <span class="muted">（Agent 推荐 {esc(dec.get("recommend"))}）</span>'
                      if dec.get("recommend") and dec.get("recommend") != choice else "")
                   + "</div>")
    else:
        verdict = ('<div class="verdict pending">待研究者决定'
                   + (f' · Agent 推荐 {esc(dec.get("recommend"))}' if dec.get("recommend") else "")
                   + "</div>")
    note = (f'<div class="note">{md_inline(dec.get("note"))}</div>' if dec.get("note") else "")
    return (f'<div class="decision"><div class="q">{esc(dec.get("question"))}</div>'
            f'<ul class="options">{options}</ul>{verdict}{note}</div>')


def record_html(rec: dict, root: Path, index: int) -> str:
    rid = esc(rec.get("id"))
    parts = [f'<section class="record" id="{rid}">',
             f'<div class="rec-head"><span class="step">{index:02d}</span>'
             f'<h2>{esc(rec.get("title"))}</h2>'
             f'<span class="status {esc(rec.get("status") or "done")}">'
             f'{"待决定" if rec.get("status") == "pending" else "已完成"}</span></div>']

    parts.append('<div class="ask"><span class="tag">这一步回答什么</span>'
                 f'<div>{md_inline(rec.get("question"))}</div></div>')
    if rec.get("provenance"):
        parts.append('<div class="prov"><span class="tag">来自哪些数据和步骤</span>'
                     f'<div>{md_inline(rec["provenance"])}</div></div>')

    for dec in rec.get("decisions", []):
        parts.append(decision_html(dec))

    result = rec.get("result") or {}
    if result:
        parts.append('<h3>结果与内容介绍</h3>')
        if result.get("headline"):
            parts.append(f'<div class="headline">{md_inline(result["headline"])}</div>')
        if result.get("body"):
            parts.append(md_blocks(result["body"]))
        metrics = result.get("metrics") or []
        if metrics:
            rows = "".join(
                f'<tr><td>{esc(m.get("label"))}</td><td class="val">{esc(m.get("value"))}</td>'
                f'<td>{esc(m.get("note"))}</td></tr>' for m in metrics)
            parts.append(f'<table class="metrics"><thead><tr><th>指标</th><th>数值</th>'
                         f'<th>说明</th></tr></thead><tbody>{rows}</tbody></table>')

    images = [f for f in rec.get("files", []) if classify(f.get("path", "")) == "image"]
    if images:
        parts.append('<h3>结果图</h3><div class="figures">')
        for f in images:
            target = safe_file(root, f.get("path", ""))
            uri = image_data_uri(target) if target else None
            if uri:
                parts.append(f'<figure><img src="{uri}" alt="{esc(f.get("caption") or f.get("path"))}">'
                             f'<figcaption>{md_inline(f.get("caption") or Path(f["path"]).name)}'
                             f'<span class="src">{esc(f.get("path"))}</span></figcaption></figure>')
            else:
                parts.append(f'<div class="missing">图片缺失：{esc(f.get("path"))}</div>')
        parts.append("</div>")

    if rec.get("technical"):
        parts.append('<h3>技术细节</h3><div class="technical">'
                     + md_blocks(rec["technical"]) + "</div>")

    codes = rec.get("code") or []
    if codes:
        parts.append('<h3>代码</h3>')
        for c in codes:
            text = c.get("content")
            source = "账本内联"
            if not text:
                target = safe_file(root, c.get("path", ""))
                text = read_text(target) if target else None
                source = esc(c.get("path"))
            if text is None:
                parts.append(f'<div class="missing">代码文件缺失：{esc(c.get("path"))}</div>')
                continue
            lang = esc(c.get("lang") or LANG_BY_EXT.get(Path(c.get("path", "")).suffix, ""))
            parts.append(f'<details class="code" open><summary>{esc(c.get("label") or c.get("path"))}'
                         f'<span class="src">{source}</span></summary>'
                         f'<pre><code class="lang-{lang}">{esc(text)}</code></pre></details>')

    others = [f for f in rec.get("files", [])
              if classify(f.get("path", "")) not in ("image",)]
    if others:
        parts.append('<h3>关联文件</h3><ul class="files">')
        for f in others:
            origin = f.get("origin") or "local"
            extra = f'<span class="server-path">服务器：{esc(f.get("serverPath"))}</span>' if f.get("serverPath") else ""
            parts.append(f'<li><span class="kind">{esc(classify(f.get("path", "")))}</span>'
                         f'<code>{esc(f.get("path"))}</code> {md_inline(f.get("caption"))}'
                         f'<span class="origin">{esc(origin)}</span>{extra}</li>')
        parts.append("</ul>")

    parts.append(f'<div class="anchor">锚点 <code>{rid}</code> · 指着它提要求，Agent 可准确接手</div>')
    parts.append("</section>")
    return "\n".join(parts)


CSS = """
:root{--ink:#20242b;--muted:#6b7280;--line:#e3e6ea;--bg:#f7f8f5;--card:#fff;
--accent:#2f6f62;--accent-soft:#e8f2ef;--warn:#a8641c;--warn-soft:#fdf3e5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
 font-size:15px;line-height:1.75}
.wrap{max-width:960px;margin:0 auto;padding:48px 40px 96px}
.cover{border-bottom:2px solid var(--ink);padding-bottom:28px;margin-bottom:36px}
.cover .eyebrow{font-size:12px;letter-spacing:.18em;color:var(--accent);font-weight:600}
.cover h1{font-size:30px;margin:10px 0 8px;line-height:1.35}
.cover .q{font-size:16px;color:#40474f}
.cover .meta{color:var(--muted);font-size:13px;margin-top:18px}
.toc{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 24px;margin-bottom:40px}
.toc h4{margin:0 0 10px;font-size:13px;color:var(--muted);letter-spacing:.08em}
.toc ol{margin:0;padding-left:20px}.toc a{color:var(--ink);text-decoration:none}
.toc a:hover{color:var(--accent)}
.record{background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:28px 32px;margin-bottom:28px;break-inside:avoid}
.rec-head{display:flex;align-items:center;gap:14px;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:20px}
.rec-head h2{font-size:20px;margin:0;flex:1}
.step{font:600 13px/1 ui-monospace,monospace;color:#fff;background:var(--accent);
 padding:8px 9px;border-radius:6px}
.status{font-size:12px;padding:4px 10px;border-radius:20px;background:var(--accent-soft);color:var(--accent)}
.status.pending{background:var(--warn-soft);color:var(--warn)}
h3{font-size:14px;letter-spacing:.04em;color:var(--accent);margin:28px 0 12px;
 border-left:3px solid var(--accent);padding-left:10px}
.ask,.prov{display:flex;gap:12px;align-items:flex-start;margin-bottom:10px;font-size:14px}
.tag{flex:0 0 118px;color:var(--muted);font-size:12px;padding-top:3px}
.decision{border:1px solid var(--line);background:#fcfcfb;border-radius:9px;padding:16px 18px;margin:18px 0}
.decision .q{font-weight:600;margin-bottom:10px}
.options{list-style:none;padding:0;margin:0 0 12px}
.options li{display:flex;gap:10px;align-items:baseline;padding:5px 0;font-size:14px}
.key{flex:0 0 22px;height:22px;line-height:22px;text-align:center;border-radius:5px;
 background:#eef0f2;font:600 12px/22px ui-monospace,monospace}
.opt-label{font-weight:600;flex:0 0 auto}
.why{color:var(--muted);font-size:13px}
.verdict{font-size:13px;padding:8px 12px;border-radius:6px;margin-top:6px}
.verdict.decided{background:var(--accent-soft);color:#1f574b}
.verdict.pending{background:var(--warn-soft);color:var(--warn)}
.note{color:var(--muted);font-size:13px;margin-top:8px}
.headline{background:var(--accent-soft);border-radius:8px;padding:14px 18px;
 font-size:16px;font-weight:600;margin-bottom:12px}
p{margin:8px 0}ul{margin:8px 0;padding-left:22px}li{margin:4px 0}
table.metrics{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px}
table.metrics th,table.metrics td{border:1px solid var(--line);padding:8px 12px;text-align:left}
table.metrics th{background:#f3f5f3;font-weight:600;font-size:12px;color:var(--muted)}
table.metrics .val{font-family:ui-monospace,monospace;font-weight:600;white-space:nowrap}
.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin:14px 0}
figure{margin:0;border:1px solid var(--line);border-radius:8px;padding:12px;background:#fff}
figure img{width:100%;display:block;border-radius:4px}
figcaption{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.6}
.src{display:block;font:11px/1.5 ui-monospace,monospace;color:#9aa1a9;margin-top:4px}
.technical{background:#f8f9f7;border-radius:8px;padding:14px 18px;font-size:14px}
code,pre{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
pre{margin:0;padding:16px;background:#f7f8f6;border-radius:0 0 7px 7px;
 overflow-x:auto;font-size:12px;line-height:1.6;white-space:pre}
.details/code summary{cursor:pointer}
.code{border:1px solid var(--line);border-radius:7px;overflow:hidden;margin:10px 0}
.code summary{padding:10px 14px;background:#f1f3f1;font-size:13px;font-weight:600}
.code summary .src{display:inline;margin-left:10px;font-weight:400}
ul.files{list-style:none;padding:0}
ul.files li{border-bottom:1px dashed var(--line);padding:7px 0;font-size:13px}
.kind{display:inline-block;min-width:52px;font-size:11px;color:var(--accent);
 background:var(--accent-soft);border-radius:4px;padding:2px 6px;margin-right:8px;text-align:center}
.origin{font-size:11px;color:var(--muted);margin-left:8px}
.server-path{display:block;color:var(--muted);font-size:11px;margin-left:60px}
.missing{color:#b42318;background:#fef3f2;padding:8px 12px;border-radius:6px;font-size:13px}
.anchor{margin-top:22px;padding-top:14px;border-top:1px dashed var(--line);
 font-size:12px;color:var(--muted)}
.appendix{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px 30px}
.appendix h2{font-size:18px;margin:0 0 14px}
.footer{text-align:center;color:var(--muted);font-size:12px;margin-top:40px}
@media print{body{background:#fff}.wrap{padding:0;max-width:none}
 .record,.appendix{border:1px solid #ddd;box-shadow:none}
 .code summary{background:#eee}.code pre{max-height:none}}
"""


def build_html(ledger: dict, root: Path) -> str:
    project = ledger.get("project") or {}
    records = ledger.get("records") or []
    toc = "".join(
        f'<li><a href="#{esc(r.get("id"))}">{esc(r.get("title"))}</a></li>' for r in records)
    body = "\n".join(record_html(r, root, i + 1) for i, r in enumerate(records))

    # 附录：项目里所有被登记过的文件
    seen: dict[str, dict] = {}
    for r in records:
        for f in r.get("files", []):
            seen.setdefault(f.get("path"), f)
        for c in r.get("code", []):
            if c.get("path"):
                seen.setdefault(c["path"], {"path": c["path"], "caption": "代码"})
    appendix_rows = []
    for rel, f in sorted(seen.items()):
        target = safe_file(root, rel)
        size = f"{target.stat().st_size / 1024:.1f} KB" if target else "未找到"
        sp = f.get("serverPath")
        appendix_rows.append(
            f'<li><span class="kind">{esc(classify(rel))}</span><code>{esc(rel)}</code>'
            f'<span class="origin">{size}</span>'
            + (f'<span class="server-path">服务器：{esc(sp)}</span>' if sp else "") + "</li>")
    server = project.get("server") or {}
    server_line = (f'<p><b>服务器登记</b>：{esc(server.get("alias") or "未填")} · '
                   f'{esc(server.get("root") or "未填")}。大数据不落本地，此处只记出处。</p>'
                   if server else "")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(project.get("name") or "Agent执行记录")} · 结果报告</title>
<style>{CSS}</style></head><body><div class="wrap">
<div class="cover">
  <div class="eyebrow">AGENT EXECUTION LOG · 结果报告</div>
  <h1>{esc(project.get("name") or "未命名项目")}</h1>
  <div class="q">{esc(ledger.get("question") or "")}</div>
  <div class="meta">项目目录 {esc(root)} · 共 {len(records)} 条执行记录 ·
  生成于 {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
</div>
<div class="toc"><h4>目录</h4><ol>{toc}</ol></div>
{body}
<div class="appendix"><h2>附录 · 文件出处与服务器登记</h2>
<p>账本只记录相对路径；代码与图片在生成报告时从项目目录现场读取，因此文件更新后报告自动同步。</p>
{server_line}<ul class="files">{"".join(appendix_rows)}</ul></div>
<div class="footer">Agent 带路，决定权在你 · 本文件由「Agent执行记录」生成，图片已内嵌，可直接打印为 PDF</div>
</div></body></html>"""


def build_markdown(ledger: dict, root: Path) -> str:
    project = ledger.get("project") or {}
    out = [f"# {project.get('name') or '未命名项目'} · Agent执行记录",
           "", f"> {ledger.get('question') or ''}", "",
           f"项目目录：`{root}`", "",
           f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "---", ""]
    for i, rec in enumerate(ledger.get("records") or [], 1):
        out += [f"## {i:02d}. {rec.get('title')}", "",
                f"**这一步回答什么**：{rec.get('question') or ''}", ""]
        if rec.get("provenance"):
            out += [f"**来自哪些数据和步骤**：{rec['provenance']}", ""]
        for dec in rec.get("decisions", []):
            out += [f"### 关键选择：{dec.get('question')}", ""]
            for o in dec.get("options", []):
                out.append(f"- **{o.get('key')}** {o.get('label')} —— {o.get('why')}")
            out.append("")
            if dec.get("choice"):
                out += [f"**研究者拍板：{dec['choice']}**"
                        + (f"（Agent 推荐 {dec.get('recommend')}）"
                           if dec.get("recommend") and dec.get("recommend") != dec.get("choice") else ""), ""]
            else:
                out += [f"**待研究者决定**" + (f"（Agent 推荐 {dec.get('recommend')}）"
                                            if dec.get("recommend") else ""), ""]
        result = rec.get("result") or {}
        if result:
            out += ["### 结果与内容介绍", ""]
            if result.get("headline"):
                out += [f"**{result['headline']}**", ""]
            if result.get("body"):
                out += [result["body"], ""]
            for m in result.get("metrics") or []:
                out.append(f"- {m.get('label')}：`{m.get('value')}` {m.get('note') or ''}")
            out.append("")
        for f in rec.get("files", []):
            if classify(f.get("path", "")) == "image":
                out += [f"![{f.get('caption') or Path(f['path']).name}](../{f['path']})", "",
                        f"*{f.get('caption') or ''}（`{f['path']}`）*", ""]
        if rec.get("technical"):
            out += ["### 技术细节", "", rec["technical"], ""]
        for c in rec.get("code", []):
            text = c.get("content")
            if not text:
                target = safe_file(root, c.get("path", ""))
                text = read_text(target) if target else None
            lang = c.get("lang") or LANG_BY_EXT.get(Path(c.get("path", "")).suffix, "")
            out += ["### 代码 · " + (c.get("label") or c.get("path") or ""), "",
                    f"来源：`{c.get('path') or '账本内联'}`", "",
                    f"```{lang}", (text or "# 文件缺失").rstrip(), "```", ""]
        others = [f for f in rec.get("files", []) if classify(f.get("path", "")) != "image"]
        if others:
            out += ["**关联文件**", ""]
            for f in others:
                extra = f"（服务器 `{f.get('serverPath')}`）" if f.get("serverPath") else ""
                out.append(f"- `{f.get('path')}` {f.get('caption') or ''}{extra}")
            out.append("")
        out += [f"> 锚点 `{rec.get('id')}`：指着它提要求，Agent 可准确接手。", "", "---", ""]
    return "\n".join(out)


def generate(ledger_path: Path) -> dict:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    root = Path(ledger["project"]["root"]).expanduser().resolve()
    outdir = root / "Agent执行记录_报告"
    outdir.mkdir(parents=True, exist_ok=True)
    html_path = outdir / "report.html"
    md_path = outdir / "report.md"
    html_path.write_text(build_html(ledger, root), encoding="utf-8")
    md_path.write_text(build_markdown(ledger, root), encoding="utf-8")

    images = 0
    for rec in ledger.get("records", []):
        for f in rec.get("files", []):
            if classify(f.get("path", "")) == "image" and safe_file(root, f.get("path", "")):
                images += 1
    return {"ok": True, "html": str(html_path), "markdown": str(md_path),
            "records": len(ledger.get("records", [])), "images": images,
            "html_bytes": html_path.stat().st_size, "outdir": str(outdir)}
