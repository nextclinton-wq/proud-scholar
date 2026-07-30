(function () {
  class APIClient {
    constructor(baseUrl = '/api/v1', tokenService = window.TokenService) {
      this.baseUrl = baseUrl;
      this.tokenService = tokenService;
      this.refreshing = false;
    }

    buildHeaders(includeJson = true, extraHeaders = {}) {
      const headers = { ...extraHeaders };
      const accessToken = this.tokenService?.getAccessToken?.();
      if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`;
      }
      if (includeJson) {
        headers['Content-Type'] = 'application/json';
      }
      const csrfToken = this.getCookie('csrftoken');
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }
      return headers;
    }

    async request(path, options = {}, retry = false) {
      const url = `${this.baseUrl}${path}`;
      const response = await fetch(url, {
        credentials: 'same-origin',
        headers: this.buildHeaders(options.body !== undefined && !options.formData, options.headers || {}),
        ...options,
      });

      const payload = await response.json().catch(() => ({}));
      if (response.ok && payload.success !== false) {
        return payload.data ?? payload;
      }

      if (!retry && response.status === 401 && this.tokenService?.getRefreshToken?.()) {
        const refreshed = await this.refreshToken();
        if (refreshed) {
          return this.request(path, options, true);
        }
      }

      throw new Error(payload.message || payload.errors?.[0] || `Request failed (${response.status})`);
    }

    async get(path, options = {}) {
      return this.request(path, { ...options, method: 'GET' });
    }

    async post(path, data, options = {}) {
      const body = data instanceof FormData ? data : JSON.stringify(data ?? {});
      return this.request(path, { ...options, method: 'POST', body });
    }

    async put(path, data, options = {}) {
      return this.request(path, { ...options, method: 'PUT', body: JSON.stringify(data ?? {}) });
    }

    async delete(path, options = {}) {
      return this.request(path, { ...options, method: 'DELETE' });
    }

    async refreshToken() {
      const refreshToken = this.tokenService?.getRefreshToken?.();
      if (!refreshToken || this.refreshing) {
        return false;
      }
      this.refreshing = true;
      try {
        const result = await this.post('/auth/refresh-token', { refresh_token: refreshToken });
        if (result.access) {
          this.tokenService?.setAccessToken?.(result.access);
        }
        if (result.refresh) {
          this.tokenService?.setRefreshToken?.(result.refresh);
        }
        return true;
      } catch (error) {
        this.tokenService?.clearAuth?.();
        return false;
      } finally {
        this.refreshing = false;
      }
    }

    getCookie(name) {
      const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
      return match ? decodeURIComponent(match[2]) : null;
    }
  }

  window.APIClient = APIClient;
})();
