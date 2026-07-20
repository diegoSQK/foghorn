import { ImageResponse } from "next/og";

// Programmatic PWA icon (no binary asset in the repo). Rendered by satori via
// next/og, so it works under `next dev` with no build step.
export const size = { width: 512, height: 512 };
export const contentType = "image/png";

// foghorn identity: a foghorn's blast cutting through fog. Warm amber arcs
// radiate from the bottom-left corner (the horn's mouth) across a deep
// teal-slate ground — the app's teal brand hue, pushed dark and foggy.
// Distinct from sibling cadence (sky-blue bars on slate).
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
          background: "linear-gradient(135deg, #0d3138 0%, #0a262c 100%)",
        }}
      >
        {arc(d * 1.5, d * 0.05, "#f59e0b", 0.34)}
        {arc(d * 1.14, d * 0.052, "#f59e0b", 0.58)}
        {arc(d * 0.82, d * 0.056, "#fbbf24", 0.82)}
        {arc(d * 0.52, d * 0.06, "#fcd34d", 1)}
        {/* horn mouth: bright core at the corner the arcs emanate from */}
        <div
          style={{
            position: "absolute",
            left: -d * 0.11,
            top: d - d * 0.11,
            width: d * 0.22,
            height: d * 0.22,
            borderRadius: d * 0.22,
            background: "#fde68a",
          }}
        />
      </div>
    ),
    { ...size },
  );
}
