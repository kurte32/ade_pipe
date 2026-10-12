import type { ReactNode } from "react";

import { Icon, type IconName } from "./icons";

export function EmptyState({
  icon = "inbox",
  title,
  children,
  actions,
  testId,
}: {
  icon?: IconName;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  testId?: string;
}) {
  return (
    <div className="empty" data-testid={testId}>
      <Icon name={icon} size={32} />
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
      {actions ? <div className="actions">{actions}</div> : null}
    </div>
  );
}
