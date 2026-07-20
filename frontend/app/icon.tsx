import { ImageResponse } from "next/og";

// Programmatic PWA icon (no binary asset in the repo). Rendered by satori via
// next/og, so it works under `next dev` with no build step.
export const size = { width: 512, height: 512 };
export const contentType = "image/png";

// foghorn identity: a foghorn's blast cutting through the dark. Teal arcs —
// the app's brand hue — radiate from the bottom-left corner across a black
// ground (#0a0a0a, the app's dark-mode background). Distinct from sibling
// cadence (sky-blue bars on slate).
export default function Icon() {
  const d = size.width;
  const arc = (dia: number, w: number, color: string, opacity: number) => (
    <div
      style={{
        position: "absolute",
        left: -dia / 2,
        top: d - dia / 2,
        width: dia,
        height: dia,
        borderRadius: dia,
        border: `${w}px solid ${color}`,
        opacity,
      }}
    />
  );
  return new ImageResponse(
    (
      <div
        style={{
          width: d,
          height: d,
          position: "relative",
          display: "flex",
          overflow: "hidden",
          background: "#0a0a0a",
        }}
      >
        {arc(d * 1.5, d * 0.05, "#0d9488", 0.34)}
        {arc(d * 1.14, d * 0.052, "#14b8a6", 0.58)}
        {arc(d * 0.82, d * 0.056, "#2dd4bf", 0.82)}
        {arc(d * 0.52, d * 0.06, "#5eead4", 1)}
        {/* bright teal source at the corner the arcs emanate from */}
        <div
          style={{
            position: "absolute",
            left: -d * 0.11,
            top: d - d * 0.11,
            width: d * 0.22,
            height: d * 0.22,
            borderRadius: d * 0.22,
            background: "#99f6e4",
          }}
        />
      </div>
    ),
    { ...size },
  );
}
