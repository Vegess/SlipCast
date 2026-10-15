declare global {
  interface Window { PLOTLINE_CONFIG?: { apiUrl?: string } }
}

export const API_URL = (window.PLOTLINE_CONFIG?.apiUrl || 'http://localhost:8000').replace(/\/$/, '') + '/api';
