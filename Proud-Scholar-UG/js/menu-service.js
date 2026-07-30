(function () {
  class MenuService {
    constructor(tokenService) {
      this.tokenService = tokenService;
    }

    normalizeMenu(payload) {
      const dashboard = payload?.dashboard || {};
      const menu = Array.isArray(payload?.menu) ? payload.menu : [];
      return {
        dashboard,
        menu: menu.map((item) => ({
          ...item,
          id: item.id || `${item.name}-${Math.random().toString(36).slice(2, 8)}`,
          route: item.route || `/dashboard/${this.normalizeSlug(item.name)}`,
          children: Array.isArray(item.children) ? item.children : [],
        })),
      };
    }

    flattenMenu(menuItems) {
      return menuItems.reduce((acc, item) => {
        acc.push(item);
        if (Array.isArray(item.children) && item.children.length) {
          acc.push(...this.flattenMenu(item.children));
        }
        return acc;
      }, []);
    }

    getMenuRoutes(menuItems) {
      return this.flattenMenu(menuItems).map((item) => this.normalizeRoute(item.route));
    }

    normalizeRoute(route) {
      if (!route) {
        return '/';
      }
      const cleaned = String(route).trim();
      if (!cleaned) {
        return '/';
      }
      return cleaned.startsWith('/') ? cleaned : `/${cleaned}`;
    }

    matchesRoute(route, candidate) {
      const normalizedRoute = this.normalizeRoute(route);
      const normalizedCandidate = this.normalizeRoute(candidate);
      return normalizedRoute === normalizedCandidate;
    }

    normalizeSlug(value) {
      return String(value || 'dashboard').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    }
  }

  window.MenuService = MenuService;
})();
