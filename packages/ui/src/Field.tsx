import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";

import { Icon } from "./icons";

/**
 * Label + control + hint + error, wired with aria-describedby / aria-invalid.
 * The child control must carry an `id`.
 */
export function Field({
  id,
  label,
  hint,
  error,
  children,
  className,
}: {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactElement;
  className?: string;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
      })
    : children;
  return (
    <div className={`field${className ? ` ${className}` : ""}`}>
      <label htmlFor={id}>{label}</label>
      {control}
      {hint ? (
        <p className="hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="error" id={errorId} role="alert">
          <Icon name="alert-circle" size={16} />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}
