const API_BASE = 'http://localhost:8002/api';

const api = {
  async get(path) {
    const r = await fetch(API_BASE + path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(path, body = {}) {
    const r = await fetch(API_BASE + path, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async put(path, body = {}) {
    const r = await fetch(API_BASE + path, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  // Last.fm
  getLfmStatus:      ()           => api.get('/lastfm/status'),
  syncLfm:           (username)   => api.post(`/lastfm/sync${username ? '?username=' + encodeURIComponent(username) : ''}`),
  syncLfmFull:       (username)   => api.post(`/lastfm/sync-full${username ? '?username=' + encodeURIComponent(username) : ''}`),
  downloadImages:    (limit = 20) => api.post(`/lastfm/download-images?limit=${limit}`),

  // Scrobbles
  getScrobbles: (from, to, limit = 200, offset = 0) =>
    api.get(`/scrobbles?date_from=${from}&date_to=${to}&limit=${limit}&offset=${offset}`),

  // Artistas
  getArtistas: (q = '', limit = 100) =>
    api.get(`/artistas?q=${encodeURIComponent(q)}&limit=${limit}`),
  getArtista: (id) => api.get(`/artistas/${id}`),
  setArtistaImage: (id, url) => api.put(`/artistas/${id}/image`, { url }),

  // Álbuns
  getAlbums: (q = '', limit = 100, artistaId = null) =>
    api.get(`/albums?q=${encodeURIComponent(q)}&limit=${limit}${artistaId ? '&artista_id=' + artistaId : ''}`),
  getAlbum: (id) => api.get(`/albums/${id}`),
  setAlbumImage: (id, url) => api.put(`/albums/${id}/image`, { url }),

  // Stats
  getOverview:     ()      => api.get('/stats/overview'),
  getByYear:       ()      => api.get('/stats/by-year'),
  getByMonth:      (year)  => api.get(`/stats/by-month${year ? '?year=' + year : ''}`),
  getByDow:        ()      => api.get('/stats/by-day-of-week'),
  getTopArtistas:  (n=10)  => api.get(`/stats/top-artistas?limit=${n}`),
  getTopAlbums:    (n=10)  => api.get(`/stats/top-albums?limit=${n}`),
  getTopMusicas:   (n=20)  => api.get(`/stats/top-musicas?limit=${n}`),
  getRecent:       (n=20)  => api.get(`/stats/recent?limit=${n}`),
  getAvailableYears: ()    => api.get('/stats/available-years'),

  // Settings
  getSetting: (key)        => api.get(`/settings/${key}`),
  setSetting: (key, value) => api.put(`/settings/${key}`, { value }),
};
