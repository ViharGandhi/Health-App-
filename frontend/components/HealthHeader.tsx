import Link from 'next/link';
import styles from '@/app/recovery/page.module.css';

export default function HealthHeader({ onInfo }: { onInfo: () => void }) {
  return <header className={styles.header}>
    <Link href="/health" aria-label="Back to Health"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m15 4-8 8 8 8" /></svg></Link>
    <span>TREND VIEW</span>
    <button onClick={onInfo} aria-label="Health guide"><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10" /><path d="M12 11v6M12 7v1" /></svg></button>
  </header>;
}
