# 使用方法

本文面向第一次下载本仓库的研究者。全部功能基于 Python 3.9+ 标准库，不需要安装依赖，也不需要连接外部服务。

---

## 1. 安装与启动

```bash
git clone https://github.com/qiyueliu16-cmd/Agent-record.git
cd Agent-record
make setup    # 安装 Agent 记录 skill
make start    # 启动工作台，默认 http://127.0.0.1:58400
```

`make setup` 把 `skill/` 复制到 `~/.workbuddy/skills/agent-execution-log/`。若该目录已存在，脚本会先备份成同级的 `.bak-<时间戳>` 再安装，不会静默覆盖。可用 `--target` 指定其它目录，`--print-path` 查看默认路径。

启动方式按环境选择：

| 环境 | 命令 | 说明 |
|---|---|---|
| macOS / Linux（图形界面） | `make start` | 自动开浏览器或 Chrome 应用窗口 |
| 远程 / 无窗口 | `make headless` | 只启动服务，浏览器手动访问 `http://127.0.0.1:58400` |
| Windows | `python app/server.py --serve` | 手动打开上述地址，功能一致 |
| macOS 桌面应用 | `make desktop` | 生成 `~/Applications/Agent执行记录.app`，双击启动（可选） |

`make check` 可在不开窗的情况下完成端到端自检；`make stop` 停止后台服务。端口被占用时会自动顺延，可用 `AGENT_LOG_PORT` 修改起始端口。

启动后默认打开仓库自带的 `examples/demo-project`。界面左上是课题总问题，左侧是记录时间线，中间是分步编辑区，右侧是当前项目可关联的文件列表，右上提供「生成报告」「重新扫描文件」「生成同步命令」等操作。

---

## 2. 切换到自己的项目

在工作台「项目根目录」填入绝对路径并确认，账本会读写该项目下的 `.agent-log/ledger.json`；目录不存在时按空白账本初始化。也可在启动时指定：

```bash
AGENT_LOG_ROOT=/path/to/project make start
```

建议一个研究课题对应一个项目目录，账本随项目一起纳入 Git。工作台只在本机 `app/logs/` 里记住最近打开过哪些项目，这个目录不入库，也不应公开。

---

## 3. 配合 Agent 记录每一次分析（核心流程）

平台的设计目标是：**每次与 Agent 共同完成一步分析，就把这一步完整、可复核地留下来**。研究者只需给出一句指令，记录的整理与写入由 Agent 自动完成。

### 3.1 一次典型循环

1. 研究者与 Agent 在服务器上跑完一步分析，得到脚本、图与结果。
2. 研究者在会话中显式点名记录：

   ```
   用 Agent执行记录 记一笔：把刚才这步记下来
   ```

   Agent 会自动读取现有账本锚点，整理「这一步回答什么、数据来自哪、代码路径、关键选择、结果指标、结果图、技术细节」，预览确认后写入账本，并回报新增锚点与待拍板项。
3. 遇到关键选择，Agent 给出选项、理由与推荐；研究者拍板：

   ```
   这步选 A
   ```

   Agent 把对应决策写为已定。未拍板的选择会保持「待研究者决定」，并出现在报告里。
4. 需要补充结果或图片时，指着锚点提要求：

   ```
   把新出的图补到 r-20261108-xxxxxxxx 这条
   ```

   Agent 按锚点更新，不会影响其它记录。
5. 阶段结束时在工作台点「生成报告」，得到带图、带代码、带技术细节的 HTML 与 Markdown。

### 3.2 为什么需要显式点名

会话结束后没有后台进程继续监听，因此平台不做静默追记，也不在每次任务结束时自动写入。**「什么时候记」由研究者决定，「记什么、怎么写」由 Agent 自动完成**。这样既避免账本混入无关内容，也保持「Agent 带路、决定权在你」的分工。若不点名，Agent 不会写账本。

### 3.3 记录器命令

安装后脚本位于 `~/.workbuddy/skills/agent-execution-log/scripts/append_record.py`，也可直接使用仓库中的 `skill/scripts/append_record.py`。全局参数必须放在子命令之前。

```bash
S=~/.workbuddy/skills/agent-execution-log/scripts/append_record.py
R=/path/to/your/project

python3 "$S" --root "$R" list
python3 "$S" --root "$R" show --id <锚点>
python3 "$S" --root "$R" --dry-run append --payload-file /tmp/payload.json
python3 "$S" --root "$R" append --payload-file /tmp/payload.json
python3 "$S" --root "$R" update --id <锚点> --payload-file /tmp/update.json
python3 "$S" --root "$R" decide --decision <决策 id> --choice A --note "研究者拍板"
python3 "$S" --root /path/to/new/project --init append --payload-file /tmp/payload.json
```

`--dry-run` 只预览、不写盘；`decisions` 按 id 合并，未提及的决策保持原样；`decide` 只改指定决策的 `choice` / `note` / `status`。每条记录会自动补齐 `id`、时间戳与默认字段，`code.content` 恒为空（报告现场读盘）。绝对路径、含 `..` 的路径会被拒绝；文件尚未从服务器同步下来只给警告、不阻断。

### 3.4 记录字段

| 字段 | 含义 |
|---|---|
| `title` / `status` | 步骤标题；`done` 或 `pending` |
| `question` | 这一步回答什么问题 |
| `provenance` | 数据来自哪些文件、承接哪一步 |
| `decisions` | 关键选择：`question` / `options[{key,label,why}]` / `recommend` / `choice` / `note` |
| `result` | `headline` / `body` / `metrics[{label,value,note}]` |
| `technical` | 方法、参数、出图规格、已知局限 |
| `code` | `[{label,path,lang}]`，路径为项目内相对路径 |
| `files` | `[{path,caption,serverPath,origin}]`，图片自动进入报告 |

完整 payload 示例见 `skill/SKILL.md`。决策的 `choice` 留空表示待拍板，Agent 不得代填。

---

## 4. 关联服务器上的结果

大规模数据留在服务器，账本里只登记「别名 + 根目录」作为出处。把脚本、图、小型结果表同步回项目目录后，在工作台点「重新扫描文件」并勾选即可关联。

界面上的「生成同步命令」只产出可复制的 `rsync` 命令，**不会执行、不会连接服务器**：

```bash
mkdir -p /path/to/project/from_server
rsync -avP my-server:/home/user/project/results/figure.svg /path/to/project/from_server/
```

若使用其它传输工具，可忽略该命令，直接把小文件放进项目目录再重新扫描。服务器上的原始路径可写进文件条目的 `serverPath` 字段，便于溯源。

---

## 5. 生成报告

在工作台点「生成报告」，输出到 `<项目根>/Agent执行记录_报告/`：

- `report.html`：单文件自包含，图片以 base64 内嵌，可直接用浏览器打印为 PDF。
- `report.md`：图片用相对路径，便于转 Word 或作为论文附录。

报告包含结果介绍与指标表、结果图与图注、技术细节、代码全文、关键选择卡、文件出处附录；每条记录带锚点 id。由于代码与图片是生成时从磁盘现场读取的，源文件更新后重新生成即可，无需修改账本。

支持的图片格式：PNG、JPG、JPEG、GIF、WEBP、BMP、SVG。PDF 等非图片文件列入附录，不会内嵌为图像。

---

## 6. 备份、回滚与常见问题

写盘前会自动把账本复制到 `.agent-log/backups/ledger-<时间戳>.json`（保留最近 10 份）。界面保存与 Agent 写入都使用原子替换，并加文件锁；需要回滚时，从 backups 里复制对应文件覆盖 `ledger.json` 即可。

| 现象 | 处理 |
|---|---|
| 端口被占用 | 启动器自动顺延；也可用 `AGENT_LOG_PORT=58500 make start` |
| 页面打不开 | 确认代理未劫持本地请求；启动器已自动清空代理并设置 `no_proxy` |
| 报告里图片不显示 | 检查文件是否在项目目录内、路径是否为相对路径；改完点「重新扫描文件」 |
| 代码未出现在报告 | `code[].path` 指向的文件不存在或写成了绝对路径 |
| 中文显示异常 | 页面与报告均为 UTF-8；若浏览器字体缺失，检查系统字体设置 |
| 记录写进了错误项目 | 用 `--root` 显式指定项目根；账本按目录隔离，不会自动跨项目 |
| Agent 没有记录 | 需要显式点名 `agent-execution-log` 或说「记一笔」；平台不做后台静默追记 |

---

## 7. 数据与隐私边界

- 示例项目全部为合成演示数据，不对应任何真实研究。
- 账本不复制代码与图片字节；只保存相对路径与文字描述。
- 服务只绑定 `127.0.0.1`，资源读取限制在项目目录内，拒绝路径穿越。
- `app/logs/` 可能包含本机项目路径，已由 `.gitignore` 排除，请勿公开。
- 平台不执行分析代码、不连服务器、不上传任何数据；研究者对写入账本的内容与最终报告负责。
