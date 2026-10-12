import { useEffect } from "react";

import { PRODUCT_NAME } from "./brand";

/** Sets `document.title` to "Page · Pipeline de Posibles Tiendas" while the component is mounted. */
export function usePageTitle(title: string | null | undefined): void {
  useEffect(() => {
    const previous = document.title;
    document.title = title ? `${title} · ${PRODUCT_NAME}` : PRODUCT_NAME;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
