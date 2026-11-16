import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "翎语 · 心象宇宙",
  description: "来自未知星球的陪伴，在心象宇宙里和你一起整理感受。",
  icons: { icon: "/mark.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN" suppressHydrationWarning><body>{children}</body></html>;
}
