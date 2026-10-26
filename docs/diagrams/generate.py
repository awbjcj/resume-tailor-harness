"""Generate bilingual, manually laid-out diagram HTML; export SVG with the skill helper."""

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAPER, INK, MUTED = "#f6f8fb", "#182026", "#65717c"
ACCENT, TINT, LINK, RULE = "#08708a", "#e6f7fa", "#3867d6", "#cbd2d9"
FONT = "'Geist', 'Microsoft YaHei', 'PingFang SC', sans-serif"
MONO = "'Geist Mono', 'Microsoft YaHei', monospace"


def text(x, y, value, size=12, weight=400, color=INK, mono=False):
    family = MONO if mono else FONT
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{escape(value)}</text>')


def node(x, y, w, h, name, detail, tag, kind="normal"):
    fill = TINT if kind == "focus" else ("#eef4f7" if kind == "store" else "#ffffff")
    stroke = ACCENT if kind == "focus" else RULE
    dash = ' stroke-dasharray="5,4"' if kind == "external" else ""
    shape = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" '
             f'fill="{fill}" stroke="{stroke}"{dash}/>')
    label = text(x + 16, y + 24, tag, 8, color=MUTED, mono=True)
    label += text(x + 16, y + 48, name, 12, 600)
    for i, line in enumerate(detail):
        label += text(x + 16, y + 68 + 16 * i, line, 9, color=MUTED)
    return shape + label


def arrow(path, kind="normal", dashed=False):
    color = LINK if kind == "http" else MUTED
    marker = "arrow-link" if kind == "http" else "arrow"
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    return (f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.5" '
            f'marker-end="url(#{marker})"{dash}/>')


def label(x, y, value, width=104):
    return (f'<rect x="{x}" y="{y}" width="{width}" height="16" fill="{PAPER}"/>'
            + text(x + width / 2, y + 11, value, 8, color=MUTED, mono=True)
            .replace("<text ", '<text text-anchor="middle" ', 1))


def tr(en, zh, chinese):
    return zh if chinese else en


def render(slug, title, desc, body, chinese, note):
    filename = slug + (".zh-CN" if chinese else "")
    title_id = filename + "-title"
    desc_id = filename + "-desc"
    defs = "<defs>"
    for name, color in [("arrow", MUTED), ("arrow-accent", ACCENT), ("arrow-link", LINK)]:
        defs += (f'<marker id="{name}" markerWidth="8" markerHeight="6" refX="7" '
                 f'refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{color}"/></marker>')
    defs += "</defs>"
    legend = f'<line x1="40" y1="664" x2="1240" y2="664" stroke="{RULE}"/>'
    if slug == "agent-workflow":
        legend += text(40, 692, tr("Solid: next check", "实线：进入下一项检查", chinese), 9, color=MUTED)
        legend += text(376, 692, tr("Teal: acceptance checks", "青色：通过条件", chinese), 9, color=ACCENT)
        legend += text(784, 692, tr("Dashed: bounded revision", "虚线：有限次修订", chinese), 9, color=MUTED)
    else:
        legend += text(40, 692, tr("Blue: HTTP / external call", "蓝线：HTTP 或外部调用", chinese), 9, color=LINK)
        legend += text(376, 692, tr("Dashed box: external system", "虚线框：外部系统", chinese), 9, color=MUTED)
        legend += text(784, 692, tr("Teal: application runtime", "青色：应用运行时", chinese), 9, color=ACCENT)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
           f'role="img" aria-labelledby="{title_id} {desc_id}">'
           f'<title id="{title_id}">{escape(title)}</title>'
           f'<desc id="{desc_id}">{escape(desc)}</desc>{defs}'
           f'<rect width="1280" height="720" fill="{PAPER}"/>'
           + text(40, 56, title, 28, 600)
           + text(40, 84, desc, 12, color=MUTED)
           + body + legend + "</svg>")
    html = f'''<!doctype html>
<html lang="{'zh-CN' if chinese else 'en'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600&amp;family=Geist+Mono:wght@400&amp;display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 24px; background: {PAPER}; color: {INK}; font-family: {FONT}; }}
main {{ max-width: 1328px; margin: auto; }}
.diagram-container {{ overflow-x: auto; width: 100%; }}
svg {{ display: block; width: 100%; min-width: 1280px; height: auto; }}
p {{ color: {MUTED}; font-size: 14px; line-height: 1.7; max-width: 80ch; }}
@media print {{ body {{ padding: 0; }} .diagram-container {{ overflow-x: visible; }} svg {{ min-width: 0; }} }}
</style></head><body><main><div class="diagram-container">{svg}</div>
<p>{escape(note)}</p></main></body></html>
'''
    (ROOT / f"{filename}.html").write_text(html, encoding="utf-8")


def context(zh):
    def t(a, b):
        return tr(a, b, zh)
    body = ""
    for path, kind in [
        ("M280 208 H360 Q368 208 368 216 V312 Q368 320 376 320 H448", "http"),
        ("M280 464 H392 Q400 464 400 456 V408 Q400 400 408 400 H448", "http"),
        ("M768 304 H816 Q824 304 824 296 V200 Q824 192 832 192 H1000", "http"),
        ("M768 336 H848 Q856 336 856 328 Q856 320 864 320 H1000", "http"),
        ("M768 368 H880 Q888 368 888 376 V440 Q888 448 896 448 H1000", "http"),
        ("M768 400 H816 Q824 400 824 408 V568 Q824 576 832 576 H1000", "http"),
    ]:
        body += arrow(path, kind)
    body += node(40, 160, 240, 96, t("Job seeker", "求职者"), [t("Approve jobs and evidence", "批准职位与证据"), t("Review documents; track outcomes", "审核文档，记录申请结果")], t("PERSON", "用户"))
    body += node(40, 416, 240, 96, t("External agent + SDK", "外部智能体与 SDK"), ["Codex / Claude Code / pi", t("Prepare forms; confirm before submit", "准备表单，提交前请求确认")], "HTTP CLIENT", "external")
    body += node(448, 272, 320, 176, "Résumé Tailor Harness", [t("Evidence profile and skill-gap analysis", "证据档案与技能缺口分析"), t("Discovery, tailoring, coaching, research", "职位发现、定制、辅导与研究"), t("Application preparation and tracking", "申请准备与进展跟踪")], t("APPLICATION", "应用"), "focus")
    for y, name, info in [
        (144, "GitHub", t("Project evidence and root dossiers", "项目证据与仓库档案")),
        (272, t("Job sources", "职位来源"), t("ATS / boards / pasted postings", "招聘系统、招聘网站与粘贴文本")),
        (400, t("Model providers", "模型服务"), t("Extract, draft, classify, review", "抽取、写作、分类与评审")),
        (528, t("Gmail (optional)", "Gmail（可选）"), t("Mail signals and email drafts", "邮件信号与邮件草稿")),
    ]:
        body += node(1000, y, 240, 96, name, [info], "EXTERNAL", "external")
    render("system-context", t("Job search, evidence, and application preparation", "职位、证据与申请准备"),
           t("The user controls approvals; external agents use the authenticated API.", "用户决定批准哪些操作；外部智能体通过认证后的 API 获取资料。"), body, zh,
           t("Overview: optional identity, billing, web search, mail delivery, and H-1B integrations are not expanded. The SDK does not control an external browser.", "图中省略身份认证、计费、网页搜索、邮件发送和 H-1B 等可选集成的细节。SDK 不控制外部浏览器。"))


def architecture(zh):
    def t(a, b):
        return tr(a, b, zh)
    body = '<rect x="448" y="120" width="384" height="464" rx="8" fill="#eef4f7" stroke="#cbd2d9"/>'
    body += text(464, 144, t("ONE PYTHON PROCESS · INTERNAL COMPONENTS", "单个 PYTHON 进程 · 内部组件"), 8, color=MUTED, mono=True)
    for path, kind in [
        ("M280 208 H480", "http"),
        ("M640 288 V400", "normal"),
        ("M280 496 H480", "normal"),
        ("M800 192 H928 Q936 192 936 184 V168 Q936 160 944 160 H1000", "http"),
        ("M800 248 H872 Q880 248 880 256 V296 Q880 304 888 304 H1000", "normal"),
        ("M800 448 H1000", "normal"),
        ("M800 512 H888 Q896 512 896 520 V584 Q896 592 904 592 H1000", "normal"),
    ]:
        body += arrow(path, kind)
    body += label(648, 332, t("DISPATCH", "任务调度"), 88)
    body += node(40, 160, 240, 96, t("Web app / Python SDK", "网页应用 / Python SDK"), ["React / TypeScript / HTTP", t("Commands, queries, run progress", "操作、查询与运行进度")], "CLIENT")
    body += node(40, 448, 240, 96, t("Standalone CLI", "独立命令行"), ["Python / Typer", t("Calls shared services directly", "直接调用共享业务服务")], "LOCAL PROCESS")
    body += node(480, 160, 320, 128, t("API + background runs", "API 与后台运行"), ["FastAPI / in-process thread pools", t("Auth, context, JSON, SSE event log", "认证、上下文、JSON 与 SSE 日志")], "RUNTIME", "focus")
    body += node(480, 400, 320, 144, t("Shared use-case services", "共享业务服务"), [t("Agents, review gates, taxonomy", "智能体、评审校验与技能分类"), t("Profile, tracking, Typst rendering", "档案、申请跟踪与 Typst 渲染")], "INTERNAL CODE")
    for y, name, info, kind in [
        (112, t("Integrations", "外部集成"), t("Providers, sources, research, Gmail", "模型、职位来源、研究与 Gmail"), "external"),
        (256, t("Platform database", "平台数据库"), t("Accounts, budgets, usage · system.db", "账号、预算与用量 · system.db"), "store"),
        (400, t("Workspace database", "工作区数据库"), t("Jobs, versions, applications, events", "职位、文档版本、申请与事件"), "store"),
        (544, t("Workspace files", "工作区文件"), t("Facts, corpus, PDFs, config, run logs", "事实、语料、PDF、配置与运行日志"), "store"),
    ]:
        body += node(1000, y, 240, 96, name, [info], "HTTPS" if kind == "external" else "SQLITE" if y != 544 else "FILESYSTEM", kind)
    render("system-architecture", t("One application, shared services, scoped data", "单体应用、共享服务与工作区数据"),
           t("Background runs are threads; agent tasks and review gates remain internal code.", "后台任务在线程中执行；智能体和评审规则属于应用内部代码。"), body, zh,
           t("Selected relationships: the API streams SSE to the browser; the CLI also accesses integrations and files. The shaded process group is not a network isolation boundary. Hosted users have separate workspace databases and files.", "图中只画主要关系：API 向浏览器推送 SSE，CLI 也会访问外部集成和文件。阴影区域表示进程内组件，不代表网络隔离。托管用户拥有各自的工作区数据库和文件。"))


def workflow(zh):
    def t(a, b):
        return tr(a, b, zh)
    body = ""
    for path, dashed in [
        ("M280 192 H432", False),
        ("M280 448 H344 Q352 448 352 440 V232 Q352 224 360 224 H432", False),
        ("M592 240 V304", False),
        ("M592 400 V464", False),
        ("M752 352 H1000", True),
        ("M752 496 H904 Q912 496 912 488 V376 Q912 368 920 368 H1000", True),
        ("M1120 304 V112 Q1120 104 1112 104 H600 Q592 104 592 112 V144", True),
        ("M752 528 H1000", False),
    ]:
        body += arrow(path, dashed=dashed)
    body += label(824, 328, t("FAIL / REVISE", "失败后修订"), 104)
    body += label(920, 424, t("FAIL", "失败"), 64)
    body += label(832, 504, t("PASS", "通过"), 88)
    body += node(40, 144, 240, 96, t("Profile evidence + JD", "档案证据与职位描述"), [t("Cited facts; JD is untrusted input", "引用档案事实；职位文本不可信")], "INPUT")
    body += node(40, 400, 240, 96, t("Verified skill procedure", "已验证的技能文件"), ["skills-lock.json / SHA-256", t("One capability; confined path", "单个能力，路径限制在根目录内")], "REGISTRY")
    body += node(432, 144, 320, 96, t("Writer / revised draft", "写作与修订草稿"), [t("Scoped facts and one task procedure", "使用限定范围的事实与任务技能")], "AGENT")
    body += node(432, 304, 320, 96, t("Deterministic gates", "程序校验"), ["provenance / skill-naming / numeric-evidence"], "IN PROCESS", "focus")
    body += node(432, 464, 320, 96, t("Fact-check + advisory panel", "事实核验与建议类评审"), [t("Fact-check blocks; scores cannot override", "事实核验失败即拦截，评分不能抵消")], "MODEL REVIEW", "focus")
    body += node(1000, 304, 240, 96, t("Bounded revision", "有限次修订"), [t("Round and retry budgets apply", "受质量轮次与重试预算限制")], "AGENT")
    body += node(1000, 464, 240, 96, t("Accepted version / PDF", "已通过版本与 PDF"), [t("Render and select separately", "渲染与附件选择分别执行")], "ARTIFACT", "store")
    body += text(432, 608, t("Rejected internal attempts remain in history; external submission saves only accepted drafts.", "内部未通过的尝试仍保留历史；外部提交只保存通过评审的草稿。"), 12, color=MUTED)
    render("agent-workflow", t("Evidence before drafting; verification before acceptance", "先有证据，再起草；通过核验，才接受"),
           t("Resume review flow; cover letters and career conversations have different gates.", "本图展示简历评审；求职信和职业对话使用各自的校验规则。"), body, zh,
           t("Simplified review flow: verdict aggregation also applies configured score thresholds. A retry is bounded and does not promise eventual approval. Cover letters use provenance checks without this panel; Career Lab stays draft-only.", "图中省略评分阈值等细节，最终结论由统一判定函数给出。重试次数有限，不保证最终通过。求职信不使用此评审团；Career Lab 只生成草稿。"))


if __name__ == "__main__":
    for chinese in (False, True):
        context(chinese)
        architecture(chinese)
        workflow(chinese)
