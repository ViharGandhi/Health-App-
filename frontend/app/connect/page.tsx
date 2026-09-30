'use client';

/**
 * Connect Page (/connect)
 * Guides the user through connecting their Fitbit via Google OAuth.
 * Shows connected state if already linked.
 */

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { AuthStatus } from '@/lib/types';
import styles from './page.module.css';

export default function ConnectPage() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState(false);

  useEffect(() => {
    api.getAuthStatus()
      .then(setStatus)
      .finally(() => setLoading(false));
  }, []);

  const handleConnect = () => api.startLogin();

  const handleDisconnect = async () => {
    setDisconnecting(true);
    await api.disconnect();
    setStatus({ connected: false, is_mock: true, user_email: null, user_name: null });
    setDisconnecting(false);
  };

  if (loading) {
    return (
      <div className="page" style={{ paddingTop: 24 }}>
        <div className="skeleton" style={{ height: 300, borderRadius: 24 }} />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Connect</h1>
      </div>

      {status?.connected ? (
        /* â”€â”€ Connected state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
        <div className="fade-in">
          <div className={`card ${styles.connectedCard}`}>
            <div className={styles.connectedIcon}>âœ…</div>
            <div className={styles.connectedInfo}>
              <p className={styles.connectedTitle}>Fitbit Connected</p>
              {status.user_name && (
                <p className={styles.connectedName}>{status.user_name}</p>
              )}
              {status.user_email && (
                <p className={styles.connectedEmail}>{status.user_email}</p>
              )}
            </div>
          </div>

          <div className={styles.steps}>
            <p className={styles.stepsTitle}>Live data is enabled</p>
            <p className={styles.stepsText}>
              Your Fitbit data is syncing automatically. Recovery, Sleep, and Strain
              scores are calculated using your real biometric data.
            </p>
          </div>

          <button
            id="disconnect-btn"
            className="btn btn-danger btn-full"
            onClick={handleDisconnect}
            disabled={disconnecting}
          >
            {disconnecting ? 'Disconnecting...' : 'âŠ— Disconnect Device'}
          </button>
        </div>

      ) : (
        /* â”€â”€ Not connected state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
        <div className="fade-in">
          {/* Hero */}
          <div className={styles.heroSection}>
            <div className={styles.heroGlow} />
            <div className={styles.heroIcon}>âŒš</div>
            <h2 className={styles.heroTitle}>Connect Your Fitbit</h2>
            <p className={styles.heroSubtitle}>
              Link your Google account to stream real HRV, heart rate, and sleep data
              directly to your dashboard.
            </p>
          </div>

          {/* Steps */}
          <div className={`card ${styles.stepsCard}`}>
            <p className="section-title" style={{ marginBottom: 16 }}>How It Works</p>
            {[
              { n: '1', title: 'Sign in with Google', desc: 'We use Google OAuth 2.0 â€” same account linked to your Fitbit.' },
              { n: '2', title: 'Grant Health Permissions', desc: 'Allow access to HRV, heart rate, sleep, and activity data.' },
              { n: '3', title: 'Sync Automatically', desc: 'Your dashboard updates with real data from your Fitbit device.' },
            ].map(({ n, title, desc }) => (
              <div key={n} className={styles.step}>
                <div className={styles.stepNum}>{n}</div>
                <div className={styles.stepInfo}>
                  <p className={styles.stepTitle}>{title}</p>
                  <p className={styles.stepDesc}>{desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* CTA */}
          <button
            id="connect-btn"
            className={`btn btn-primary btn-full ${styles.connectBtn}`}
            onClick={handleConnect}
          >
            <span>G</span> Sign in with Google
          </button>

          {/* Note */}
          <p className={styles.note}>
            ðŸ”’ Your data never leaves your device. All processing runs locally
            using your algorithms in Python.
          </p>

          {/* Setup instructions */}
          <div className={`card ${styles.setupCard}`}>
            <p className="section-title" style={{ marginBottom: 14 }}>First-Time Setup</p>
            <p className={styles.setupText}>
              Before connecting, you need to configure Google Cloud credentials
              once in <code className={styles.code}>backend/.env</code>:
            </p>
            <ol className={styles.setupList}>
              <li>Go to <strong>console.cloud.google.com</strong></li>
              <li>Create a project â†’ Enable <strong>Google Health API</strong></li>
              <li>Create OAuth 2.0 credentials (Web Application)</li>
              <li>Set redirect URI: <code className={styles.code}>http://localhost:8000/api/auth/callback</code></li>
              <li>Copy <code className={styles.code}>CLIENT_ID</code> and <code className={styles.code}>CLIENT_SECRET</code> to <code className={styles.code}>.env</code></li>
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
