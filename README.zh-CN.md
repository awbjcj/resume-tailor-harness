# Résumé Tailor Harness

[![CI](https://github.com/awbjcj/resume-tailor-harness/actions/workflows/ci-main.yml/badge.svg)](https://github.com/awbjcj/resume-tailor-harness/actions/workflows/ci-main.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)

[English](README.md) | 简体中文

Résumé Tailor Harness 覆盖完整的求职流程。它从招聘网站连接器、LinkedIn 或手动输入中获取职位，根据真实经历进行匹配评分，定制简历和求职信，将材料渲染为 PDF，并在工作区级 SQLite 数据库中跟踪申请进度。你可以将它作为命令行工具、本地网页应用或多用户托管服务使用。

**事实锁定（fact-lock）**要求定制简历中的每一条陈述都能追溯到用户提供的真实事实。智能体可以起草、改写和评审。确定性的控制流闸门决定哪些内容可以进入已保存的文档。具体机制见下方[框架设计](#框架设计)。

> 本文档中的命令、配置键、API 路径和状态值保持英文，以便与程序界面和源码一致。

---

## 框架设计

本仓库由六项机制组成，让开放式写作任务更可信、更可复现，也更容易控制成本。

### 1. 事实锁定让每条表述有据可查

用户的简历和代码仓库会被抽取为**封闭 schema** 的证据档案（`data/profile/facts.json`）：每条事实都带有 id，抽取 schema 会拒绝未定义的字段，因此项目类来源无法悄悄产出任职经历或教育背景。

随后每一轮定制都要经过**三道确定性闸门**，全部在进程内判定，不涉及任何模型：

| 闸门               | 在以下情况拦截该轮结果           |
| ------------------ | -------------------------------- |
| `provenance`       | 引用的事实 id 无法对应到真实事实 |
| `skill-naming`     | 声称了档案中并未确立的技能       |
| `numeric-evidence` | 给出了证据无法支撑的数字         |

这三个名称是**保留名**。把评审员配置成其中任意一个会直接导致启动报错，因此修改评审名单无法架空闸门。闸门与模型评审意见会汇入唯一的判定构造函数（`tailor/verdict.py::aggregate`），使"这一轮算不算通过"只有一个定义。任何一道闸门未通过，无论评分多高都会拦截该轮。

求职信同样由确定性的 provenance 闸门把关，不使用评审团。

### 2. 技能集中式定制（skill-concentrated tailoring）

每个任务智能体都属于一个稳定的**智能体族（agent family）**，例如职位分析、简历撰写、简历评审、求职信、面试、Career Lab、内部档案或担保研究。每个智能体使用**恰好一个**已核准的执行程序。

这些程序是本地 `SKILL.md` 文件，由根目录受限、**SHA-256 校验**的注册表（`career_skills/registry.py`）依据 `skills-lock.json` 中的锁定清单解析。模型不选择路径，只报出能力名称；注册表返回唯一且不可变的 `SkillRef`（名称、版本、摘要、族）。若文件被修改、被替换为符号链接，或指向技能根目录之外，该能力会被**停用**。系统不会加载被篡改的文本。解析出的 `SkillRef` 会随它影响过的每一件产物和每一轮对话一并持久化，因此任何输出都能回溯到产生它的那份程序的确切字节。

### 3. 受限的只读工具循环

Source Scout、Profile Coach、担保研究和 Career Lab 在循环内只使用**只读**工具，例如检索、探测和查看。确定性服务会在循环结束后写入数据，并要求用户批准。工具"验证过"的结论会在呈现前再次校验。Scout 只*提议*来源；Coach 只*起草*笔记，由用户编辑后保存；Career Lab 只产生草稿，无法投递、上传、发送或更新用户档案。

### 4. 最小权限提示（least-privilege prompting）

评审员看到的上下文按权限划分：

- **闸门评审员**只看到草稿、职位描述，以及*该草稿实际引用到的那些档案事实*。
- **建议类评审员**（文风、影响力、排版）完全看不到原始档案。
- 每一份第三方职位描述都会被包进明确的"不可信内容"分隔标记，因此 JD 中夹带的"忽略你的指令"只是数据，不是策略。
- 声称了错误评审员身份的评审结果会被拒绝。合并式建议评审团必须完整覆盖其配置名单，不允许遗漏或重复。

### 5. 用控制流表达成本控制

评审团是最昂贵的环节，因此框架会控制这部分成本：

- 可机械证明的闸门在付费评审团**之前**计算，因此引用错误会在产生的那一轮交给修订者处理，无需再执行一轮昂贵的 fact-check。
- **仅**因 provenance 失败的一轮可获得一次**免费重试**，不占用 `max_rounds` 的质量轮次。
- 每次修订都以**评分最高且闸门全过的那一轮**为基础，因此一次糟糕的修订不会成为下一轮的基线。
- 评分出现回退时，循环会提前结束，避免再执行一轮付费评审。
- 三个模型档位（`CHEAP_MODEL`、`MID_MODEL`、`PREMIUM_MODEL`）各自带**提供商前缀**。廉价抽取可以跑在 Gemini 上，撰写者仍留在 Claude，未使用的提供商 SDK 不会被导入。

### 6. 持久化的运行与数据保管

耗时操作以后台**运行（run）**的形式执行，并带有持久事件日志：SSE 流可恢复、取消是协作式的、终态结果会写入幂等的历史记录，因此浏览器断连不会抹掉结果。在托管模式下，每个用户拥有独立工作区，其中包含各自的数据库、语料、密钥与渲染产物。所有受用户影响的对外请求都经过抗 DNS 重绑定的出网网关，它会校验每一次重定向并锁定已校验的地址。

---

## 工作流程

职位会依次经过获取、筛选、人工批准、定制和申请跟踪。需要花费较高模型成本或改变持久状态的关键节点由用户决定。

```text
              ┌─ pull ───┐
  连接器      │          │
  LinkedIn    │  scrape  │
  手动输入    └─ addjob ─┘
                   │
                   ▼
   raw ─▶ extracted ─▶ filtered ─▶ shortlisted ─▶ approved ─▶ tailored ─▶ rendered
                          │            ▲   │           ▲           │
                       rejected     discover       用户批准    cover-letter

   申请状态：ready ─▶ submitted ─▶ interview ─▶ offer / rejected / closed
                                        ▲
                                sync-status 提议 Gmail 状态变更
```

| 阶段       | 命令或入口                   | 作用                                                                         |
| ---------- | ---------------------------- | ---------------------------------------------------------------------------- |
| 获取职位   | `pull` / `scrape` / `addjob` | 从已启用的招聘来源、LinkedIn 或手动输入中写入职位，并按 URL 或职位描述去重。 |
| 发现与评分 | `discover`                   | 提取结构化职位要求，应用硬性筛选条件，并计算匹配度。                         |
| 人工批准   | 网页界面或 `approve`         | 只批准值得进入定制流程的职位。                                               |
| 定制简历   | `tailor`                     | 由写作智能体起草、评审面板批注，并循环修订到通过事实门禁。                   |
| 求职信     | `cover-letter`               | 根据事实锁定资料生成求职信，并进行确定性的来源校验。                         |
| PDF 渲染   | `render`                     | 使用 Typst 将指定版本渲染为 PDF。                                            |
| 申请跟踪   | 网页界面或 `sync-status`     | 记录申请事件、结果、复盘和薪酬信息；Gmail 只提出状态变更建议，不会静默修改。 |

## 求职工具

下列工具共享同一份事实锁定档案、已校验的技能注册表、只读工具循环和持久运行历史。它们帮助你处理求职中反复出现的工作：

| 工具                | 如何帮助                                                                 |
| ------------------- | ------------------------------------------------------------------------ |
| **Profile Coach**   | 补充你尚未写下的经历证据。它会逐个提问，只根据你的回答起草。            |
| **Mock Interviews** | 针对具体的已定制职位练习，并提供带评分的复盘。                          |
| **Career Lab**      | 支持谈薪准备、转行和作品集撰写。每轮使用一个已校验技能，所有输出都是草稿。 |
| **Match-gap**       | 按需求程度排列目标职位需要、但你的资料尚未体现的技能。                  |
| **担保证据**        | 将历史备案作为研究信号，不承诺当前是否提供赞助。                        |
| **公司研究**        | 在你发起请求时生成带引用的雇主简报。                                    |
| **申请时间线**      | 将轮次、结果和截止日期汇入一份数据集，可导出为 CSV 或日历。             |
| **Gmail 同步**      | 读取收件箱，并提出由你确认的状态变更建议。                              |
| **Analytics**       | 显示哪些来源和匹配分档更可能进入后续阶段。                              |

### 职位看板

- **Triage** (`/triage`)：处理尚未筛选或已拒绝的职位。
- **Shortlist** (`/shortlist`)：查看评分结果并决定是否批准定制。
- **Pipeline** (`/pipeline`)：查看已批准、定制和渲染中的职位。
- Triage、Shortlist 和 Pipeline 都可以把当前筛选条件保存为命名视图。

### 事实锁定资料与申请材料

- 从简历、补充材料和可选的 GitHub 项目构建 `data/profile/facts.json`。
- 定制简历中的项目、经历和技能必须携带可验证的来源标识。
- 事实检查和确定性来源门禁会阻止不受支持的陈述。
- 简历和求职信都可以保留多个版本，并通过 Typst 渲染为 PDF。

### 职业辅导

- **Profile Coach** (`/coach`)：逐个发现资料中的证据缺口，只根据用户回答起草新事实。
- **Mock Interviews** (`/interview`)：针对具体职位进行模拟面试，并生成评分复盘。
- **Career Lab** (`/career-lab`)：一次调用一个经过校验的本地职业技能；输出始终是草稿，不能替用户申请、上传或发送内容。

```bash
uv run resume-tailor-harness career-lab "准备薪酬谈判要点" \
  --skill salary-negotiation-prep --offer-application-id 7
```

### 申请时间线与复盘

每个职位的 **Tracking** 页签可以记录提交申请、招聘人员初筛、在线测评、技术面试、系统设计、行为面试、终面、offer、拒绝、撤回和自定义事件。事件可以包含时间、时区、形式、面试官、结果、笔记、复盘和薪酬明细。

**Applications** 页面 (`/applications`) 使用统一的数据集展示所有申请，支持搜索、排序、重复技术轮次展示，以及两种 CSV 导出：

- 宽表：便于人工阅读和横向比较。
- 事件明细表：无损保留每一个申请事件。

**Analytics** 页面 (`/analytics`) 使用同一份数据计算阶段流转、周期时间、当前申请时间线和 offer 对比。单个事件或全部即将发生的事件也可以下载为 `.ics` 日历文件。

### 公司研究与 H-1B 证据

职位详情中的 **Research** 页签将两类证据明确分开：

- **Company intelligence**：用户主动触发的公司研究，覆盖战略、近期动态、工程文化、挑战和竞争位置。只有研究结果中真实出现的来源 URL 和引用才能通过校验；刷新失败时保留上一份有效资料，过期内容会标记为陈旧但不会自动刷新。
- **Sponsorship**：可选的历史 H-1B 申报数据。历史申报不能证明当前职位提供赞助，也不会自动拒绝职位。

启用 H-1B MCP 集成时，只允许三个只读工具：`h1b_get_company_stats`、`h1b_search_h1b_jobs` 和 `h1b_get_available_data`。详细配置见 [环境变量参考](docs/configuration.md)。

### 运行历史和仪表盘

- 通知菜单持久保存后台任务的成功、失败和取消结果；即使浏览器断线，终态也不会丢失。
- Dashboard 展示工作队列、模拟面试分数趋势和职位来源故障。
- 长任务仍可通过 Server-Sent Events 实时显示进度，持久运行历史负责最终一致性。

---

## 前置要求

选择一种安装方式：

- 容器运行需要 Docker Engine 和 Docker Compose 插件。Docker Desktop 已包含两者。
- 原生开发需要 [uv](https://docs.astral.sh/uv/) 与 Node.js 22+（含 npm）。项目使用 Python 3.13+。

AI 功能需要至少一个模型提供商密钥。发现、定制和求职信步骤默认使用 Anthropic，也支持 OpenAI、Google Gemini 和 DeepSeek。没有密钥也可以启动应用，然后在网页界面中完成配置。

可选集成：

- GitHub token 可提高仓库资料获取的速率限制。
- LinkedIn 专用账号仅用于 `scrape`。
- Adzuna 等职位来源凭据用于对应连接器。
- Gmail OAuth 用于状态同步、提醒和邮件草稿。

## 使用 Docker 启动

Docker 会将网页和 API 构建进同一个镜像，将应用数据保存在具名卷中，并且只绑定到这台计算机的回环地址。

### 先配置一次

复制安全模板，然后按需填写模型提供商密钥（例如 `ANTHROPIC_API_KEY`）。没有密钥也可以启动，再从网页 UI 完成配置。

```powershell
Copy-Item .env.example .env
notepad .env
```

如果 `8000` 被占用，可设置 `RESUME_TAILOR_HARNESS_PORT`。`.env` 不会进入镜像。使用随附 H-1B 服务时，不要在 `.env` 中手动启用 H-1B 变量；可选 Compose 栈会在运行时注入私有服务地址。

### 启动默认应用

```bash
docker compose up --build
```

容器会把已构建的网页和 API 一起提供在 <http://localhost:8000>。按 `Ctrl+C` 停止，以后用 `docker compose up` 重启。`docker compose down` 会删除容器和网络，但保留具名数据卷。只有明确要清除本地应用和 H-1B 缓存数据时，才使用 `docker compose down --volumes`。

镜像默认关闭浏览器型连接器；需要 LinkedIn 或其他浏览器驱动的来源时，请使用原生安装方式。

### 同时启动可选 H-1B 服务

仓库将配套服务固定为 Git 子模块，并使用其冻结依赖锁构建，所以组合栈使用的是已知的源代码版本。克隆时使用 `--recurse-submodules`，或在现有克隆中执行一次：

```bash
git submodule update --init --recursive
docker compose -f compose.yaml -f compose.h1b.yaml --profile h1b up --build
```

该命令会同时启动应用和 H-1B MCP 服务。MCP 端点只存在于 Docker 私有网络中；浏览器仍然只访问 <http://localhost:8000>。两个服务的数据卷在正常停止和重启后都会保留。历史 H-1B 记录只是辅助证据，不能证明公司当前提供赞助。

### Windows 快速启动

安装并启动 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)（默认 WSL 2 后端适合大多数用户），然后在 PowerShell 中确认：

```powershell
docker version
docker compose version
```

只有计划使用 `-WithH1B` 时才需要安装 Git for Windows，因为该模式会在第一次运行时初始化固定版本的服务子模块。

随附的 PowerShell 启动器会创建缺失的 `.env`、检查 Docker Desktop、按需初始化 H-1B 子模块，并在停止时保留数据：

```powershell
.\scripts\windows\Start-ResumeTailor.cmd -Detach
.\scripts\windows\Start-ResumeTailor.cmd -WithH1B -Detach
.\scripts\windows\Start-ResumeTailor.cmd -WithH1B -Status
.\scripts\windows\Start-ResumeTailor.cmd -WithH1B -Stop
```

`-WithH1B` 是可选项；省略它即可使用较小的默认栈。端口冲突时可在任一启动命令后加 `-Port 8080`。`.cmd` 启动器只会在其子 PowerShell 进程中临时绕过执行策略；也可以在已配置的 shell 中直接调用 `.ps1` 文件。

也可以直接构建并运行镜像：

```bash
docker build -t resume-tailor-harness .
docker run --name resume-tailor-harness --init --restart unless-stopped \
  -e APP_MODE=local \
  -p 127.0.0.1:8000:8000 \
  -v resume-tailor-harness-data:/app/data \
  resume-tailor-harness
```

如需在启动时注入模型密钥，请在创建 `.env` 后添加 `--env-file .env`。

生产部署见 [Railway 部署说明](docs/deploy-railway.md)。

## 原生安装

```bash
uv run --no-project scripts/bootstrap.py
uv run resume-tailor-harness setup
uv run python scripts/dev.py
```

第一条命令会以幂等方式安装锁定的 Python 和前端依赖；只有需要浏览器型职位来源时才传入 `--browser`。`resume-tailor-harness setup` 会引导配置密钥、搜索条件和职位连接器，并写入 `.env` 与 `config/*.yaml`。也可以从仓库中的 `.example` 文件手动创建配置。

开发脚本会同时启动 API 和 Vite，默认网页地址为 `http://localhost:5173`。如果已安装 `make`，也可以使用 `make setup` 和 `make dev`。

---

## 快速开始

```bash
# 1. 根据简历和可选 GitHub 来源构建事实锁定资料
uv run resume-tailor-harness profile build

# 2. 导入职位（三选一）
uv run resume-tailor-harness pull --limit 10
uv run resume-tailor-harness scrape --limit 10
uv run resume-tailor-harness addjob --company "Acme" --title "Backend Engineer" --jd-file jd.txt

# 3. 提取要求、筛选并评分
uv run resume-tailor-harness discover
uv run resume-tailor-harness match-gap

# 4. 在网页 Shortlist 页面中批准职位
make dev

# 5. 定制所有已批准的职位并生成求职信
uv run resume-tailor-harness tailor --approved
uv run resume-tailor-harness cover-letter --approved

# 6. 将指定简历版本渲染为 PDF
uv run resume-tailor-harness render 12

# 7. 在网页 Tracking 页签中记录申请事件

# 8. 可选：读取 Gmail 并提出状态变更建议
uv run resume-tailor-harness sync-status
uv run resume-tailor-harness sync-status --apply
```

## 常用命令

| 命令                                      | 说明                                     |
| ----------------------------------------- | ---------------------------------------- |
| `resume-tailor-harness setup`             | 交互式创建本地配置。                     |
| `resume-tailor-harness profile build`     | 从配置的来源构建事实锁定资料。           |
| `resume-tailor-harness addjob`            | 手动添加一个职位。                       |
| `resume-tailor-harness pull`              | 运行所有已启用的职位连接器。             |
| `resume-tailor-harness scrape`            | 使用本地浏览器获取 LinkedIn 职位。       |
| `resume-tailor-harness sources`           | 查看职位来源和连接器运行历史。           |
| `resume-tailor-harness discover`          | 提取职位要求、应用筛选条件并评分；将符合条件的职位移至 `shortlisted`。 |
| `resume-tailor-harness match-gap`         | 查看目标职位需要但资料中缺乏证据的技能。 |
| `resume-tailor-harness approve JOB_ID`    | 从命令行批准职位。                       |
| `resume-tailor-harness tailor`            | 生成并评审事实锁定简历。                 |
| `resume-tailor-harness cover-letter`      | 生成经过来源校验的求职信。               |
| `resume-tailor-harness render VERSION_ID` | 将简历版本渲染为 PDF。                   |
| `resume-tailor-harness sync-status`       | 从 Gmail 生成申请状态建议。              |
| `resume-tailor-harness career-lab`        | 使用一个已校验的职业技能创建草稿。       |
| `resume-tailor-harness serve`             | 启动 API 和已构建的网页应用。            |

完整参数与示例见 [英文命令参考](README.md#command-reference)。

---

## 多用户托管模式

`resume-tailor-harness serve` 默认是无需登录的本地应用，只绑定回环地址。要公开服务或启用多用户模式，请设置管理员凭据并显式启动 hosted 模式：

```bash
uv run resume-tailor-harness serve --mode hosted --host 0.0.0.0 --port 8080
```

```env
AUTH_USERNAME=owner
AUTH_PASSWORD_HASH=<uv run resume-tailor-harness hash-password 的输出>
SESSION_SECRET=<足够长的随机值>
APP_BASE_URL=https://your-domain.example
```

每个用户都有独立的数据库、资料库、配置、密钥、输出文件和运行历史。管理员可以管理注册模式和邀请，以及模型费率、美元成本额度、积分、活跃职位上限和并发任务上限。

生产环境还应配置 `ALLOWED_HOSTS`、安全 Cookie、API 文档开关和持久化卷。完整要求见：

- [Railway 部署说明](docs/deploy-railway.md)
- [成本额度说明](docs/cost-quotas.md)
- [环境变量参考](docs/configuration.md)

## Gmail 配置

Gmail 集成只会读取邮件和创建草稿，不会发送邮件。

- **本地 CLI**：在 Google Cloud 创建 Desktop app OAuth 客户端，将下载的 JSON 保存为 `config/gmail_credentials.json`。
- **网页/API**：创建 Web application OAuth 客户端，将回调地址设置为 `<域名>/api/gmail/callback`，并配置 `GOOGLE_OAUTH_CLIENT_ID` 与 `GOOGLE_OAUTH_CLIENT_SECRET`。
- 在网页 **Settings → Keys** 中连接 Gmail。授权 token 按工作区独立保存。

如果 OAuth 同意屏幕仍处于 Testing 状态，需要在 Google Cloud 中把每一个测试邮箱加入允许列表。

---

## API

```bash
uv run resume-tailor-harness serve
uv run resume-tailor-harness serve --mode hosted --host 0.0.0.0 --port 8080
```

- 本地交互式文档：`/docs`
- OpenAPI：`/openapi.json`
- 已提交的契约：`contracts/openapi.json`
- TypeScript 客户端：`contracts/ts/api.ts`
- 后台任务进度：`GET /api/runs/{id}` 和 `GET /api/runs/{id}/events`
- 持久运行终态：`GET /api/run-completions`
- 申请事件：`/api/jobs/{job_id}/events`
- 跨职位申请表：`/api/applications`
- 命名看板视图：`/api/board-views`
- 公司研究刷新：`POST /api/jobs/{job_id}/company-intelligence/refreshes`

API schema 发生变化后，运行 `bash scripts/gen_ts_client.sh` 更新前端客户端。

## 配置

复制 `.env.example` 为 `.env`。环境变量用于密钥、模型、认证、配额和外部集成；YAML 文件用于搜索、连接器、评审和渲染策略。

| 文件                          | 作用                                         |
| ----------------------------- | -------------------------------------------- |
| `.env`                        | 模型密钥、服务模式、认证、Gmail 和外部集成。 |
| `config/search.yaml`          | 地点、关键词、排除条件和其他搜索偏好。       |
| `config/connectors.yaml`      | 职位来源、招聘网站和每个来源的限制。         |
| `config/profile_sources.yaml` | 简历、补充材料和 GitHub 资料来源。           |
| `config/review.yaml`          | 默认快速评审流程。                           |
| `config/review_deep.yaml`     | 更完整的深度评审流程。                       |
| `config/render.yaml`          | Typst 模板和渲染设置。                       |

模型 ID 可以带提供商前缀：

```env
CHEAP_MODEL=gemini:gemini-3.5-flash-lite
MID_MODEL=deepseek:deepseek-v4-flash
PREMIUM_MODEL=claude-opus-5
```

不带前缀的模型 ID 使用 Anthropic；`openai:`、`gemini:` 和 `deepseek:` 分别路由到对应提供商。只需要配置实际使用的提供商密钥。

完整变量、边界和部署默认值见 [环境变量参考](docs/configuration.md)。

## 数据位置

| 路径                            | 内容                                           |
| ------------------------------- | ---------------------------------------------- |
| `data/resume_tailor_harness.db` | 本地模式下的职位、简历版本、求职信和申请记录。 |
| `data/profile/facts.json`       | 事实锁定资料。                                 |
| `data/connector_runs.json`      | 连接器运行历史。                               |
| `data/gmail_token.json`         | 本地 CLI 使用的 Gmail OAuth token。            |
| `output/`                       | 渲染后的简历和求职信 PDF。                     |
| `.linkedin_profile/`            | 本地 LinkedIn 浏览器会话。                     |
| `templates/`                    | Typst 简历与求职信模板。                       |

托管模式下，每个用户的数据位于独立工作区中。工作区导出和平台级数据根导出属于敏感资料，因为其中可能包含运行所需的密钥。

## 负责任地使用抓取功能

`scrape` 只适合个人、低频使用。请使用专用 LinkedIn 账号，保持较小的 `--limit`，并遵守目标网站的条款和适用法律。若不希望运行浏览器自动化，可以始终使用 `addjob` 或 URL 导入。

## 开发

```bash
uv run pytest
uv run pytest -k scraper
uv run ruff check .

cd web
npm run test:run
npm run lint
npm run build
```

后端测试使用假的智能体、浏览器和固定响应数据，正常情况下不需要模型密钥或网络访问。提交 API 契约变更时还应检查生成的 OpenAPI 和 TypeScript 客户端是否同步。

## 参与贡献

欢迎贡献。请阅读 [贡献指南](.github/CONTRIBUTING.md)，从 `dev` 创建分支，并向 `dev` 提交 Pull Request。提交前请运行与改动相关的测试和 `make verify`。

## 安全

请根据 [安全策略](.github/SECURITY.md) 私下报告漏洞，不要创建公开 issue。

仓库还包含以下安全文档：

- [威胁模型](docs/resume-tailor-harness-threat-model.md)
- [安全最佳实践报告](docs/security_best_practices_report.md)
- [ADR-0008：出口网关、租户存储和规范来源](docs/adr/0008-egress-gateway-tenant-storage-canonical-origin.md)

## 许可证

[MIT](LICENSE) © awbjcj
