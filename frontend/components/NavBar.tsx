/**
 * NavBar.tsx
 * WHOOP bottom tab navigation: Home, Health, Community, More.
 */
'use client';

import styles from './NavBar.module.css';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function NavBar() {
  const pathname = usePathname();

  const isHome = pathname === '/';
  const isHealth = pathname === '/recovery' || pathname === '/sleep' || pathname === '/strain';
  const isConnect = pathname === '/connect';

  return (
    <nav className={styles.nav}>
      <div className={styles.inner}>
        {/* Home */}
        <Link href="/" className={`${styles.item} ${isHome ? styles.active : ''}`}>
          <div className={styles.iconBox}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
              <polyline points="9 22 9 12 15 12 15 22" />
            </svg>
          </div>
          <span className={styles.label}>Home</span>
        </Link>

        {/* Health */}
        <Link href="/recovery" className={`${styles.item} ${isHealth ? styles.active : ''}`}>
          <div className={styles.iconBox}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20.42 4.58a5.4 5.4 0 0 0-7.65 0l-.77.78-.77-.78a5.4 5.4 0 0 0-7.65 0C1.46 6.7 1.33 10.28 4 13l8 8 8-8c2.67-2.72 2.54-6.3.42-8.42z" />
              <path d="M12 9v6" strokeWidth="2" />
              <path d="M9 12h6" strokeWidth="2" />
            </svg>
          </div>
          <span className={styles.label}>Health</span>
        </Link>

        {/* Community */}
        <Link href="/connect" className={`${styles.item} ${isConnect ? styles.active : ''}`}>
          <div className={styles.iconBox}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
          <span className={styles.label}>Community</span>
        </Link>

        {/* More */}
        <Link href="/connect" className={styles.item}>
          <div className={styles.iconBox}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="1" />
              <circle cx="19" cy="12" r="1" />
              <circle cx="5" cy="12" r="1" />
            </svg>
          </div>
          <span className={styles.label}>More</span>
        </Link>
      </div>
    </nav>
  );
}
