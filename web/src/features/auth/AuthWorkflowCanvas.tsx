import { FileCheck2, FileText, GitBranch, ScanLine, ShieldCheck, UserRoundCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

// An illustrative workflow, deliberately separate from live run/status UI.
// Native SVG keeps the expanded canvas crisp without a rendering dependency.
export function AuthWorkflowCanvas() {
  const { t } = useTranslation();
  const nodes = [
    { x: 74, y: 518, icon: FileText, label: t("auth.workflow.sources"), detail: t("auth.workflow.sourcesDetail"), index: "01" },
    { x: 338, y: 652, icon: ScanLine, label: t("auth.workflow.evidence"), detail: t("auth.workflow.evidenceDetail"), index: "02" },
    { x: 606, y: 518, icon: GitBranch, label: t("auth.workflow.tailoring"), detail: t("auth.workflow.tailoringDetail"), index: "03" },
    { x: 874, y: 716, icon: ShieldCheck, label: t("auth.workflow.review"), detail: t("auth.workflow.reviewDetail"), index: "04" },
    { x: 1142, y: 598, icon: UserRoundCheck, label: t("auth.workflow.approval"), detail: t("auth.workflow.approvalDetail"), index: "05" },
    { x: 1410, y: 396, icon: FileCheck2, label: t("auth.workflow.output"), detail: t("auth.workflow.outputDetail"), index: "06" },
  ];
  return (
    <div className="auth-canvas" data-slot="auth-brand" aria-hidden="true">
      <div className="auth-canvas-grid" />
      <svg className="auth-workflow" data-slot="auth-brand-visual" viewBox="0 0 1600 1000" fill="none" focusable="false">
        <g className="auth-workflow-traces">
          <path d="M-120 570H74 M290 570H310Q324 570 324 584V690Q324 704 338 704 M554 704H570Q590 704 590 684V590Q590 570 606 570 M822 570H840Q856 570 856 590V748Q856 768 874 768 M1090 768H1108Q1126 768 1126 750V670Q1126 650 1142 650 M1358 650H1374Q1394 650 1394 630V468Q1394 448 1410 448 M1626 448H1730" />
          <path className="auth-workflow-return" d="M982 820V868Q982 888 962 888H466Q446 888 446 868V756" />
          <path className="auth-workflow-branch" d="M714 518V462Q714 444 732 444H852 M182 518V444Q182 426 164 426H-50 M1250 598V230Q1250 210 1270 210H1680" />
        </g>
        <g className="auth-workflow-junctions">
          <circle cx="324" cy="637" r="4" /><circle cx="590" cy="634" r="4" />
          <circle cx="856" cy="670" r="4" /><circle cx="1126" cy="708" r="4" />
          <circle cx="1394" cy="546" r="4" /><circle cx="714" cy="444" r="4" />
        </g>
        {nodes.map(({ x, y, icon: Icon, label, detail, index }) => (
          <g key={index} transform={`translate(${x} ${y})`} className={`auth-workflow-node${index === "03" ? " auth-workflow-node-core" : ""}`}>
            <rect className="auth-node-surface" width="216" height="104" rx="12" />
            <rect className="auth-node-icon-surface" x="16" y="16" width="32" height="32" rx="8" />
            <Icon x="23" y="23" width="18" height="18" className="auth-node-icon" />
            <text x="196" y="35" textAnchor="end" className="auth-node-index">{index}</text>
            <text x="16" y="70" className="auth-node-title">{label}</text>
            <text x="16" y="89" className="auth-node-detail">{detail}</text>
            <circle cx="0" cy="52" r="3" className="auth-node-port" />
            <circle cx="216" cy="52" r="3" className="auth-node-port" />
          </g>
        ))}
      </svg>
      <div className="auth-canvas-vignette" />
    </div>
  );
}
