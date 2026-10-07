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
  const [syncing, setSyncing] = useState(false);
  const [lastSynced, setLastSynced] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [age, setAge] = useState('');
  const [ageSaved, setAgeSaved] = useState(false);
  const [ageError, setAgeError] = useState('');

  useEffect(() => {
    if (status?.connected) api.getDataStatus().then(data => setLastSynced(data.last_synced_at)).catch(() => {});
  }, [status?.connected]);

  useEffect(() => {
    setAge(window.localStorage.getItem('ojas_age') ?? '');
    const reason = new URLSearchParams(window.location.search).get('error');
    if (reason) {
      setError({
        invalid_state: 'Connection expired. Please try again.',
        health_account_not_linked: 'This Google account is not linked to a Google Health profile.',
        health_access_failed: 'Google Health access failed. Check that this project has API access.',
        token_exchange_failed: 'Google sign-in could not finish. Please try again.',
      }[reason] || 'Connection could not finish. Please try again.');
    }
    api.getAuthStatus()
      .then(setStatus)
      .catch(reason => setError(reason instanceof Error ? reason.message : 'Connection status unavailable.'))
      .finally(() => setLoading(false));
  }, []);

  const handleConnect = () => api.startLogin();

  const handleDisconnect = async () => {
    setDisconnecting(true);
    await api.disconnect();
    setStatus({ connected: false, is_mock: true, can_connect: status?.can_connect ?? false, user_email: null, user_name: null });
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
            <div className={styles.connectedIcon}>✓</div>
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
            <p className={styles.stepsTitle}>Google Health is connected</p>
            <p className={styles.stepsText}>
              The dashboard reads available Fitbit data from Google Health when you open it.
              Scores depend on the measurements your device provides.
            </p>
          </div>

          <button
            id="disconnect-btn"
            className="btn btn-danger btn-full"
            onClick={handleDisconnect}
            disabled={disconnecting}
          >
            {disconnecting ? 'Disconnecting...' : 'Disconnect Device'}
          </button>
          <p className={styles.setupText} style={{ marginTop: 16 }}>
            {lastSynced ? `Last fetched: ${new Date(lastSynced).toLocaleString()}` : 'No readings stored yet.'}
            {' '}Pages reuse recent data. Sync now checks for new readings and recent corrections.
          </p>
          <button className="btn btn-primary btn-full" disabled={syncing || disconnecting} style={{ marginTop: 12 }} onClick={async () => {
            setSyncing(true); setError('');
            try { await api.syncNow(); window.location.href = '/'; }
            catch (reason) { setError(reason instanceof Error ? reason.message : 'Sync could not start.'); setSyncing(false); }
          }}>{syncing ? 'Starting sync…' : 'Sync now'}</button>
          {error && <p className={styles.error} role="alert">{error}</p>}
        </div>

      ) : (
        /* â”€â”€ Not connected state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
        <div className="fade-in">
          {/* Hero */}
          <div className={styles.heroSection}>
            <div className={styles.heroGlow} />
            <div className={styles.heroIcon} aria-hidden="true">
              <svg width="60" height="60" viewBox="0 0 60 60" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M22 5h16l3 10H19L22 5ZM19 45h22l-3 10H22l-3-10Z" />
                <rect x="13" y="14" width="34" height="32" rx="10" />
                <circle cx="30" cy="30" r="9" />
              </svg>
            </div>
            <h2 className={styles.heroTitle}>Connect Your Fitbit</h2>
            <p className={styles.heroSubtitle}>
              Link the Google account used by your Fitbit and Google Health profile
              to read available HRV, heart rate, and sleep data.
            </p>
          </div>

          {error && <p className={styles.error} role="alert">{error}</p>}

          {/* Steps */}
          <div className={`card ${styles.stepsCard}`}>
            <p className="section-title" style={{ marginBottom: 16 }}>How It Works</p>
            {[
              { n: '1', title: 'Sign in with Google', desc: 'We use Google OAuth 2.0 with the account linked to your Fitbit.' },
              { n: '2', title: 'Grant Health Permissions', desc: 'Allow access to HRV, heart rate, sleep, and activity data.' },
              { n: '3', title: 'View Your Data', desc: 'The dashboard reads available Fitbit measurements from Google Health.' },
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
            disabled={!status?.can_connect}
          >
            <span>G</span> {status?.can_connect ? 'Sign in with Google' : 'Google Health access not configured'}
          </button>

          {/* Note */}
          <p className={styles.note}>
            Google Health stores and serves your Fitbit data. This app requests read-only access
            and calculates scores in its Python backend.
          </p>

          {/* Setup instructions */}
          <div className={`card ${styles.setupCard}`}>
            <p className="section-title" style={{ marginBottom: 14 }}>First-Time Setup</p>
            <p className={styles.setupText}>
              Google currently says it is not onboarding new Health API projects. When access
              opens, configure credentials in <code className={styles.code}>backend/.env</code>:
            </p>
            <ol className={styles.setupList}>
              <li>Go to <strong>console.cloud.google.com</strong></li>
              <li>Create a project and enable <strong>Google Health API</strong></li>
              <li>Create OAuth 2.0 credentials (Web Application)</li>
              <li>Set redirect URI: <code className={styles.code}>http://localhost:8000/api/auth/callback</code></li>
              <li>Copy <code className={styles.code}>GOOGLE_CLIENT_ID</code> and <code className={styles.code}>GOOGLE_CLIENT_SECRET</code> to <code className={styles.code}>.env</code></li>
            </ol>
          </div>
        </div>
      )}
      <div className={`card ${styles.setupCard}`}>
        <p className="section-title" style={{ marginBottom: 10 }}>Your age</p>
        <p className={styles.setupText}>Used to estimate maximum heart rate for connected zone calculations. Fitbit Air does not supply a measured maximum heart rate through the current data fields. Demo scores do not use this setting.</p>
        <label htmlFor="user-age" className={styles.setupText}>Age in years</label>
        <input id="user-age" type="number" min="18" max="100" value={age} onChange={(event) => { setAge(event.target.value); setAgeSaved(false); }} style={{ width: '100%', margin: '8px 0 12px', padding: 12, borderRadius: 10, border: '1px solid #454545', background: '#151515', color: '#FFFFFF', fontSize: 16 }} />
        <button type="button" className="btn btn-primary" onClick={() => {
          const value = Number(age);
          if (!Number.isInteger(value) || value < 18 || value > 100) { setAgeError('Enter an age from 18 to 100.'); return; }
          window.localStorage.setItem('ojas_age', String(value));
          setAgeError('');
          setAgeSaved(true);
        }}>Save age</button>
        {ageSaved && <p className={styles.setupText} role="status">Saved on this device.</p>}
        {ageError && <p className={styles.error} role="alert">{ageError}</p>}
      </div>
      <div className={`card ${styles.setupCard}`}>
        <p className="section-title" style={{ marginBottom: 10 }}>Install on iPhone</p>
        <p className={styles.setupText}>Open the deployed Ojas site in Safari, tap Share, then Add to Home Screen. A secure HTTPS address is required outside local development. Device readings still need Google Health access.</p>
      </div>
    </div>
  );
}
