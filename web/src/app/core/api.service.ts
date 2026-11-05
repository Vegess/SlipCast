import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { API_URL } from './config';

export function errorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) return "Can't reach the SlipCast API. Check that the backend is running.";
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail[0]?.msg) {
      const field = detail[0].loc?.slice(-1)[0];
      return field ? `${field}: ${detail[0].msg}` : detail[0].msg;
    }
    if (err.status >= 500) return 'The server had a problem. Try again shortly.';
  }
  return 'Something went wrong. Try again.';
}

/** Small promise-based wrapper: components await calls and show errorMessage() on failure. */
@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);

  get<T>(path: string, params?: Record<string, string>): Promise<T> {
    return firstValueFrom(this.http.get<T>(API_URL + path, { params: new HttpParams({ fromObject: params ?? {} }) }));
  }
  post<T>(path: string, body: unknown = {}): Promise<T> {
    return firstValueFrom(this.http.post<T>(API_URL + path, body));
  }
  patch<T>(path: string, body: unknown): Promise<T> {
    return firstValueFrom(this.http.patch<T>(API_URL + path, body));
  }
  /** Downloads an authenticated file and hands it to the browser to save. */
  async download(path: string, fallbackName: string): Promise<void> {
    const res = await firstValueFrom(this.http.get(API_URL + path, { responseType: 'blob', observe: 'response' }));
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? fallbackName;
    const url = URL.createObjectURL(res.body!);
    const a = document.createElement('a');
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  delete(path: string): Promise<unknown> {
    return firstValueFrom(this.http.delete(API_URL + path));
  }
}
