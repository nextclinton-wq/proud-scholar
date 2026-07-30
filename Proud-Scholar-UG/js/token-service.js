(function () {
  const STORAGE_KEYS = {
    access: 'proudScholarAccessToken',
    refresh: 'proudScholarRefreshToken',
    user: 'proudScholarUser',
    menu: 'proudScholarMenu',
  };

  class TokenService {
    getAccessToken() {
      return sessionStorage.getItem(STORAGE_KEYS.access) || '';
    }

    setAccessToken(token) {
      if (token) {
        sessionStorage.setItem(STORAGE_KEYS.access, token);
        return;
      }
      sessionStorage.removeItem(STORAGE_KEYS.access);
    }

    getRefreshToken() {
      return sessionStorage.getItem(STORAGE_KEYS.refresh) || '';
    }

    setRefreshToken(token) {
      if (token) {
        sessionStorage.setItem(STORAGE_KEYS.refresh, token);
        return;
      }
      sessionStorage.removeItem(STORAGE_KEYS.refresh);
    }

    getUser() {
      try {
        return JSON.parse(sessionStorage.getItem(STORAGE_KEYS.user) || 'null');
      } catch (error) {
        return null;
      }
    }

    setUser(user) {
      if (user) {
        sessionStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
        return;
      }
      sessionStorage.removeItem(STORAGE_KEYS.user);
    }

    getStoredMenu() {
      try {
        return JSON.parse(sessionStorage.getItem(STORAGE_KEYS.menu) || 'null');
      } catch (error) {
        return null;
      }
    }

    setStoredMenu(menu) {
      if (menu) {
        sessionStorage.setItem(STORAGE_KEYS.menu, JSON.stringify(menu));
        return;
      }
      sessionStorage.removeItem(STORAGE_KEYS.menu);
    }

    clearAuth() {
      this.setAccessToken('');
      this.setRefreshToken('');
      this.setUser(null);
      this.setStoredMenu(null);
    }

    isAuthenticated() {
      return Boolean(this.getAccessToken());
    }
  }

  window.TokenService = new TokenService();
})();
