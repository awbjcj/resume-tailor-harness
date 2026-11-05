"use client";

import { useId, type ComponentProps, type ReactNode } from "react";

const classes = (...values: (string | undefined)[]) => values.filter(Boolean).join(" ");

export type Theme = "light" | "dark" | "system" | "gateway";
export type Tone = "success" | "warning" | "danger" | "info" | "stage-1" | "stage-2" | "stage-3" | "stage-4" | "stage-5" | "stage-6";
export type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "outline" | "secondary" | "ghost" | "danger" | "link";
  size?: "sm" | "md" | "lg" | "icon";
  loading?: boolean;
  loadingLabel?: string;
};

export function Button({ variant = "primary", size = "md", loading = false, loadingLabel, disabled, className, type = "button", children, ...props }: ButtonProps) {
  return (
    <button {...props} type={type} className={classes("ti-button", className)} data-variant={variant === "primary" ? undefined : variant} data-size={size} disabled={disabled || loading} aria-busy={loading || undefined}>
      {loading ? <span className="ti-spinner" aria-hidden="true" /> : null}
      {loading && loadingLabel ? loadingLabel : children}
    </button>
  );
}

export type TextFieldProps = ComponentProps<"input"> & {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
  fieldClassName?: string;
};

export function TextField({ label, hint, error, id, className, fieldClassName, "aria-describedby": describedBy, "aria-invalid": invalid, ...props }: TextFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const descriptions = [...new Set([describedBy, hintId, errorId].filter(Boolean))].join(" ") || undefined;
  return (
    <div className={classes("ti-field", fieldClassName)}>
      <label className="ti-label" htmlFor={inputId}>{label}{props.required ? <span aria-hidden="true"> *</span> : null}</label>
      <input {...props} id={inputId} className={classes("ti-input", className)} aria-describedby={descriptions} aria-invalid={error ? true : invalid} />
      {hint ? <p className="ti-hint" id={hintId}>{hint}</p> : null}
      {error ? <p className="ti-error" id={errorId}>{error}</p> : null}
    </div>
  );
}

export function ThemeBoundary({ theme = "system", className, ...props }: ComponentProps<"div"> & { theme?: Theme }) {
  return <div {...props} className={classes("ti-root", className)} data-ti-theme={theme} />;
}

export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={classes("ti-card", className)} />;
}

export function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={classes("ti-card-header", className)} />;
}

export function CardTitle({ as: Tag = "h2", className, ...props }: ComponentProps<"h2"> & { as?: "h2" | "h3" | "h4" }) {
  return <Tag {...props} className={classes("ti-card-title", className)} />;
}

export function CardDescription({ className, ...props }: ComponentProps<"p">) {
  return <p {...props} className={classes("ti-card-description", className)} />;
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={classes("ti-card-footer", className)} />;
}

export function Badge({ tone, className, ...props }: ComponentProps<"span"> & { tone?: Tone }) {
  return <span {...props} className={classes("ti-badge", className)} data-tone={tone} />;
}

export function Alert({ tone = "info", className, ...props }: ComponentProps<"div"> & { tone?: Tone }) {
  // Callers choose role="alert" only for urgent dynamic errors. Static notices
  // should not announce themselves every time the containing page renders.
  return <div {...props} className={classes("ti-alert", className)} data-tone={tone} />;
}

export function PageHeader({ title, description, actions, className, ...props }: Omit<ComponentProps<"header">, "title"> & { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return <header {...props} className={classes("ti-page-header", className)}><div><h1 className="ti-heading">{title}</h1>{description ? <p className="ti-muted">{description}</p> : null}</div>{actions ? <div className="ti-cluster">{actions}</div> : null}</header>;
}

export function MetricRow({ items, className, ...props }: ComponentProps<"dl"> & { items: { id: string; label: ReactNode; value: ReactNode }[] }) {
  return <dl {...props} className={classes("ti-metrics", className)}>{items.map((item) => <div key={item.id}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>;
}

export function CompactRows({ rows, className, ...props }: ComponentProps<"div"> & { rows: { id: string; label: ReactNode; content: ReactNode }[] }) {
  return <div {...props} className={classes("ti-rows", className)}>{rows.map((row) => <div key={row.id} className="ti-row"><div className="ti-row-label">{row.label}</div><div className="ti-row-value">{row.content}</div></div>)}</div>;
}

export function Progress({ label, className, max = 100, ...props }: ComponentProps<"progress"> & { label: string }) {
  return <progress {...props} max={max} aria-label={label} className={classes("ti-progress", className)} />;
}
