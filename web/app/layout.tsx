import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "舞迹智存｜民族舞蹈数字化保护平台",
  description: "基于单目视觉、三维姿态重建与可溯源 AI 内容的民族舞蹈数字化保护与智能传习平台。",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}

