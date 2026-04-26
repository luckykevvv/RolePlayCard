import type { TaskResult } from '../../../shared/types.js';

export interface ApiRequestOptions extends RequestInit {
  timeoutMs?: number;
}

export async function apiRequest<T>(
  path: string,
  init?: ApiRequestOptions,
  apiBase = '/api',
): Promise<TaskResult<T>> {
  const timeoutRaw = init?.timeoutMs;
  const timeoutCandidate = Number(timeoutRaw ?? 60000);
  const timeoutMs = Number.isFinite(timeoutCandidate) ? Math.max(0, timeoutCandidate) : 60000;
  const controller = new AbortController();
  let didTimeout = false;
  const timeoutHandle = timeoutMs > 0
    ? window.setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, timeoutMs)
    : null;
  try {
    const response = await fetch(`${apiBase}${path}`, {
      ...init,
      signal: init?.signal ?? controller.signal,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...(init?.headers ?? {}),
      },
    });

    let payload: TaskResult<T> | null = null;
    let rawText = '';
    try {
      rawText = await response.text();
      payload = rawText ? (JSON.parse(rawText) as TaskResult<T>) : null;
    } catch {
      payload = null;
    }
    if (payload && typeof payload.success === 'boolean' && 'message' in payload) {
      return payload;
    }
    const snippet = rawText.slice(0, 200).trim();
    return {
      success: false,
      error_code: response.ok ? 'invalid_response' : 'http_error',
      message: snippet || `HTTP ${response.status}`,
      data: null,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (!didTimeout) {
        return {
          success: false,
          error_code: 'request_aborted',
          message: '请求已取消',
          data: null,
        };
      }
      return {
        success: false,
        error_code: 'request_timeout',
        message: `请求超时（>${timeoutMs}ms）`,
        data: null,
      };
    }
    return {
      success: false,
      error_code: 'network_error',
      message: error instanceof Error ? error.message : '网络请求失败',
      data: null,
    };
  } finally {
    if (timeoutHandle !== null) {
      window.clearTimeout(timeoutHandle);
    }
  }
}

export function imageSrcFromPath(pathValue: string, seed: number, apiBase = '/api'): string {
  if (!pathValue) return '';
  if (pathValue.startsWith('data:') || pathValue.startsWith('blob:') || pathValue.startsWith('http')) {
    return pathValue;
  }
  return `${apiBase}/files/image?path=${encodeURIComponent(pathValue)}&t=${seed}`;
}

export function downloadBase64Png(filename: string, imageBase64: string): void {
  const binary = atob(imageBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: 'image/png' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
