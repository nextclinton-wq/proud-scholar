(function () {
  if (!window.TokenService || !window.APIClient || !window.AuthenticationService || !window.DashboardService || !window.MenuService || !window.RouteGuard || !window.ThemeService) {
    return;
  }

  const tokenService = window.TokenService;
  const apiClient = new window.APIClient('/api/v1', tokenService);
  const authService = new window.AuthenticationService(apiClient, tokenService);
  const dashboardService = new window.DashboardService(apiClient);
  const menuService = new window.MenuService(tokenService);
  const routeGuard = new window.RouteGuard(menuService);
  const themeService = new window.ThemeService();

  const state = {
    menu: [],
    dashboard: {},
    activeRoute: '/',
    theme: { mode: 'light' },
  };

  function mountShell() {
    if (document.querySelector('.app-shell')) {
      return;
    }

    document.body.innerHTML = `
      <div class="app-shell">
        <aside class="sidebar" aria-label="Primary navigation">
          <div class="brand">
            <div class="brand-mark">PS</div>
            <div>
              <div class="brand-title">Proud Scholar UG</div>
              <div class="brand-subtitle">Dynamic dashboard</div>
            </div>
          </div>
          <div class="user-card" id="userCard">Loading…</div>
          <nav class="menu" id="sidebarMenu"></nav>
        </aside>
        <div class="backdrop" data-sidebar-close></div>
        <div class="main-area">
          <header class="topbar">
            <button class="icon-button" type="button" data-sidebar-toggle aria-label="Toggle sidebar">
              <span></span><span></span><span></span>
            </button>
            <div class="topbar-search" role="search">
              <span aria-hidden="true">⌕</span>
              <input type="search" placeholder="Search menu items" aria-label="Search menu" />
            </div>
            <div class="topbar-actions">
              <button class="pill-button" type="button" data-theme-toggle>Toggle color scheme</button>
              <button class="icon-chip" type="button" id="logoutButton" aria-label="Logout">⎋</button>
            </div>
          </header>
          <main class="content" id="dashboard"></main>
        </div>
      </div>
    `;
    document.body.style.margin = '0';
    document.body.style.minHeight = '100vh';
  }

  function getContextElements() {
    return {
      appShell: document.querySelector('.app-shell'),
      sidebarMenu: document.querySelector('#sidebarMenu'),
      content: document.querySelector('#dashboard'),
      userCard: document.querySelector('#userCard'),
      brandTitle: document.querySelector('.brand-title'),
      brandSubtitle: document.querySelector('.brand-subtitle'),
      searchInput: document.querySelector('.topbar-search input'),
      themeToggle: document.querySelector('[data-theme-toggle]'),
      sidebarToggle: document.querySelector('[data-sidebar-toggle]'),
      backdrop: document.querySelector('[data-sidebar-close]'),
      logoutButton: document.querySelector('#logoutButton'),
    };
  }

  function renderLoader(content) {
    content.innerHTML = '<section class="app-loader">Loading dashboard…</section>';
  }

  function setError(message, status = 'error') {
    const elements = getContextElements();
    if (!elements.content) {
      return;
    }
    elements.content.innerHTML = `
      <section class="error-card">
        <p class="eyebrow">${status.toUpperCase()}</p>
        <h2>${message}</h2>
        <p>Try refreshing the page or signing in again.</p>
      </section>
    `;
  }

  function setSidebarOpen(isOpen) {
    document.querySelector('.app-shell')?.classList.toggle('sidebar-open', isOpen);
  }

  function setSidebarCollapsed(isCollapsed) {
    document.querySelector('.app-shell')?.classList.toggle('sidebar-collapsed', isCollapsed);
  }

  function renderSidebar(menuItems, elements) {
    if (!elements.sidebarMenu) {
      return;
    }
    elements.sidebarMenu.innerHTML = '';

    const globalItems = [
      { name: 'My Profile', route: '/profile' },
      { name: 'Change Password', route: '/change-password' },
      { name: 'Notifications', route: '/notifications' },
      { name: 'Help', route: '/help' },
      { name: 'Logout', route: '/logout' },
    ];

    const buildItem = (item) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'menu-group';
      const link = document.createElement('a');
      link.className = 'menu-item';
      link.href = item.route || '#';
      link.innerHTML = `<span>${item.name}</span><strong>${Array.isArray(item.children) && item.children.length ? '▾' : ''}</strong>`;
      link.addEventListener('click', (event) => {
        event.preventDefault();
        if (item.route === '/logout') {
          authService.logout().finally(() => {
            window.location.href = '/';
          });
          return;
        }
        state.activeRoute = item.route;
        renderRoute(item.route);
        if (window.innerWidth < 980) {
          setSidebarOpen(false);
        }
      });
      wrapper.appendChild(link);
      if (Array.isArray(item.children) && item.children.length) {
        const children = document.createElement('div');
        children.className = 'menu-submenu';
        item.children.forEach((child) => children.appendChild(buildItem(child)));
        wrapper.appendChild(children);
      }
      return wrapper;
    };

    globalItems.forEach((item) => elements.sidebarMenu.appendChild(buildItem(item)));
    menuItems.forEach((item) => elements.sidebarMenu.appendChild(buildItem(item)));
  }

  function renderDashboardShell(elements) {
    const user = tokenService.getUser() || {};
    if (elements.brandTitle) {
      elements.brandTitle.textContent = state.dashboard.name || 'Proud Scholar UG';
    }
    if (elements.brandSubtitle) {
      elements.brandSubtitle.textContent = state.dashboard.description || 'Dynamic dashboard';
    }
    if (elements.userCard) {
      elements.userCard.innerHTML = `
        <img src="https://adminlte.io/themes/v4/assets/img/user2-160x160.jpg" alt="${user.username || 'User'}" />
        <div>
          <p>${user.username || 'User'}</p>
          <span>${state.dashboard.name || 'Dashboard User'}</span>
        </div>
      `;
    }
  }

  function renderRoute(route) {
    const normalizedRoute = route || '/';
    const allowed = routeGuard.canAccess(normalizedRoute, state.menu) || ['/', '/profile', '/change-password', '/notifications', '/help', '/logout', '/dashboard'].includes(normalizedRoute);
    if (!allowed) {
      setError('You do not have access to this feature.', '403');
      return;
    }

    const elements = getContextElements();
    const routeLabel = normalizedRoute.replace(/^\//, '').replace(/-/g, ' ') || 'dashboard';
    if (!elements.content) {
      return;
    }
    elements.content.innerHTML = `
      <section class="hero card">
        <div>
          <p class="eyebrow">${state.dashboard.name || 'Dashboard'}</p>
          <h1>${routeLabel}</h1>
          <p class="hero-copy">${state.dashboard.description || 'This section is rendered from backend metadata.'}</p>
        </div>
        <div class="hero-metric">
          <span>Active Route</span>
          <strong>${normalizedRoute}</strong>
          <small>${state.dashboard.welcome_message || 'Welcome to your workspace'}</small>
        </div>
      </section>
      <section class="stats-grid" aria-label="Dashboard overview">
        <article class="stat-card stat-blue"><div><p>Menu Items</p><strong>${state.menu.length}</strong></div><span>●</span></article>
        <article class="stat-card stat-green"><div><p>Dashboard</p><strong>${state.dashboard.name || 'Custom'}</strong></div><span>●</span></article>
        <article class="stat-card stat-amber"><div><p>Theme</p><strong>${state.theme?.mode || 'light'}</strong></div><span>●</span></article>
      </section>
    `;
  }

  function resolveRoute(pathname) {
    const parts = pathname.split('/').filter(Boolean);
    if (parts[0] === 'dashboard' && parts[1]) {
      return `/dashboard/${parts[1]}`;
    }
    return pathname || '/';
  }

  async function loadDashboard(route) {
    const elements = getContextElements();
    renderLoader(elements.content);
    try {
      const menuPayload = await dashboardService.getMenu();
      const normalized = menuService.normalizeMenu(menuPayload);
      state.menu = normalized.menu;
      state.dashboard = normalized.dashboard;
      state.theme = { mode: 'light' };
      themeService.applyTheme(state.theme);
      renderDashboardShell(elements);
      renderSidebar(normalized.menu, elements);
      renderRoute(route);
    } catch (error) {
      setError(error.message || 'Unable to load dashboard.', '500');
    }
  }

  async function initialize() {
    mountShell();
    const elements = getContextElements();
    if (!authService.isAuthenticated()) {
      window.location.href = '/';
      return;
    }

    try {
      const profile = await authService.getProfile();
      tokenService.setUser(profile);
      await loadDashboard(resolveRoute(window.location.pathname));
    } catch (error) {
      setError(error.message || 'Authentication failed.', '401');
    }

    elements.sidebarToggle?.addEventListener('click', () => {
      const isCollapsed = document.querySelector('.app-shell')?.classList.contains('sidebar-collapsed');
      setSidebarCollapsed(!isCollapsed);
    });

    elements.backdrop?.addEventListener('click', () => setSidebarOpen(false));
    elements.themeToggle?.addEventListener('click', () => {
      document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    });
    elements.logoutButton?.addEventListener('click', () => {
      authService.logout().finally(() => {
        window.location.href = '/';
      });
    });
    elements.searchInput?.addEventListener('input', (event) => {
      const term = event.target.value.toLowerCase();
      document.querySelectorAll('.menu-item').forEach((item) => {
        item.style.display = item.textContent.toLowerCase().includes(term) ? '' : 'none';
      });
    });
  }

  initialize();
})();
