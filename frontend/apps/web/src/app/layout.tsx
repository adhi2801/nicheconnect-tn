import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font, with a size-matched fallback so text does not shift as it loads.
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
const jakarta = Plus_Jakarta_Sans({ variable: "--font-jakarta", subsets: ["latin"], display: "swap" });
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: { default: "Colyv", template: "%s · Colyv" },
  description: "Every brand and creator deal, on the record.",
};

export const viewport: Viewport = { themeColor: "#F7F2E1" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${jakarta.variable} ${jetbrains.variable} h-full`}>
      <body className="ground-glow min-h-full flex flex-col">{children}</body>
    </html>
  );
}
