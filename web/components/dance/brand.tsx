"use client";

import { useId } from "react";
import "./brand.css";

type BrandProps = {
  compact?: boolean;
};

export function Brand({ compact = false }: BrandProps) {
  const filterId = `brand-paper-${useId().replace(/:/g, "")}`;
  return (
    <span className={`brand-lockup${compact ? " brand-lockup--compact" : ""}`}>
      <svg className="brand-mark" aria-hidden="true" viewBox="342 20 256 360">
        <defs><filter id={filterId} colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  -3 -3 -3 0 8" /></filter></defs>
        <image href="/brand/brand-board.png" width="1254" height="1254" filter={`url(#${filterId})`} />
      </svg>
      <span className="brand-wordmark">
        <span className="brand-name">舞之华</span>
        {!compact ? <span className="brand-tagline">以舞为桥 · 连接多彩中国</span> : null}
      </span>
    </span>
  );
}

type CharacterPortraitProps = {
  className?: string;
  decorative?: boolean;
};

/** Shows only the complete front portrait from the supplied character board. */
export function CharacterPortrait({
  className = "",
  decorative = false,
}: CharacterPortraitProps) {
  return (
    <span
      className={`brand-character${className ? ` ${className}` : ""}`}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : "舞之华品牌舞者，身着青绿与金色舞衣的完整正面形象"}
      aria-hidden={decorative ? true : undefined}
    >
      <span className="brand-character__art" />
    </span>
  );
}
