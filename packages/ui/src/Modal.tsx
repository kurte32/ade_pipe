import { useEffect, useId, useRef, type ReactNode } from "react";

import { Icon } from "./icons";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Accessible dialog: labelled by its title, traps focus, restores focus on close, closes on
 * Escape. Backdrop click closes only when `dismissOnBackdrop` (default true) is set; forms with
 * user input should pass false so a stray click does not discard work.
 */
export function Modal({
  title,
  onClose,
  children,
  testId,
  lede,
  dismissOnBackdrop = true,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
  lede?: ReactNode;
  dismissOnBackdrop?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  // The mount effect must run once: a new inline onClose on every parent render would otherwise
  // tear it down and re-run it, moving focus out of and back into the dialog mid-interaction.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !node) return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null);
      if (items.length === 0) return;
      const firstEl = items[0]!;
      const lastEl = items[items.length - 1]!;
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, []);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => dismissOnBackdrop && e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} data-testid={testId} tabIndex={-1}>
        <div className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="ghost small" aria-label="Cerrar" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        {lede ? <p className="lede">{lede}</p> : null}
        {children}
      </div>
    </div>
  );
}
