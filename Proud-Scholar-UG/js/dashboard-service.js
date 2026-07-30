(function () {
  class DashboardService {
    constructor(apiClient) {
      this.apiClient = apiClient;
    }

    async getMenu() {
      const result = await this.apiClient.get('/dashboard/menu/');
      return {
        dashboard: result.dashboard || {},
        menu: Array.isArray(result.menu) ? result.menu : [],
      };
    }

    async getDashboardByUrl(slug) {
      return this.apiClient.get(`/dashboard/by-url/${encodeURIComponent(slug)}`);
    }
  }

  window.DashboardService = DashboardService;
})();
