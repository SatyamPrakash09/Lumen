const BASE_URL = import.meta.env.VITE_API || (
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000/api/v1'
    : 'https://lumen-ri0b.onrender.com/api/v1'
);

let isRefreshing = false;
let refreshSubscribers = [];

function subscribeTokenRefresh(cb) {
  refreshSubscribers.push(cb);
}

function onRefreshed() {
  refreshSubscribers.forEach((cb) => cb());
  refreshSubscribers = [];
}

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  options.credentials = 'include';
  
  if (options.body && !(options.body instanceof FormData)) {
    options.headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
  }

  const response = await fetch(url, options);
  
  if (response.status === 401 && path !== '/auth/login' && path !== '/auth/register' && path !== '/auth/refresh') {
    if (!isRefreshing) {
      isRefreshing = true;
      try {
        await api.refreshToken();
        isRefreshing = false;
        onRefreshed();
      } catch (err) {
        isRefreshing = false;
        refreshSubscribers = [];
        throw new Error('Session expired. Please log in again.', { cause: err });
      }
    }

    return new Promise((resolve, reject) => {
      subscribeTokenRefresh(() => {
        fetch(url, options)
          .then((res) => {
            if (!res.ok) {
              return res.json().then(
                (err) => reject(new Error(err.detail || 'Request failed after refresh')),
                () => reject(new Error('Request failed after refresh'))
              );
            }
            resolve(res.json());
          })
          .catch(reject);
      });
    });
  }
  
  if (!response.ok) {
    let errorDetail = 'An error occurred';
    try {
      const err = await response.json();
      errorDetail = err.detail || errorDetail;
    } catch {
      // Ignore JSON parse error
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export const api = {
  // Auth
  async register({ email, password, firstName, lastName, niatId }) {
    return request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        first_name: firstName,
        last_name: lastName || null,
        username: niatId,
      }),
    });
  },

  async login({ email, password, niatId }) {
    const payload = {};
    if (email) payload.email = email;
    if (niatId) payload.username = niatId;
    payload.password = password;

    return request('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async logout() {
    return request('/auth/logout', {
      method: 'POST',
    });
  },

  async getCurrentUser() {
    return request('/auth/me', {
      method: 'GET',
    });
  },

  async refreshToken() {
    return request('/auth/refresh', {
      method: 'POST',
    });
  },

  // Sessions
  async listSessions() {
    return request('/sessions/', {
      method: 'GET',
    });
  },

  async createSession(title) {
    return request('/sessions/', {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  },

  async deleteSession(sessionId) {
    return request(`/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  },

  // Documents
  async uploadDocuments(sessionId, files) {
    const formData = new FormData();
    for (const file of files) {
      formData.append('files', file);
    }
    return request(`/sessions/${sessionId}/documents`, {
      method: 'POST',
      body: formData,
    });
  },

  async listDocuments(sessionId) {
    return request(`/sessions/${sessionId}/documents`, {
      method: 'GET',
    });
  },

  // Messages
  async getMessages(sessionId) {
    return request(`/sessions/${sessionId}/messages`, {
      method: 'GET',
    });
  },
};

// Async Generator for NDJSON streaming
export async function* streamAgentResponse(sessionId, query) {
  let response = await fetch(`${BASE_URL}/sessions/${sessionId}/agent/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
    credentials: 'include',
  });

  if (response.status === 401) {
    try {
      await api.refreshToken();
      response = await fetch(`${BASE_URL}/sessions/${sessionId}/agent/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query }),
        credentials: 'include',
      });
    } catch {
      throw new Error('Session expired. Please log in again.');
    }
  }

  if (!response.ok) {
    let errorDetail = 'Connection failed';
    try {
      const err = await response.json();
      errorDetail = err.detail || errorDetail;
    } catch {
      // Ignore JSON parse error
    }
    throw new Error(errorDetail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep the last partial line in the buffer

    for (const line of lines) {
      if (line.trim()) {
        try {
          yield JSON.parse(line);
        } catch (e) {
          console.error('Failed to parse line:', line, e);
        }
      }
    }
  }

  if (buffer.trim()) {
    try {
      yield JSON.parse(buffer);
    } catch (e) {
      console.error('Failed to parse trailing buffer:', buffer, e);
    }
  }
}
