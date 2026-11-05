declare global {
  interface Window { SLIPCAST_CONFIG?: { apiUrl?: string } }
}

export const API_URL = (window.SLIPCAST_CONFIG?.apiUrl || 'http://localhost:8000').replace(/\/$/, '') + '/api';
