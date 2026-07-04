import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import "./globals.css";
import { getJSON, type WatchlistEntry } from "./lib/api";

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
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Server-rendered per request, so the count reflects the watchlist on every
  // navigation. (Optimistic add/remove on cards catches up on the next nav.)
  const watchlist = await getJSON<WatchlistEntry[]>("/api/watchlist");
  const count = watchlist?.length ?? 0;

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <nav className="sticky top-0 z-10 flex items-baseline gap-4 border-b border-zinc-200 bg-white/85 px-6 py-3 text-sm backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/85">
          <Link
            href="/"
            className="mr-2 font-semibold tracking-tight text-teal-700 hover:text-teal-800 dark:text-teal-400 dark:hover:text-teal-300"
          >
            foghorn
          </Link>
          <Link href="/" className="font-medium hover:text-teal-700 dark:hover:text-teal-300">
            Shows
          </Link>
          <Link href="/watchlist" className="hover:text-teal-700 dark:hover:text-teal-300">
            Watchlist{count > 0 ? ` (${count})` : ""}
          </Link>
          <Link href="/venues" className="hover:text-teal-700 dark:hover:text-teal-300">
            Venues
          </Link>
          <Link href="/add" className="hover:text-teal-700 dark:hover:text-teal-300">
            Add event
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
