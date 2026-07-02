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
        <nav className="flex gap-4 border-b border-zinc-200 px-6 py-3 text-sm dark:border-zinc-800">
          <Link href="/" className="font-medium hover:underline">
            Shows
          </Link>
          <Link href="/watchlist" className="hover:underline">
            Watchlist{count > 0 ? ` (${count})` : ""}
          </Link>
          <Link href="/add" className="hover:underline">
            Add event
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
