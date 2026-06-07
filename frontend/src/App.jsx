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
