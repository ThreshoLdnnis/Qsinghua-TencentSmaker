import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LoveStone · 心象宇宙",
  description: "在心象宇宙里，和拾光一起整理感受，留下一点属于自己的光。",
  icons: { icon: "/mark.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Browser recorders can add attributes to the document root before hydration.
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
