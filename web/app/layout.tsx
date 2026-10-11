import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "舞之华｜让传统，在当下起舞",
  description: "从一段舞蹈开始，观看示范、慢放跟练，用动作辅助认识民族舞蹈。",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}

