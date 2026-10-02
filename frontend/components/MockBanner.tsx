/**
 * MockBanner.tsx
 * WHOOP-style dismissable top banner shown when running in demo/mock mode.
 */
'use client';

import styles from './MockBanner.module.css';
import Link from 'next/link';

interface Props {
  isMock: boolean;
}

export default function MockBanner({ isMock }: Props) {
  if (!isMock) return null;

  return (
    <div className={styles.banner} role="alert">
      <span className={styles.dot} />
      <span className={styles.text}>Demo data &mdash; </span>
      <Link href="/connect" className={styles.link}>
        Connect your Fitbit &rarr;
      </Link>
    </div>
  );
}
