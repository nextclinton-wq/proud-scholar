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
