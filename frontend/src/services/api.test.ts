import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { api } from './api';

describe('ApiClient', () => {
  beforeEach(() => {
    // Mock fetch globally
    (globalThis as unknown as { fetch: typeof fetch }).fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('get', () => {
    it('should make a GET request and return data', async () => {
      const mockResponse = { success: true, data: { id: 1, name: 'Test' } };
      vi.mocked(fetch).mockResolvedValueOnce({
        json: () => Promise.resolve(mockResponse),
      } as Response);

      const result = await api.get<{ id: number; name: string }>('/api/test');

      expect(fetch).toHaveBeenCalledWith('/api/test', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      expect(result).toEqual(mockResponse);
    });

    it('should handle network errors', async () => {
      vi.mocked(fetch).mockRejectedValueOnce(new Error('Network error'));

      const result = await api.get('/api/test');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Network error');
    });
  });

  describe('post', () => {
    it('should make a POST request with body', async () => {
      const mockResponse = { success: true, data: { created: true } };
      vi.mocked(fetch).mockResolvedValueOnce({
        json: () => Promise.resolve(mockResponse),
      } as Response);

      const body = { name: 'New Item' };
      const result = await api.post('/api/items', body);

      expect(fetch).toHaveBeenCalledWith('/api/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      expect(result).toEqual(mockResponse);
    });

    it('should make a POST request without body', async () => {
      const mockResponse = { success: true, data: null };
      vi.mocked(fetch).mockResolvedValueOnce({
        json: () => Promise.resolve(mockResponse),
      } as Response);

      await api.post('/api/action');

      expect(fetch).toHaveBeenCalledWith('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: undefined,
      });
    });
  });

  describe('put', () => {
    it('should make a PUT request with body', async () => {
      const mockResponse = { success: true, data: { updated: true } };
      vi.mocked(fetch).mockResolvedValueOnce({
        json: () => Promise.resolve(mockResponse),
      } as Response);

      const body = { name: 'Updated Item' };
      const result = await api.put('/api/items/1', body);

      expect(fetch).toHaveBeenCalledWith('/api/items/1', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('delete', () => {
    it('should make a DELETE request', async () => {
      const mockResponse = { success: true, data: null };
      vi.mocked(fetch).mockResolvedValueOnce({
        json: () => Promise.resolve(mockResponse),
      } as Response);

      const result = await api.delete('/api/items/1');

      expect(fetch).toHaveBeenCalledWith('/api/items/1', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
      });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('error handling', () => {
    it('should handle JSON parse errors', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        json: () => Promise.reject(new Error('Invalid JSON')),
      } as Response);

      const result = await api.get('/api/test');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Invalid JSON');
    });

    const respond = (status: number, body: unknown) =>
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      } as Response);

    it('uses the message of the documented error envelope object', async () => {
      respond(500, {
        success: false,
        error: { code: 'INTERNAL_ERROR', message: 'Database is locked', details: {} },
        meta: { timestamp: '2026-10-24T12:00:00Z' },
      });

      const result = await api.get('/api/test');

      expect(result).toEqual({ success: false, data: null, error: 'Database is locked' });
    });

    it('uses the message of the exception middleware body (no success key)', async () => {
      respond(502, { error: { code: 'STEAM_API_ERROR', message: 'Steam is down', details: {} } });

      const result = await api.get('/api/test');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Steam is down');
    });

    it('uses an HTTPException detail string (settings ValueError -> 400)', async () => {
      respond(400, { detail: 'excluded_genres accepts at most 50 items' });

      const result = await api.put('/api/v1/settings', { excluded_genres: [] });

      expect(result.success).toBe(false);
      expect(result.error).toBe('excluded_genres accepts at most 50 items');
    });

    it('joins request-validation details with their field path (422)', async () => {
      respond(422, {
        detail: [
          {
            type: 'value_error',
            loc: ['body', 'excluded_genres'],
            msg: 'Value error, at most 50 genres',
            input: [],
          },
          { type: 'missing', loc: ['body', 'other'], msg: 'Field required' },
        ],
      });

      const result = await api.put('/api/v1/settings', { excluded_genres: [] });

      expect(result.success).toBe(false);
      expect(result.error).toBe(
        'excluded_genres: Value error, at most 50 genres; other: Field required'
      );
    });

    it('falls back to the HTTP status when the error body has no message', async () => {
      respond(503, { unexpected: true });

      const result = await api.get('/api/test');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Request failed with status 503');
    });

    it('never yields "[object Object]" from getGameGenres on an envelope error', async () => {
      respond(500, {
        success: false,
        error: { code: 'INTERNAL_ERROR', message: 'Genre query failed', details: {} },
      });

      const result = await api.getGameGenres();

      expect(fetch).toHaveBeenCalledWith('/api/v1/games/genres', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      expect(result.error).toBe('Genre query failed');
    });

    it('returns a successful getGameGenres body unchanged', async () => {
      const body = { success: true, data: { genres: [{ name: 'Action', count: 2 }] } };
      respond(200, body);

      expect(await api.getGameGenres()).toEqual(body);
    });

    it('should handle unknown errors', async () => {
      vi.mocked(fetch).mockRejectedValueOnce('Unknown error type');

      const result = await api.get('/api/test');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Unknown error');
    });
  });
});
