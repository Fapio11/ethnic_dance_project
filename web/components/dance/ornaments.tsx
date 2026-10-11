type DanceArtworkProps = { variant?: "solo" | "ensemble" };

/** Original stage-dance artwork. Decorative, with no ethnic or instructional attribution. */
export function DanceArtwork({ variant = "solo" }: DanceArtworkProps) {
  return <picture className={`dance-artwork dance-artwork--${variant}`}>
    <img
      src="/art/handdrawn/ensemble.webp"
      width={1800}
      height={600}
      alt="" aria-hidden="true" decoding="async"
    />
  </picture>;
}
