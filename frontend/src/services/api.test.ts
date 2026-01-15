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

    it('should handle unknown errors', async () => {
      vi.mocked(fetch).mockRejectedValueOnce('Unknown error type');

      const result = await api.get('/api/test');

      expect(result.success).toBe(false);
      expect(result.error).toBe('Unknown error');
    });
  });
});
