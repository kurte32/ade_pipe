/**
 * Brand mark: a vector re-creation of the Tiendas 3B roundel as observed on tiendas3b.com
 * (red circle, white "B" over "BB"). Replace with the official asset from Mercadotecnia before
 * go-live (docs/ux/DESIGN_SYSTEM.md section 1).
 */
export function BrandMark({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={`brand-mark${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Tiendas 3B"
    >
      <circle cx="32" cy="32" r="31" fill="#d7121e" />
      <text
        x="32"
        y="29"
        textAnchor="middle"
        fontFamily="Montserrat, system-ui, sans-serif"
        fontWeight="800"
        fontSize="19"
        fill="#fff"
      >
        B
      </text>
      <text
        x="32"
        y="49"
        textAnchor="middle"
        fontFamily="Montserrat, system-ui, sans-serif"
        fontWeight="800"
        fontSize="21"
        fill="#fff"
      >
        BB
      </text>
    </svg>
  );
}

export const PRODUCT_NAME = "Pipeline de Posibles Tiendas";

export function Brand({ area, href = "/" }: { area?: string; href?: string }) {
  return (
    <a className="brand" href={href} aria-label={`${PRODUCT_NAME}${area ? ` · ${area}` : ""}, inicio`}>
      <BrandMark />
      <span className="brand-text" aria-hidden="true">
        <span className="brand-name">{PRODUCT_NAME}</span>
        {area ? <span className="brand-area">{area}</span> : null}
      </span>
    </a>
  );
}
