import { config } from '@/config/env';
import type { ApiResponse, GenreList } from '@/types';

/**
 * Error bodies the backend can send. The documented envelope is
 * `{success: false, error: {code, message, details}}`; the exception
 * middleware sends `{error: {code, message, details}}`; FastAPI's own
 * HTTPException and request-validation handlers send `{detail: string}` and
 * `{detail: [{loc, msg, type}]}`.
 */
interface ErrorBody {
  success?: unknown;
  error?: unknown;
  detail?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function validationItemMessage(item: unknown): string | null {
  if (!isRecord(item) || typeof item.msg !== 'string') return null;
  const loc = Array.isArray(item.loc)
    ? item.loc.filter((part) => part !== 'body' && part !== 'query' && part !== 'path')
    : [];
  return loc.length > 0 ? `${loc.join('.')}: ${item.msg}` : item.msg;
}

/**
 * Turn any backend error body into one human-readable message.
 */
export function extractErrorMessage(body: unknown, status?: number): string {
  if (isRecord(body)) {
    const { error, detail } = body as ErrorBody;
    if (typeof error === 'string' && error) return error;
    if (isRecord(error) && typeof error.message === 'string' && error.message) {
      return error.message;
    }
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map(validationItemMessage)
        .filter((message): message is string => message !== null);
      if (messages.length > 0) return messages.join('; ');
    }
  }
  return status ? `Request failed with status ${status}` : 'Unknown error';
}

/**
 * API Client for backend communication
 *
 * Handles all HTTP requests to the backend API.
 * Uses the Vite proxy in development to avoid CORS issues.
 */
class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  /**
   * Make an HTTP request to the API
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      // Parse JSON response
      const data = await response.json();

      if (isRecord(data) && data.success === true) {
        return data as unknown as ApiResponse<T>;
      }

      // Error bodies come in several shapes (see ErrorBody); normalize them so
      // callers always get `error` as a message string.
      if (response.ok === false || (isRecord(data) && data.success === false)) {
        return {
          success: false,
          data: null as T,
          error: extractErrorMessage(data, response.status),
        };
      }

      return data as ApiResponse<T>;
    } catch (error) {
      // Network error or invalid JSON
      return {
        success: false,
        data: null as T,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * GET request
   */
  async get<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  /**
   * POST request
   */
  async post<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * PUT request
   */
  async put<T>(endpoint: string, body: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  /**
   * DELETE request
   */
  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  /**
   * Distinct genres across cached games, with how many games carry each
   */
  async getGameGenres(): Promise<ApiResponse<GenreList>> {
    return this.get<GenreList>('/api/v1/games/genres');
  }
}

// Export singleton instance
export const api = new ApiClient(config.apiUrl);
