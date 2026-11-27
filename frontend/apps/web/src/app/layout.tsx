import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font, with a size-matched fallback so text does not shift as it loads.
// Inter is the one typeface of the neutral look (HD-004), with its optical-size axis: at display sizes the letters draw tighter and
// finer on their own, as Inter Display, so headlines need no second face.
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap", axes: ["opsz"] });
// The heritage look's display face (data-look="heritage"): not preloaded, so the neutral look does not pay for it.
const jakarta = Plus_Jakarta_Sans({ variable: "--font-jakarta", subsets: ["latin"], display: "swap", preload: false });
// Figures in the signed-in app only: not preloaded, so public pages do not pay for a face they never show.
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"], display: "swap", preload: false });

export const metadata: Metadata = {
  title: { default: "Colyv", template: "%s · Colyv" },
  description: "Every brand and creator deal, on the record.",
  // Phones (Safari on iPhone above all) turn numbers, addresses and emails in page text into tappable links. Other people's text is
  // never made clickable (frontend.md section 10): "Call me on 98765 43210" in a note stays words.
  formatDetection: { telephone: false, email: false, address: false },
};

// The neutral look's ground (tokens.json look.neutral.light.ground), so the phone's browser bar matches the page.
export const viewport: Viewport = { themeColor: "#F7F7F6" };

// Development builds outline every design slot with its name (src/design/design-slot.tsx), so it is clear where each design goes.
const showSlots = process.env.NODE_ENV === "development" ? "" : undefined;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-show-slots={showSlots} className={`${inter.variable} ${jakarta.variable} ${jetbrains.variable} h-full`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
