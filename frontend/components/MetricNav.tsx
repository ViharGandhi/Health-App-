'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import styles from './MetricNav.module.css';

type Section = 'overview' | 'sleep' | 'recovery' | 'strain';

const tabs: { label: string; href: string; section: Section }[] = [
  { label: 'Overview', href: '/', section: 'overview' },
  { label: 'Sleep', href: '/sleep', section: 'sleep' },
  { label: 'Recovery', href: '/recovery', section: 'recovery' },
  { label: 'Strain', href: '/strain', section: 'strain' },
];

export default function MetricNav({
  active, isMock, children,
}: {
  active: Section;
  isMock: boolean;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [dayOffset, setDayOffset] = useState(0);

  useEffect(() => {
    const readDay = () => {
      const value = Number(new URLSearchParams(window.location.search).get('day') ?? 0);
      setDayOffset(Number.isInteger(value) ? Math.max(-7, Math.min(0, value)) : 0);
    };
    readDay();
    window.addEventListener('popstate', readDay);
    return () => window.removeEventListener('popstate', readDay);
  }, []);

  const changeDay = (next: number) => {
    const offset = Math.max(-7, Math.min(0, next));
    setDayOffset(offset);
    router.push(offset === 0 ? pathname : `${pathname}?day=${offset}`);
  };
  const chosenDate = new Date();
  chosenDate.setDate(chosenDate.getDate() + dayOffset);
  const dayLabel = dayOffset === 0
    ? 'TODAY'
    : chosenDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase();
  const query = dayOffset === 0 ? '' : `?day=${dayOffset}`;

  return (
    <>
      <header className={styles.header}>
        <Link href="/connect" className={styles.mark} aria-label="Ojas settings">O</Link>
        <div className={styles.datePicker}>
          <button type="button" onClick={() => changeDay(dayOffset - 1)} disabled={!isMock || dayOffset <= -7} aria-label="Previous day">‹</button>
          <span>{dayLabel}</span>
          <button type="button" onClick={() => changeDay(dayOffset + 1)} disabled={dayOffset >= 0} aria-label="Next day">›</button>
        </div>
        <Link href="/connect" className={styles.device} aria-label="Device connection">{isMock ? 'DEMO' : 'LIVE'}<span aria-hidden="true">◌</span></Link>
      </header>
      <nav className={styles.tabs} aria-label="Metrics">
        {tabs.map((tab) => (
          <Link key={tab.section} href={tab.href + query} className={active === tab.section ? styles.active : ''}>
            {tab.label}
          </Link>
        ))}
      </nav>
      {active === 'overview' && <div className={styles.wordmark}>OJAS</div>}
      {dayOffset === 0 ? children : (
        <div className={styles.noHistory}>
          <strong>No demo measurements for {dayLabel}</strong>
          <p>The sample dataset represents today. Historical scores will appear when synced data is available.</p>
          <button type="button" onClick={() => changeDay(0)}>Back to today</button>
        </div>
      )}
    </>
  );
}
