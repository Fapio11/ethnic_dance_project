export type DanceIconName = "stage" | "archive" | "movement" | "record" | "depth";

type DanceIconProps = {
  name: DanceIconName;
  selected?: boolean;
  size?: "nav" | "folio" | "empty" | "small";
  className?: string;
};

/** Original hand-painted raster assets. Adjacent native text supplies the meaning. */
export function DanceIcon({ name, selected = false, size = "nav", className = "" }: DanceIconProps) {
  return (
    <span className={`dance-icon dance-icon--${size} ${className}`} data-selected={selected} aria-hidden="true">
      {/* Pre-encoded transparent WebP assets are 17–24 KB; no runtime image service is needed. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/art/handdrawn/${name}.webp`} width={256} height={256} alt="" decoding="async" draggable={false} />
    </span>
  );
}
