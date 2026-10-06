import type { RecoveryDemo } from '@/lib/types';
import styles from '@/app/recovery/page.module.css';

export default function RecoveryDemoSwitch({ value, onChange }: { value: RecoveryDemo; onChange: (value: RecoveryDemo) => void }) {
  return <div className={styles.demoFooter}><span>DEMO · SYNTHETIC DATA</span>
    <label>Recovery demo<select aria-label="Recovery demo algorithm" value={value} onChange={event => onChange(event.target.value as RecoveryDemo)}>
      <option value="estimate">New estimate</option><option value="legacy">Older prototype</option>
    </select></label></div>;
}
