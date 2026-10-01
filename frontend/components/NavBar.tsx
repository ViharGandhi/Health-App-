'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styles from './NavBar.module.css';

const items = [
  { href: '/', label: 'Home', icon: '⌂' },
  { href: '/sleep', label: 'Sleep', icon: '☾' },
  { href: '/recovery', label: 'Recovery', icon: '♡' },
  { href: '/strain', label: 'Strain', icon: '◌' },
];

export default function NavBar() {
  const pathname = usePathname();
  return (
    <nav className={styles.nav} aria-label="Main navigation">
      <div className={styles.inner}>
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`${styles.item} ${pathname === item.href || (item.href === '/sleep' && pathname.startsWith('/sleep/')) ? styles.active : ''}`}
            aria-current={pathname === item.href ? 'page' : undefined}
          >
            <span className={styles.icon} aria-hidden="true">{item.icon}</span>
            <span className={styles.label}>{item.label}</span>
          </Link>
        ))}
      </div>
    </nav>
  );
}
