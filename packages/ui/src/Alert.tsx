import type { ReactNode } from "react";

import { Icon, type IconName } from "./icons";

export type AlertTone = "info" | "success" | "warning" | "error" | "neutral";

const ICONS: Record<AlertTone, IconName> = {
  info: "info",
  success: "check-circle",
  warning: "alert-triangle",
  error: "alert-circle",
  neutral: "info",
};

/**
 * Inline message. Errors announce with role="alert"; everything else is polite (role="status").
 * `banner` renders edge to edge under the app bar (connectivity, session).
 */
export function Alert({
  tone = "info",
  title,
  children,
  actions,
  banner,
  icon,
  role,
  testId,
  onClose,
  className,
}: {
  tone?: AlertTone;
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  banner?: boolean;
  icon?: IconName | null;
  role?: "alert" | "status" | "none";
  testId?: string;
  onClose?: () => void;
  className?: string;
}) {
  const r = role ?? (tone === "error" ? "alert" : "status");
  const iconName = icon === null ? null : (icon ?? ICONS[tone]);
  return (
    <div
      className={`alert tone-${tone}${banner ? " banner" : ""}${className ? ` ${className}` : ""}`}
      role={r === "none" ? undefined : r}
      data-testid={testId}
    >
      {iconName ? <Icon name={iconName} /> : null}
      <div className="alert-body">
        {title ? <strong className="alert-title">{title}</strong> : null}
        {children}
        {actions ? <div className="alert-actions">{actions}</div> : null}
      </div>
      {onClose ? (
        <button type="button" className="ghost small alert-close" onClick={onClose} aria-label="Cerrar aviso">
          <Icon name="x" size={16} />
        </button>
      ) : null}
    </div>
  );
}
