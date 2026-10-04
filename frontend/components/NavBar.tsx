'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styles from './NavBar.module.css';

export default function NavBar() {
  const pathname = usePathname();
  if (pathname.startsWith('/sleep/')) {
    return null;
  }
  const items = [
    { href: '/', label: 'Home', icon: <><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></> },
    { href: '/sleep', label: 'Sleep', icon: <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5z" /> },
    { href: '/recovery', label: 'Recovery', icon: <><path d="M20.42 4.58a5.4 5.4 0 0 0-7.65 0l-.77.78-.77-.78a5.4 5.4 0 0 0-7.65 0C1.46 6.7 1.33 10.28 4 13l8 8 8-8c2.67-2.72 2.54-6.3.42-8.42z" /><path d="M12 9v6M9 12h6" /></> },
    { href: '/strain', label: 'Strain', icon: <><path d="M12 3v5M12 16v5M3 12h5M16 12h5" /><circle cx="12" cy="12" r="4" /></> },
    { href: '/health', label: 'Health', icon: <path d="M3 12h4l2.3-5 4.2 10 2.2-5H21" /> },
  ];

  return <nav className={styles.nav} aria-label="Main navigation"><div className={styles.inner}>
    {items.map((item) => {
      const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
      return <Link key={item.href} href={item.href} className={`${styles.item} ${active ? styles.active : ''}`} aria-current={active ? 'page' : undefined}>
        <div className={styles.iconBox}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{item.icon}</svg></div>
        <span className={styles.label}>{item.label}</span>
      </Link>;
    })}
  </div></nav>;
}
