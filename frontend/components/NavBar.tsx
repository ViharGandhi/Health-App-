/**
 * NavBar.tsx
 * WHOOP-style bottom navigation bar.
 * Minimal dark design with subtle active states.
 */
'use client';

import styles from './NavBar.module.css';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { href: '/',          icon: '◉', label: 'Overview'  },
  { href: '/recovery',  icon: '♡', label: 'Recovery'  },
  { href: '/sleep',     icon: '☽', label: 'Sleep'     },
  { href: '/strain',    icon: '⚡', label: 'Strain'    },
  { href: '/connect',   icon: '⊕', label: 'Connect'   },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <nav className={styles.nav}>
      <div className={styles.inner}>
        {NAV_ITEMS.map(({ href, icon, label }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`${styles.item} ${active ? styles.active : ''}`}
              aria-label={label}
            >
              <span className={styles.icon}>{icon}</span>
              <span className={styles.label}>{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
