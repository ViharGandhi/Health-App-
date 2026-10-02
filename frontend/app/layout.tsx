import type { Metadata, Viewport } from 'next';
import './globals.css';
import NavBar from '@/components/NavBar';

export const metadata: Metadata = {
  title: 'Ojas — Health and Recovery',
  description: 'Personal fitness tracking with Recovery, Sleep Score, and Strain — powered by your data.',
  icons: { icon: '/favicon.ico' },
};

export const viewport: Viewport = {
  themeColor: '#0B0B0B',
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
