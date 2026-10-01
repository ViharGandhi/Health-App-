import type { Metadata, Viewport } from 'next';
import './globals.css';
import NavBar from '@/components/NavBar';

export const metadata: Metadata = {
  title: 'WHOOP — Your Fitness Dashboard',
  description: 'Personal fitness tracking with Recovery, Sleep Score, and Strain — powered by your data.',
  icons: { icon: '/favicon.ico' },
};

export const viewport: Viewport = {
  themeColor: '#1a1c22',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>
          {children}
        </main>
        <NavBar />
      </body>
    </html>
  );
}
