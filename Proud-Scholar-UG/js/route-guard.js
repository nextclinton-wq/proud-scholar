(function () {
  class RouteGuard {
    constructor(menuService) {
      this.menuService = menuService;
    }

    canAccess(route, menuItems) {
      const routes = this.menuService.getMenuRoutes(menuItems);
      return routes.some((itemRoute) => this.menuService.matchesRoute(route, itemRoute));
    }
  }

  window.RouteGuard = RouteGuard;
})();
