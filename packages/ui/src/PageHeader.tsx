import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
  back,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Back link rendered above the title (detail pages). */
  back?: ReactNode;
  /** Extra content under the title (badges, stage indicator). */
  children?: ReactNode;
}) {
  return (
    <>
      {back}
      <div className="page-header">
        <div className="page-title">
          <h1>{title}</h1>
          {description ? <p className="description">{description}</p> : null}
          {children}
        </div>
        {actions ? <div className="page-actions">{actions}</div> : null}
      </div>
    </>
  );
}
