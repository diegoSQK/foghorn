import type { MetadataRoute } from "next";

// Web App Manifest for foghorn's "Add to Home Screen" (PWA) install.
// Next auto-serves this at /manifest.webmanifest and links it from <head>.
// Icons here drive Android/Chrome installs; iOS uses the apple-icon route
// (auto-linked as apple-touch-icon) plus the appleWebApp metadata in layout.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "foghorn",
    short_name: "foghorn",
    description: "A Bay Area local music & jazz show aggregator.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    // Splash background matches the app's real light-mode page background;
    // theme_color is the teal brand chrome (matches the nav's foghorn wordmark).
    background_color: "#ffffff",
    theme_color: "#0f766e",
    icons: [
      {
        src: "/icon",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}
