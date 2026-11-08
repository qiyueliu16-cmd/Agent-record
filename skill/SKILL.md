---
name: agent-execution-log
summary: 配合 Agent 记录每一次分析执行。研究者显式点名后，由 Agent 自动把代码、关键选择、结果、结果图与技术细节写成一条完整账本记录；不是默认后台行为。
description: "OPT-IN ONLY。仅当研究者明确点名 agent-execution-log 或「Agent执行记录」这个 skill，或明确说「记一笔」「记录这一步」「把刚才的分析记下来」「更新账本」「这一步我选 A」时使用。触发后由 Agent 自动完成记录的全部字段整理与写入，研究者无需手工填表；默认绝不后台静默追记、不在会话结束时自动写入、不改变其它会话的行为。作用是把分析步骤追加到项目目录内的 .agent-log/ledger.json，供本地工作台生成带图报告。"
---

# Agent执行记录 · 按需记录

## 定位

这个 skill 是「Agent 执行记录」平台的记录入口。**每次使用 Agent 完成一步分析后，研究者点名本 skill，Agent 即自动把这一步的来源、代码、关键选择、结果、结果图与技术细节整理成一条结构化记录**，写入项目账本；随后本地工作台可直接生成带图报告。研究者不需要手工填写表格，也不需要复制粘贴代码。

## 硬契约（先读这一条）

**本 skill 是开关，不是习惯。** 只有研究者显式加载本 skill、并给出明确的记录指令时，才可以调用脚本写账本。加载之后也只对本次请求生效，**不构成后续会话的默认行为**。下一个会话如果不点名，就不要记录，也不要主动追问「要不要记一笔」。

「什么时候记」由研究者决定，「记什么、怎么写」由 Agent 自动完成。宁可漏记，不可自作主张写。

| 可以做 | 不可以做 |
|---|---|
| 研究者说「记一笔 / 记录这一步 / 用 Agent执行记录 记下来」时追加一条 | 会话结束、任务完成时自动追记 |
| 研究者明确拍板「这步选 A」时，把对应决策填成 decided | 替研究者填 choice、把 pending 改成已决定 |
| 研究者说「把结果补到上一条」时按锚点更新 | 凭猜测补写没有来源的结果数字 |
| 研究者要求看账本时只读 list / show | 顺手整理、重排、删改已有记录 |

## 账本定位

账本是项目目录里的纯 JSON：`<项目根>/.agent-log/ledger.json`。工作台（默认端口 58400）每次读盘，写入后刷新界面即可看到；**脚本不依赖服务在运行**，也不需要启动桌面应用。

- 默认从当前目录向上找 `.agent-log/ledger.json`；在子目录里执行也能找到所属项目。
- 跨项目必须显式 `--root <项目根>`，避免把 A 项目的步骤记进 B 项目。
- 新项目加 `--init` 新建一份空账本；不加则报「未找到账本」，不会误建。
- 全局参数（`--root` / `--ledger` / `--dry-run` / `--init`）必须放在子命令**前面**。

## 记录边界

- **决策**：`choice` 留空即 `status: pending`。只有研究者明确说出选哪个，才填 choice 或用 `decide` 命令；推荐值照写在 `recommend`，不代拍板。
- **代码与图**：只写相对项目根的路径，`content` 一律留空（报告生成时现场读盘，账本不复制字节）。绝对路径和 `..` 会被拒绝。服务器上的路径写进 `serverPath`，大规模数据不落本地。
- **文件未同步**：脚本只给警告不阻断，因为服务器脚本常常还没拉回本地。
- 不改 `project` / `question` 等顶层字段，除非研究者明确要求。
- 不执行分析代码、不连服务器、不生成报告（出报告由工作台一键完成）。

## 工作流

1. 先 `list` 看现有记录与锚点，避免重复追加；`show --id <锚点>` 可读某条全文。
2. 用文件写入工具生成 payload JSON（中文与换行安全），**不要用 shell echo / 内联字符串拼 JSON**。Agent 依据本次会话上下文自动填充字段。
3. 先 `--dry-run` 预览，确认字段与路径无误，再去掉 `--dry-run` 正式写。
4. 回报研究者：新增锚点 id、写了哪些字段、有无待拍板决策、警告内容。

写盘前自动备份到 `.agent-log/backups/ledger-<时间戳>.json`（保留最近 10 份），写入用文件锁＋原子替换，不会与工作台界面互相覆盖。

## 命令

安装后脚本位于 `~/.workbuddy/skills/agent-execution-log/scripts/append_record.py`（也可用仓库里的 `skill/scripts/append_record.py`）。

```bash
S=~/.workbuddy/skills/agent-execution-log/scripts/append_record.py
R=/path/to/your/project

python3 "$S" --root "$R" list
python3 "$S" --root "$R" show --id r-20261108-xxxxxxxx
python3 "$S" --root "$R" --dry-run append --payload-file /tmp/agent-log-payload.json
python3 "$S" --root "$R" append --payload-file /tmp/agent-log-payload.json
python3 "$S" --root "$R" update --id r-20261108-xxxxxxxx --payload-file /tmp/agent-log-update.json
python3 "$S" --root "$R" decide --decision d-xxxxxxxxxx --choice A --note "研究者拍板"
python3 "$S" --root /path/to/new/project --init append --payload-file /tmp/agent-log-payload.json
```

`update` 的顶层字段覆盖原值，`decisions` 按 id 合并（未提及的决策保持原样），适合补结果、补图、补技术细节。`decide` 只改指定决策的 choice / note / status。

## payload 字段

一条记录对应界面里的一步，字段与工作台完全一致：

| 字段 | 含义 | 必填 |
|---|---|---|
| `title` | 步骤标题 | 建议 |
| `status` | `done` / `pending` | 否，默认 done |
| `question` | 这一步回答什么问题 | 是 |
| `provenance` | 数据来自哪、承接哪一步 | 是 |
| `decisions` | 关键选择：`question` / `options[{key,label,why}]` / `recommend` / `choice` / `note` | 否 |
| `result` | `headline` / `body` / `metrics[{label,value,note}]` | 是 |
| `technical` | 方法、参数、出图规格、已知局限 | 建议 |
| `code` | `[{label,path,lang}]` | 否 |
| `files` | `[{path,caption,serverPath,origin}]`，图片会自动进报告 | 否 |

示例（用文件写入工具存成 `/tmp/agent-log-payload.json`）：

```json
{
  "title": "③ 敏感性分析",
  "question": "结论对度量选择是否敏感？",
  "provenance": "承接 ② 的同一份只读数据；正式主口径不变，本步仅作敏感性对照。",
  "decisions": [
    {
      "question": "是否把替代度量写进正文主结果？",
      "options": [
        {"key": "A", "label": "只放补充材料", "why": "主口径已定，避免读者混淆两种度量"},
        {"key": "B", "label": "正文并列报告", "why": "更透明，但需解释方向差异"}
      ],
      "recommend": "A",
      "choice": "",
      "note": ""
    }
  ],
  "result": {
    "headline": "待补",
    "body": "结果出来后再按锚点 update 补齐，不要预填数字。",
    "metrics": []
  },
  "technical": "",
  "code": [{"label": "敏感性分析", "path": "scripts/step3_sensitivity.R", "lang": "R"}],
  "files": []
}
```

`choice` 留空是刻意的：这条决策会显示成「待研究者决定」，等拍板后再用 `decide` 填。

## 写完

刷新工作台即可看到新记录；点「生成报告」才会把新记录写进 HTML / Markdown 报告。报告里的图片和代码全文是从项目目录现场读的，所以脚本同步下来改过之后，重新生成报告即可，不用改账本。
