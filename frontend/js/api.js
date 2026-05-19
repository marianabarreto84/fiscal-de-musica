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
  async del(path) {
    const r = await fetch(API_BASE + path, { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  // Last.fm
  getLfmStatus:      ()           => api.get('/lastfm/status'),
  syncLfm:           (username)   => api.post(`/lastfm/sync${username ? '?username=' + encodeURIComponent(username) : ''}`),
  syncLfmFull:       (username)   => api.post(`/lastfm/sync-full${username ? '?username=' + encodeURIComponent(username) : ''}`),
  getSyncProgress:   ()           => api.get('/lastfm/sync/progress'),
  downloadImages:    ()           => api.post('/lastfm/download-images'),

  // Scrobbles
  getScrobbles: (from, to, limit = 200, offset = 0) =>
    api.get(`/scrobbles?date_from=${from}&date_to=${to}&limit=${limit}&offset=${offset}`),
  getScrobble:    (id)        => api.get(`/scrobbles/${id}`),
  updateScrobble: (id, data)  => api.put(`/scrobbles/${id}`, data),
  deleteScrobble: (id)        => api.del(`/scrobbles/${id}`),

  // Artistas
  getArtistas: (q = '', limit = 100) =>
    api.get(`/artistas?q=${encodeURIComponent(q)}&limit=${limit}`),
  getArtista: (id) => api.get(`/artistas/${id}`),
  setArtistaImage: (id, url) => api.put(`/artistas/${id}/image`, { url }),
  downloadArtistaImage: (id) => api.post(`/artistas/${id}/download-image`),
  getPendingArtistas:   (limit = 500) => api.get(`/artistas/pending-images?limit=${limit}`),

  // Álbuns
  getAlbums: (params = {}) => {
    const qp = new URLSearchParams();
    if (params.q)            qp.set('q', params.q);
    if (params.artistaId)    qp.set('artista_id', params.artistaId);
    if (params.statusPlays)  qp.set('status_plays', params.statusPlays);
    if (params.sort)         qp.set('sort', params.sort);
    if (params.limit  != null) qp.set('limit',  params.limit);
    if (params.offset != null) qp.set('offset', params.offset);
    return api.get(`/albums?${qp.toString()}`);
  },
  getAlbum: (id) => api.get(`/albums/${id}`),
  setAlbumImage: (id, url) => api.put(`/albums/${id}/image`, { url }),
  setAlbumNotas: (id, notasMd) => api.put(`/albums/${id}/notas`, { notas_md: notasMd }),
  downloadAlbumImage: (id) => api.post(`/albums/${id}/download-image`),
  resyncAlbumTracklist: (id) => api.post(`/albums/${id}/resync-tracklist`),
  recalibrarAlbum: (id, spotifyId = null) =>
    api.post(`/albums/${id}/recalibrar`, { spotify_id: spotifyId }),
  addAlbumAlias:    (id, spotifyId)  => api.post(`/albums/${id}/aliases`, { spotify_id: spotifyId }),
  getSpotifyCandidates: (id) => api.get(`/albums/${id}/spotify-candidates`),
  removeAlbumAlias: (id, spotifyId)  => api.del(`/albums/${id}/aliases/${spotifyId}`),
  mergeAlbumInto:   (sourceId, targetId) => api.post(`/albums/${sourceId}/merge-into`, { target_album_id: targetId }),
  deleteAlbum:      (id) => api.del(`/albums/${id}`),
  findAlbumDuplicates: (id) => api.get(`/albums/${id}/duplicate-candidates`),
  getPendingAlbums:   (limit = 500) => api.get(`/albums/pending-images?limit=${limit}`),

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

  // Músicas
  mergeMusicas: (intoId, fromId) =>
    api.post('/musicas/merge', { into_id: intoId, from_id: fromId }),

  // Jobs (genérico)
  listJobs:  ()      => api.get('/jobs'),
  getJob:    (name)  => api.get(`/jobs/${name}`),
  startJob:  (name)  => api.post(`/jobs/${name}/start`),

  // Projetos
  getProjetos:        ()                      => api.get('/projetos'),
  getProjeto:         (id)                    => api.get(`/projetos/${id}`),
  createProjeto:      (data)                  => api.post('/projetos', data),
  updateProjeto:      (id, data)              => api.put(`/projetos/${id}`, data),
  deleteProjeto:      (id)                    => api.del(`/projetos/${id}`),
  addAlbumsToProjeto: (id, albumIds)          => api.post(`/projetos/${id}/albums`, { album_ids: albumIds }),
  removeAlbumFromProjeto: (id, albumId)       => api.del(`/projetos/${id}/albums/${albumId}`),
};
