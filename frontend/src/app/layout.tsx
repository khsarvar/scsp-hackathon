import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "@/hooks/useSession";

export const metadata: Metadata = {
  title: "HealthLab Agent — Public Health Data Analysis",
  description: "Turn public health data into reproducible insights with AI.",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
