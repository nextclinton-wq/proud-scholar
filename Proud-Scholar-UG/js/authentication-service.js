(function () {
  class AuthenticationService {
    constructor(apiClient, tokenService = window.TokenService) {
      this.apiClient = apiClient;
      this.tokenService = tokenService;
    }

    async login({ username, password, email }) {
      const payload = email ? { email, password } : { username, password };
      const result = await this.apiClient.post('/auth/login', payload);
      if (result.access) {
        this.tokenService.setAccessToken(result.access);
      }
      if (result.refresh) {
        this.tokenService.setRefreshToken(result.refresh);
      }
      if (result.user) {
        this.tokenService.setUser(result.user);
      }
      return result;
    }

    async refreshToken() {
      const result = await this.apiClient.refreshToken();
      return result;
    }

    async getProfile() {
      const result = await this.apiClient.get('/auth/me');
      this.tokenService.setUser(result);
      return result;
    }

    async updateProfile(payload = {}, avatarFile = null) {
      const formData = new FormData();
      Object.entries(payload).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          formData.append(key, value);
        }
      });
      if (avatarFile instanceof File) {
        formData.append('avatar', avatarFile);
      }
      const result = await this.apiClient.post('/auth/profile/update', formData, { formData: true });
      this.tokenService.setUser(result);
      return result;
    }

    async changePassword(payload) {
      return this.apiClient.post('/auth/password/change', payload);
    }

    async updatePreferences(payload) {
      return this.apiClient.post('/auth/preferences', payload);
    }

    async setupMfa(payload) {
      return this.apiClient.post('/auth/mfa/setup', payload);
    }

    async verifyMfa(payload) {
      const result = await this.apiClient.post('/auth/mfa/verify', payload);
      if (result.access) {
        this.tokenService.setAccessToken(result.access);
      }
      if (result.refresh) {
        this.tokenService.setRefreshToken(result.refresh);
      }
      if (result.user) {
        this.tokenService.setUser(result.user);
      }
      return result;
    }

    async disableMfa(payload) {
      return this.apiClient.post('/auth/mfa/disable', payload);
    }

    async logout() {
      const refreshToken = this.tokenService.getRefreshToken();
      try {
        if (refreshToken) {
          await this.apiClient.post('/auth/logout', { refresh_token: refreshToken });
        }
      } finally {
        this.tokenService.clearAuth();
      }
    }

    isAuthenticated() {
      return this.tokenService.isAuthenticated();
    }
  }

  window.AuthenticationService = AuthenticationService;
})();
