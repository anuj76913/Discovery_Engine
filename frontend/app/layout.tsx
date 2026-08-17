import type { Metadata } from "next";
import { Hanken_Grotesk, Inter, JetBrains_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";

const bodyFont = Inter({ subsets: ["latin"], variable: "--font-body" });
const headingFont = Hanken_Grotesk({ subsets: ["latin"], weight: ["600", "700", "800"], variable: "--font-heading" });
const dataMonoFont = JetBrains_Mono({ subsets: ["latin"], weight: ["500"], variable: "--font-data-mono" });

export const metadata: Metadata = {
  title: "Myntra Discovery Engine",
  description:
    "Ranked, quantified, evidence-backed opportunity areas behind Myntra's wishlist-to-purchase conversion, discovered from public conversation.",
};

// Set the theme attribute before hydration so there's no flash of the
// wrong theme — reads the same localStorage key ThemeToggle writes to.
const THEME_INIT_SCRIPT = `
(function() {
  try {
    var stored = localStorage.getItem('theme');
    if (stored === 'light' || stored === 'dark') {
      document.documentElement.setAttribute('data-theme', stored);
    }
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`h-full antialiased ${bodyFont.variable} ${headingFont.variable} ${dataMonoFont.variable}`}
      suppressHydrationWarning
    >
      <head>
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
      </head>
      <body className="min-h-full bg-page-plane text-text-primary">{children}</body>
    </html>
  );
}
