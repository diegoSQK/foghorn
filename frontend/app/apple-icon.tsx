import { ImageResponse } from "next/og";

// Apple touch icon for iOS "Add to Home Screen". Full-bleed and opaque
// (solid ground, no transparency, no pre-rounded corners — iOS masks the
// rounding itself). Rendered by satori via next/og; works under `next dev`.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// Same foghorn mark as icon.tsx, scaled for the 180x180 apple slot.
export default function AppleIcon() {
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
