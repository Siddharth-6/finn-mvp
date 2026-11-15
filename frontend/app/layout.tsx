import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'FINN | Investment Intelligence',
  description: 'Evidence-first financial investment intelligence',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
