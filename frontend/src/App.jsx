import { useState, useEffect } from 'react';
import Auth from './components/Auth';
import Dashboard from './components/Dashboard';
import { api } from './api';

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = async () => {
    try {
      const currentUser = await api.getCurrentUser();
      setUser(currentUser);
    } catch {
      // Not logged in or expired token
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  // Check login status on mount
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    bootstrap();
  }, []);

  // Proactive token refresh — keeps the session alive while the user is active
  useEffect(() => {
    if (!user) return;

    let lastActivity = Date.now();

    const trackActivity = () => { lastActivity = Date.now(); };
    window.addEventListener('mousemove', trackActivity, { passive: true });
    window.addEventListener('keydown', trackActivity, { passive: true });
    window.addEventListener('touchstart', trackActivity, { passive: true });
    window.addEventListener('click', trackActivity, { passive: true });

    // Refresh access token every 5 minutes if user was active in the last 10 minutes
    const REFRESH_INTERVAL = 5 * 60 * 1000; // 5 min
    const IDLE_THRESHOLD = 10 * 60 * 1000;   // 10 min

    const intervalId = setInterval(async () => {
      if (Date.now() - lastActivity > IDLE_THRESHOLD) return; // user truly idle, skip
      try {
        await api.refreshToken();
      } catch {
        // Refresh failed — token is dead, log the user out
        setUser(null);
      }
    }, REFRESH_INTERVAL);

    return () => {
      clearInterval(intervalId);
      window.removeEventListener('mousemove', trackActivity);
      window.removeEventListener('keydown', trackActivity);
      window.removeEventListener('touchstart', trackActivity);
      window.removeEventListener('click', trackActivity);
    };
  }, [user]);


  const handleAuthSuccess = (authenticatedUser) => {
    setUser(authenticatedUser);
  };

  const handleLogout = async () => {
    if (!window.confirm('Are you sure you want to log out?')) return;
    try {
      await api.logout();
      setUser(null);
    } catch (e) {
      console.error('Logout failed:', e);
      setUser(null); // Force log out on frontend anyway
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col justify-center items-center text-on-surface select-none">
        <span className="material-symbols-outlined animate-spin text-4xl text-secondary" style={{ animationDuration: '2s' }}>progress_activity</span>
        <p className="mt-4 text-sm text-on-surface-variant font-label-md">Bootstrapping Lumen...</p>
      </div>
    );
  }

  return user ? (
    <Dashboard user={user} onLogout={handleLogout} />
  ) : (
    <Auth onAuthSuccess={handleAuthSuccess} />
  );
}
