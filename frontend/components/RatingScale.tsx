'use client';

import styles from './RatingScale.module.css';

export interface RatingOption { value: number; label?: string }

/** A row of tap targets for a 1–N self-report, with a status line underneath. */
export default function RatingScale({ title, question, options, value, onSelect, busy, status, error, children }: {
  title: string; question: string; options: RatingOption[]; value: number | null;
  onSelect: (value: number) => void; busy?: boolean; status?: string; error?: string | null; children?: React.ReactNode;
}) {
  return <section className={styles.card} aria-label={title}>
    <h2 className={styles.title}>{title}</h2>
    <p className={styles.question}>{question}</p>
    <div className={`${styles.scale} ${options.length > 6 ? styles.long : ''}`} role="radiogroup" aria-label={question} style={{ '--columns': options.length } as React.CSSProperties}>
      {options.map(option => <button key={option.value} type="button" role="radio" aria-checked={value === option.value}
        aria-label={option.label ? `${option.value}, ${option.label}` : String(option.value)}
        className={value === option.value ? styles.selected : undefined} disabled={busy} onClick={() => onSelect(option.value)}>
        <strong>{option.value}</strong>{option.label && <small>{option.label}</small>}
      </button>)}
    </div>
    {children}
    {status && <p className={styles.status} role="status">{status}</p>}
    {error && <p className={styles.error} role="alert">{error}</p>}
  </section>;
}
