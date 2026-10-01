'use client';

import { useState } from 'react';

export default function ShareButton({ metric, value, isMock }: { metric: string; value: string; isMock: boolean }) {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    const text = `${isMock ? 'Demo · ' : ''}Ojas ${metric}: ${value}`;
    if (navigator.share) {
      try { await navigator.share({ title: 'Ojas', text }); } catch { /* User dismissed share sheet. */ }
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch { setCopied(false); }
  };
  return <button type="button" onClick={share} className="share-button" aria-label={`Share ${metric}`}>
    <span aria-hidden="true">↗</span> {copied ? 'COPIED' : 'SHARE'}
  </button>;
}
