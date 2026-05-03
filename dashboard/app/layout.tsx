import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { Github, ExternalLink } from "lucide-react";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "bcbs239-lakehouse · BCBS 239 reference dashboard",
  description:
    "Reference implementation of the BCBS 239 risk-data-aggregation lakehouse pattern on Databricks + Delta Lake + Unity Catalog. Synthetic data only.",
  metadataBase: new URL("https://bcbs239-lakehouse.vercel.app"),
  openGraph: {
    title: "bcbs239-lakehouse",
    description:
      "BCBS 239 lakehouse reference implementation on Databricks + Delta Lake + Unity Catalog. Portfolio piece, synthetic data only.",
    type: "website",
  },
  robots: { index: true, follow: true },
};

const NAV_LINKS = [
  { href: "/", label: "Overview" },
  { href: "/scorecard", label: "DQ scorecard" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/exposures", label: "Exposures" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen flex flex-col">
        <header className="border-b border-[var(--color-border)]">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 py-4 flex flex-wrap items-center gap-4 justify-between">
            <Link
              href="/"
              className="inline-link font-semibold tracking-tight text-base sm:text-lg"
            >
              bcbs239-lakehouse
            </Link>
            <nav className="flex flex-wrap items-center gap-4 sm:gap-6 text-sm">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="inline-link text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
                >
                  {link.label}
                </Link>
              ))}
              <a
                href="https://github.com/soneeee22000/bcbs239-lakehouse"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-link inline-flex items-center gap-1 text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
              >
                <Github size={16} aria-hidden="true" />
                <span>Repo</span>
                <ExternalLink size={12} aria-hidden="true" />
              </a>
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-[var(--color-border)]">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 py-6 text-xs text-[var(--color-muted-foreground)] flex flex-wrap items-center gap-x-4 gap-y-2 justify-between">
            <p>
              Synthetic data only · LEI prefix <code>9999</code> · MIT license
            </p>
            <p>
              <a
                className="inline-link hover:text-[var(--color-foreground)]"
                href="https://github.com/soneeee22000/csrd-lake"
                target="_blank"
                rel="noopener noreferrer"
              >
                Sibling: csrd-lake (Snowflake stack)
              </a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
