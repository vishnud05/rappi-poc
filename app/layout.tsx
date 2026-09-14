import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Buyer agent | Purchase review",
  description: "Investigate recommendations, execute purchases, and verify supplier outcomes.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
