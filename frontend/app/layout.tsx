import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import "./globals.css";
import UserMenu from "./UserMenu";
import { getJSON, type PendingEventView } from "./lib/api";
import { getMe, sessionHeaders } from "./lib/serverAuth";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "foghorn",
  description: "A Bay Area local music & jazz show aggregator.",
  // Standalone "Add to Home Screen" launch on iOS: own app-switcher card,
  // chrome-less. The manifest + icon routes are auto-linked by Next.
  appleWebApp: {
    capable: true,
    title: "foghorn",
    statusBarStyle: "default",
  },
};

// Split out from metadata per Next 16 (themeColor / viewportFit live here).
// themeColor tracks the real page background per color scheme (globals.css:
// #ffffff light, #0a0a0a dark); viewportFit 'cover' lets standalone launch
// paint into the iPhone safe-area insets.
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
  viewportFit: "cover",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Server-rendered per request, so the session state and inbox count
  // reflect current state on every navigation. The inbox (and the nav links
  // to it and to Add event) is admin-only since multi-user (August 2026).
  const me = await getMe();
  let inboxCount = 0;
  if (me?.is_admin) {
    const headers = await sessionHeaders();
    const inbox = await getJSON<PendingEventView[]>("/api/inbox", { headers });
    inboxCount = inbox?.length ?? 0;
  }

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* whitespace-nowrap keeps the nav a constant 45px tall at any
            viewport width — ShowList's sticky date headers pin to that
            offset, so a link wrapping to two lines would break them. */}
        <nav className="sticky top-0 z-10 flex items-baseline gap-4 whitespace-nowrap border-b border-zinc-200 bg-white/85 px-6 py-3 text-sm backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/85">
          <Link
            href="/"
            className="mr-2 font-semibold tracking-tight text-teal-700 hover:text-teal-800 dark:text-teal-400 dark:hover:text-teal-300"
          >
            foghorn
          </Link>
          <Link href="/" className="font-medium hover:text-teal-700 dark:hover:text-teal-300">
            Shows
          </Link>
          {me?.is_admin && (
            <>
              <Link href="/add" className="hover:text-teal-700 dark:hover:text-teal-300">
                Add event
              </Link>
              <Link href="/inbox" className="hover:text-teal-700 dark:hover:text-teal-300">
                Inbox{inboxCount > 0 ? ` (${inboxCount})` : ""}
              </Link>
              <Link href="/people" className="hover:text-teal-700 dark:hover:text-teal-300">
                People
              </Link>
            </>
          )}
          <UserMenu me={me} />
        </nav>
        {children}
      </body>
    </html>
  );
}
