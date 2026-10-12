import type { ReactNode } from "react";

import { Brand } from "./brand";

/** Application shell header: brand, primary navigation and a right-hand slot (status, account). */
export function AppBar({
  area,
  nav,
  right,
  narrow,
  homeHref = "/",
}: {
  area?: string;
  /** Rendered inside `<nav aria-label="Principal">`; the app supplies its router links. */
  nav: ReactNode;
  right?: ReactNode;
  narrow?: boolean;
  homeHref?: string;
}) {
  return (
    <>
      <a className="skip-link" href="#contenido">
        Ir al contenido
      </a>
      <header className={`appbar${narrow ? " narrow" : ""}`}>
        <div className="appbar-inner">
          <Brand area={area} href={homeHref} />
          <nav aria-label="Principal">{nav}</nav>
          {right ? <div className="appbar-right">{right}</div> : null}
        </div>
      </header>
    </>
  );
}
