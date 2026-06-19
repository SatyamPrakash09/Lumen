import { useState } from 'react';
import { api } from '../api';

export default function Auth({ onAuthSuccess }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [username, setusername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        const payload = { password };
        if (email.includes('@')) {
          payload.email = email;
        } else {
          payload.username = email;
        }
        const user = await api.login(payload);
        onAuthSuccess(user);
      } else {
        await api.register({
          email,
          password,
          firstName,
          lastName,
          username,
        });
        const loggedInUser = await api.login({ email, password });
        onAuthSuccess(loggedInUser);
      }
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 relative overflow-hidden select-none">
      <div className="relative w-full max-w-sm">
        <div className="bg-zinc-950 border border-zinc-800 rounded-2xl p-8 shadow-2xl">
          <div className="text-center mb-8">
            <div className="w-12 h-12 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mx-auto mb-4 animate-pulse-emerald">
              <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>token</span>
            </div>
            <h1 className="text-2xl font-bold text-zinc-100 tracking-wide">
              Lumen AI
            </h1>
            <p className="text-zinc-400 text-xs mt-2 leading-relaxed">
              {isLogin ? 'Welcome back. Log in to continue.' : 'Create an account to start document analysis.'}
            </p>
          </div>

          {error && (
            <div className="mb-5 p-3 bg-red-950/45 border border-red-900/50 rounded-xl text-red-400 text-xs leading-normal">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {!isLogin && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-zinc-400 mb-1.5">First Name</label>
                    <input
                      type="text"
                      required
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      placeholder="Jane"
                      className="w-full bg-zinc-900 border border-zinc-850 focus:border-zinc-750 rounded-xl py-2 px-3 text-sm text-zinc-100 placeholder-zinc-700 outline-none transition-colors"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-zinc-400 mb-1.5">Last Name</label>
                    <input
                      type="text"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      placeholder="Doe"
                      className="w-full bg-zinc-900 border border-zinc-850 focus:border-zinc-750 rounded-xl py-2 px-3 text-sm text-zinc-100 placeholder-zinc-700 outline-none transition-colors"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-zinc-400 mb-1.5">Username</label>
                  <input
                    type="text"
                    required
                    value={username}
                    onChange={(e) => setusername(e.target.value)}
                    placeholder="Username001"
                    className="w-full bg-zinc-900 border border-zinc-850 focus:border-zinc-750 rounded-xl py-2 px-3 text-sm text-zinc-100 placeholder-zinc-700 outline-none transition-colors"
                  />
                </div>
              </>
            )}

            <div>
              <label className="block text-[11px] font-semibold text-zinc-400 mb-1.5">
                {isLogin ? 'Email or Username' : 'Email Address'}
              </label>
              <input
                type="text"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={isLogin ? "test@lumen.app or Username001" : "test@lumen.app"}
                className="w-full bg-zinc-900 border border-zinc-850 focus:border-zinc-750 rounded-xl py-2 px-3 text-sm text-zinc-100 placeholder-zinc-700 outline-none transition-colors"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-zinc-400 mb-1.5">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-zinc-900 border border-zinc-850 focus:border-zinc-750 rounded-xl py-2 px-3 text-sm text-zinc-100 placeholder-zinc-700 outline-none transition-colors"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-primary hover:bg-primary/90 text-white font-semibold py-2.5 rounded-xl transition-all cursor-pointer flex items-center justify-center gap-2 mt-6 disabled:opacity-50 text-sm shadow-md"
            >
              {loading ? (
                <span className="material-symbols-outlined animate-spin text-lg" style={{ animationDuration: '2s' }}>progress_activity</span>
              ) : isLogin ? (
                'Continue'
              ) : (
                'Create Account'
              )}
            </button>
          </form>

          <div className="mt-6 text-center border-t border-zinc-900 pt-4">
            <p className="text-xs text-zinc-450">
              {isLogin ? "Don't have an account?" : 'Already have an account?'}
              <button
                onClick={() => {
                  setIsLogin(!isLogin);
                  setError('');
                }}
                className="text-primary font-semibold ml-1.5 hover:underline focus:outline-none cursor-pointer"
              >
                {isLogin ? 'Sign up' : 'Log in'}
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
