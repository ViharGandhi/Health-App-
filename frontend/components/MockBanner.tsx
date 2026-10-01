/**
 * MockBanner.tsx
 * Visible label for sample measurements.
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
      <span className={styles.text}>SAMPLE DATA</span>
      <Link href="/connect" className={styles.link}>
        Device setup &rarr;
      </Link>
    </div>
  );
}
