import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Soroban Health",
  description:
    "Contract observability, anti-pattern detection, and test-coverage scoring for Soroban smart contracts.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
