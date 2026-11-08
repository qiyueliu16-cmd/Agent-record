# Agent执行记录（Agent-record）

一个用于**研究者与 Agent 共同维护分析过程**的本地工作台：把每一步的代码、关键选择、结果、结果图与技术细节沉淀为可复核的执行记录，并一键生成带图的结构化报告。

设计上坚持三条原则：

1. **记录与执行分离**：平台不执行分析代码、不连接计算服务器。代码由研究者在本地或服务器运行，平台只负责把「跑了什么、为什么这样选、得到了什么」记下来。因此没有 kernel、没有 MCP 会话、没有超时与僵死进程。
2. **来源可追溯**：账本只记录项目内的相对路径，不复制代码与图片字节；报告生成时现场从磁盘读取，源文件更新后报告自动同步。
3. **决定权在研究者**：Agent 负责带路与整理，遇到关键选择只给出选项与理由，拍板由研究者完成；未拍板的选择在报告中明确标注为「待研究者决定」。

> 本项目是**执行记录与报告工具**，不验证统计结论的正确性，也不替代研究者的学术判断。

---

## 本地运行

前置：Python 3.9+。**无需安装任何第三方包**，也无需 Node、R、数据库或网络服务。

选择一种方式取得代码（两种方式后续命令完全相同）：

```bash
# 方式 A：Git 克隆，目录名 Agent-record
git clone https://github.com/qiyueliu16-cmd/Agent-record.git
cd Agent-record

# 方式 B：仓库页 Code → Download ZIP，解压后目录名是 Agent-record-main
cd Agent-record-main
```

然后：

```bash
make check     # 建议先跑一次自检：页面、账本、文件扫描
make setup     # 安装 Agent 记录 skill（见下文）
make start     # 启动工作台并打开窗口
```

默认地址 `http://127.0.0.1:58400`；端口被占用时自动顺延，用 `make url` 查看实际地址。首次启动打开仓库自带的 `examples/demo-project`（合成示例数据），点「生成报告」即可看到完整输出。

| 命令 | 作用 |
|---|---|
| `make check` | 不开窗的端到端自检 |
| `make headless` | 只启动服务不开窗，适合远程或脚本化使用 |
| `make url` | 打印当前服务地址与进程状态 |
| `make stop` | 停止后台控制台服务 |
| `make desktop` | 生成可双击的 macOS 桌面应用（见下节） |
| `make demo` | 打印示例项目与账本路径 |

没有 `make` 的环境可直接调用脚本：`python3 scripts/install_skill.py`、`python3 app/launcher.py`、`python3 app/launcher.py --selftest`。

### 双击启动（推荐日常使用）

```bash
make desktop
```

生成 `~/Applications/Agent执行记录.app` 并在桌面创建快捷方式，图标由纯标准库现场生成，不需要 Pillow。**应用是自包含的**：仓库内容已复制进 `.app`，之后删除或移动下载解压的目录，双击仍可正常使用。Windows / Linux 请直接运行 `python3 app/launcher.py`；若仅需控制台，可用 `python3 app/server.py --serve`。

环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AGENT_LOG_ROOT` | `examples/demo-project` | 启动时打开的项目根目录 |
| `AGENT_LOG_PORT` | `58400` | 控制台端口，占用时自动顺延至下一个可用端口 |

切换自己的项目有两种方式：在工作台「项目根目录」填入绝对路径并点「打开项目」；或启动时指定 `AGENT_LOG_ROOT=/path/to/project make start`。账本固定落在项目目录内的 `.agent-log/ledger.json`，随项目走，可纳入版本管理。

---

## 配合 Agent 记录每一次分析

这是本平台的核心用法。**每次使用 Agent 完成一步分析后，在会话中显式点名记录 skill，Agent 即自动把这一步整理成一条完整记录**，研究者不需要手工填表、复制代码或整理图注：

```
用 Agent执行记录 记一笔：把刚才这步记下来
```

Agent 会自动完成：核对已有锚点 → 组织「这一步回答什么 / 数据来自哪 / 代码路径 / 关键选择 / 结果指标 / 结果图 / 技术细节」→ 预览校验 → 写入 `.agent-log/ledger.json` → 回报新增锚点与待拍板项。典型循环如下：

| 阶段 | 研究者 | Agent |
|---|---|---|
| 分析 | 在服务器或本地运行代码 | 协助编写与解释结果 |
| 记录 | 点名 `agent-execution-log` 或说「记一笔」 | 自动整理字段并写入账本 |
| 判断 | 对关键选择拍板：「这步选 A」 | 给出选项、理由与推荐，不代拍板 |
| 交付 | 在工作台点「生成报告」 | 输出含图、含代码、含技术细节的报告 |

**为什么需要显式点名**：会话结束后没有后台进程继续监听，平台不做静默追记。记录时机由研究者掌握，记录内容由 Agent 自动完成；这既保证账本不混入无关内容，也保证「Agent 带路、决定权在你」。未在会话中点名时，Agent 不会写入账本。

### 让 Agent 认识这个 skill

`make setup` 默认安装到 WorkBuddy 的用户级目录。其它 Agent 指定各自的 skills 目录即可，脚本内容完全相同：

```bash
# WorkBuddy（默认）
make setup

# Claude Code
python3 scripts/install_skill.py --target ~/.claude/skills/agent-execution-log

# 其它支持 skill / rules 的 Agent：把 skill/ 放进对应目录
python3 scripts/install_skill.py --target /path/to/agent/skills/agent-execution-log
```

若所用 Agent 没有 skills 机制，把 `skill/SKILL.md` 作为会话规则或系统提示提供，并让 Agent 调用 `skill/scripts/append_record.py` 即可；该脚本是纯标准库命令行工具，不依赖工作台服务是否运行。

记录器常用命令（字段与工作流详见 `skill/SKILL.md`）：

```bash
S=~/.workbuddy/skills/agent-execution-log/scripts/append_record.py
R=/path/to/your/project

python3 "$S" --root "$R" list                                  # 查看记录与锚点
python3 "$S" --root "$R" append --payload-file p.json         # 追加一条记录
python3 "$S" --root "$R" update --id <锚点> --payload-file p.json  # 按锚点补结果
python3 "$S" --root "$R" decide --decision <决策 id> --choice A    # 填入研究者拍板
```

写盘前自动备份到 `.agent-log/backups/`，写入使用文件锁与原子替换，与工作台界面同时打开不会互相覆盖。`decisions` 中 `choice` 留空即标记为待决定，只有研究者明确拍板后才会写入。

---

## 报告输出

在工作台点击「生成报告」，输出到 `<项目根>/Agent执行记录_报告/`：

| 文件 | 说明 |
|---|---|
| `report.html` | 单文件自包含，图片以 base64 内嵌，可直接打印为 PDF |
| `report.md` | Markdown 版，图片使用相对路径，便于转 Word 或论文附录 |

报告按记录展开，依次包含：结果与内容介绍、指标表、结果图与图注、技术细节、代码全文、关键选择卡、文件出处附录；每条记录带稳定锚点，指着锚点提要求即可让 Agent 准确接手。支持 PNG / JPG / SVG / WEBP 等图片内嵌，PDF 等矢量文件列入附录。

---

## 数据说明

- **示例数据全部为合成数据**：`examples/demo-project/` 中的样本、数值、图与脚本仅用于演示字段与报告结构，不对应任何真实研究对象或研究结果。
- **账本只记路径**：代码全文与图片字节不写入 `ledger.json`，报告生成时从项目目录现场读取。服务器脚本同步下来并修改后，重新生成报告即可，无需改账本。
- **大规模数据不落本地**：计算服务器只登记「别名 + 根目录」作为出处；工作台的「生成同步命令」只产出可复制的 `rsync` 命令，**不执行、不连接服务器**。建议仅同步脚本、图与小型结果表。
- 运行时状态写在 `app/logs/`（直接运行时）或 `~/Library/Application Support/Agent执行记录/logs/`（桌面应用内运行时），均不入库；其中可能包含本机项目路径，请勿公开。

---

## 目录说明

```
app/          本地控制台（纯标准库）
  server.py         HTTP 接口：项目切换、文件扫描、账本读写、报告生成
  report.py         HTML / Markdown 报告生成器
  launcher.py       启动器：端口复用、健康检查、窗口打开
  build_desktop_app.py  自包含 macOS .app 构建器
  web/index.html    单页工作台界面
  assets/make_icon.py  纯标准库图标生成器（无需 Pillow）
skill/        Agent 记录契约
  SKILL.md          触发条件、字段定义、工作流与边界
  scripts/append_record.py  账本追加器（list / show / append / update / decide）
scripts/      install_skill.py：把 skill 安装到任意用户级 skills 目录
examples/     demo-project：合成示例项目（账本、脚本、SVG 图、结果表）
docs/         USAGE.md：详细使用方法与常见问题
Makefile      安装、启动、自检、桌面应用等入口
```

主要接口：`GET /api/health`、`GET /api/state`、`GET /api/ledger`、`GET /api/files`、`GET /api/asset`、`GET /api/handoff`；`POST /api/project`、`POST /api/ledger`、`POST /api/report`、`POST /api/sync-command`、`POST /api/reveal`、`POST /api/new-id`。服务仅绑定 `127.0.0.1`，资源读取限制在项目目录内，拒绝 `..` 与绝对路径。

---

## 免责声明

本工具用于分析过程的记录、复现与报告整理，不执行统计计算，也不对账本中的数值、结论或方法正确性作任何保证。所有示例内容均为合成演示数据，不得引用于真实研究、临床或商业场景。研究者应对自己写入账本的内容与最终报告负责。
