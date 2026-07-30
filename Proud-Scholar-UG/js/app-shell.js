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
    profile: null,
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
              <button class="pill-button" type="button" data-fullscreen-toggle aria-label="Toggle full screen">Full screen</button>
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
      fullscreenToggle: document.querySelector('[data-fullscreen-toggle]'),
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

  function renderProfileSettings() {
    const elements = getContextElements();
    const profile = state.profile || tokenService.getUser() || {};
    const avatarSrc = profile.avatar || 'https://adminlte.io/themes/v4/assets/img/user2-160x160.jpg';
    elements.content.innerHTML = `
      <section class="hero card">
        <div>
          <p class="eyebrow">Account</p>
          <h1>Profile settings</h1>
          <p class="hero-copy">Keep your workspace profile current, update your password, and control MFA and notifications from one place.</p>
        </div>
        <div class="hero-metric">
          <span>Account status</span>
          <strong>${profile.mfa_enabled ? 'MFA enabled' : 'MFA disabled'}</strong>
          <small>${profile.notifications_enabled ? 'Notifications enabled' : 'Notifications muted'}</small>
        </div>
      </section>
      <div class="settings-grid">
        <section class="card settings-card">
          <div class="section-head"><h2>Profile details</h2><span class="badge">Editable</span></div>
          <form id="profileSettingsForm" class="settings-form">
            <div class="avatar-row">
              <img class="avatar large" src="${avatarSrc}" alt="${profile.username || 'User'}" />
              <label class="file-field">
                <span>Upload profile picture</span>
                <input type="file" name="avatar" accept="image/*" />
              </label>
            </div>
            <div class="field-grid">
              <label class="field">
                <span>Username</span>
                <input type="text" name="username" value="${profile.username || ''}" />
              </label>
              <label class="field">
                <span>Email</span>
                <input type="email" name="email" value="${profile.email || ''}" />
              </label>
              <label class="field">
                <span>First name</span>
                <input type="text" name="first_name" value="${profile.first_name || ''}" />
              </label>
              <label class="field">
                <span>Last name</span>
                <input type="text" name="last_name" value="${profile.last_name || ''}" />
              </label>
            </div>
            <label class="toggle-row">
              <input type="checkbox" name="notifications_enabled" ${profile.notifications_enabled ? 'checked' : ''} />
              <span>Enable desktop and email notifications</span>
            </label>
            <div class="form-actions">
              <button class="primary-action" type="submit">Save profile</button>
              <div id="profileFeedback" class="feedback-message"></div>
            </div>
          </form>
        </section>
        <section class="card settings-card">
          <div class="section-head"><h2>Security</h2><span class="badge">Password</span></div>
          <form id="passwordSettingsForm" class="settings-form">
            <label class="field"><span>Current password</span><input type="password" name="current_password" required /></label>
            <div class="field-grid">
              <label class="field"><span>New password</span><input type="password" name="new_password" required /></label>
              <label class="field"><span>Confirm new password</span><input type="password" name="new_password_confirm" required /></label>
            </div>
            <div class="form-actions">
              <button class="primary-action" type="submit">Change password</button>
              <div id="passwordFeedback" class="feedback-message"></div>
            </div>
          </form>
        </section>
        <section class="card settings-card">
          <div class="section-head"><h2>Multi-factor authentication</h2><span class="badge">${profile.mfa_enabled ? 'Enabled' : 'Disabled'}</span></div>
          ${profile.mfa_enabled ? `
            <form id="mfaDisableForm" class="settings-form">
              <label class="field"><span>Confirm password to disable MFA</span><input type="password" name="password" required /></label>
              <div class="form-actions"><button class="tool-button" type="submit">Disable MFA</button><div id="mfaFeedback" class="feedback-message"></div></div>
            </form>
          ` : `
            <form id="mfaEnableForm" class="settings-form">
              <label class="field"><span>Confirm password to enable MFA</span><input type="password" name="password" required /></label>
              <label class="field"><span>Device name</span><input type="text" name="device_name" placeholder="Google Authenticator" /></label>
              <div class="form-actions"><button class="primary-action" type="submit">Enable MFA</button><div id="mfaFeedback" class="feedback-message"></div></div>
            </form>
          `}
        </section>
      </div>
    `;

    const profileForm = elements.content.querySelector('#profileSettingsForm');
    const passwordForm = elements.content.querySelector('#passwordSettingsForm');
    const mfaForm = elements.content.querySelector('#mfaEnableForm') || elements.content.querySelector('#mfaDisableForm');

    profileForm?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const feedback = elements.content.querySelector('#profileFeedback');
      const fileInput = profileForm.querySelector('input[type="file"]');
      const payload = {
        username: profileForm.querySelector('input[name="username"]').value,
        email: profileForm.querySelector('input[name="email"]').value,
        first_name: profileForm.querySelector('input[name="first_name"]').value,
        last_name: profileForm.querySelector('input[name="last_name"]').value,
        notifications_enabled: profileForm.querySelector('input[name="notifications_enabled"]').checked,
      };
      try {
        const updated = await authService.updateProfile(payload, fileInput?.files?.[0] || null);
        state.profile = updated;
        tokenService.setUser(updated);
        feedback.textContent = 'Profile updated successfully.';
        feedback.classList.add('success');
        renderProfileSettings();
      } catch (error) {
        feedback.textContent = error.message || 'Unable to update profile.';
        feedback.classList.add('error');
      }
    });

    passwordForm?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const feedback = elements.content.querySelector('#passwordFeedback');
      const payload = {
        current_password: passwordForm.querySelector('input[name="current_password"]').value,
        new_password: passwordForm.querySelector('input[name="new_password"]').value,
        new_password_confirm: passwordForm.querySelector('input[name="new_password_confirm"]').value,
      };
      try {
        await authService.changePassword(payload);
        feedback.textContent = 'Password updated successfully.';
        feedback.classList.add('success');
        passwordForm.reset();
      } catch (error) {
        feedback.textContent = error.message || 'Unable to update password.';
        feedback.classList.add('error');
      }
    });

    mfaForm?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const feedback = elements.content.querySelector('#mfaFeedback');
      const form = event.currentTarget;
      try {
        if (form.id === 'mfaEnableForm') {
          const payload = {
            password: form.querySelector('input[name="password"]').value,
            device_name: form.querySelector('input[name="device_name"]').value || 'Google Authenticator',
          };
          const setup = await authService.setupMfa(payload);
          feedback.textContent = `${setup.otp_instructions || 'Scan the QR and enter the 6-digit code.'}`;
          feedback.classList.add('success');
          const code = window.prompt('Enter the 6-digit MFA code from your authenticator app');
          if (code) {
            const verified = await authService.verifyMfa({ username: profile.username, code });
            state.profile = { ...(state.profile || {}), mfa_enabled: Boolean(verified.access) };
            renderProfileSettings();
          }
        } else {
          const payload = { password: form.querySelector('input[name="password"]').value };
          const disabled = await authService.disableMfa(payload);
          state.profile = disabled;
          feedback.textContent = 'MFA disabled successfully.';
          feedback.classList.add('success');
          renderProfileSettings();
        }
      } catch (error) {
        feedback.textContent = error.message || 'Unable to update MFA.';
        feedback.classList.add('error');
      }
    });
  }

  function renderStaffManagement() {
    const elements = getContextElements();
    elements.content.innerHTML = `
      <section class="hero card">
        <div>
          <p class="eyebrow">Administration</p>
          <h1>Staff management</h1>
          <p class="hero-copy">Create staff accounts, update their details, block access, and send password reset emails for your team.</p>
        </div>
        <div class="hero-metric">
          <span>Manage</span>
          <strong>Staff</strong>
          <small>Tenant-scoped access for your registered staff.</small>
        </div>
      </section>
      <section class="card settings-card">
        <div class="section-head">
          <h2>Staff directory</h2>
          <button class="tool-button" type="button" id="staffAddButton">Add staff</button>
        </div>
        <div id="staffTable" class="staff-table"></div>
      </section>
    `;

    const table = elements.content.querySelector('#staffTable');
    const renderList = async () => {
      try {
        const staff = await authService.listStaff();
        if (!staff.length) {
          table.innerHTML = '<p class="empty-state">No staff members yet.</p>';
          return;
        }
        table.innerHTML = `
          <div class="table-shell">
            <table class="data-table">
              <thead><tr><th>Name</th><th>Email</th><th>Department</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                ${staff.map((member) => `
                  <tr>
                    <td>${member.first_name || member.username} ${member.last_name || ''}</td>
                    <td>${member.email}</td>
                    <td>${member.department || '—'}</td>
                    <td>${member.is_active ? 'Active' : 'Blocked'}</td>
                    <td>
                      <div class="table-actions">
                        <button class="tool-button" data-edit="${member.id}" type="button">Edit</button>
                        <button class="tool-button" data-block="${member.id}" type="button">${member.is_active ? 'Block' : 'Unblock'}</button>
                        <button class="tool-button" data-reset="${member.id}" type="button">Reset password</button>
                      </div>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `;
        table.querySelectorAll('[data-edit]').forEach((button) => {
          button.addEventListener('click', () => {
            const id = button.getAttribute('data-edit');
            const member = staff.find((item) => item.id === id);
            if (!member) return;
            const firstName = window.prompt('First name', member.first_name || '');
            const lastName = window.prompt('Last name', member.last_name || '');
            const department = window.prompt('Department', member.department || '');
            if (firstName !== null && lastName !== null && department !== null) {
              authService.updateStaff(id, { first_name: firstName, last_name: lastName, department }).then(() => renderList()).catch(() => window.alert('Unable to update staff member.'));
            }
          });
        });
        table.querySelectorAll('[data-block]').forEach((button) => {
          button.addEventListener('click', () => {
            const id = button.getAttribute('data-block');
            const member = staff.find((item) => item.id === id);
            if (!member) return;
            authService.blockStaff(id, { blocked: member.is_active }).then(() => renderList()).catch(() => window.alert('Unable to change staff status.'));
          });
        });
        table.querySelectorAll('[data-reset]').forEach((button) => {
          button.addEventListener('click', () => {
            const id = button.getAttribute('data-reset');
            authService.resetStaffPassword(id).then(() => window.alert('Password reset email sent.')).catch(() => window.alert('Unable to send password reset email.'));
          });
        });
      } catch (error) {
        table.innerHTML = `<p class="empty-state">${error.message || 'Unable to load staff.'}</p>`;
      }
    };

    renderList();

    elements.content.querySelector('#staffAddButton')?.addEventListener('click', async () => {
      const username = window.prompt('Username');
      const email = window.prompt('Email');
      const password = window.prompt('Password');
      const passwordConfirm = window.prompt('Confirm password');
      const firstName = window.prompt('First name');
      const lastName = window.prompt('Last name');
      const department = window.prompt('Department');
      if (!username || !email || !password || !passwordConfirm) {
        window.alert('Username, email, and passwords are required.');
        return;
      }
      try {
        await authService.createStaff({ username, email, password, password_confirm: passwordConfirm, first_name: firstName || '', last_name: lastName || '', department: department || '' });
        await renderList();
      } catch (error) {
        window.alert(error.message || 'Unable to create staff account.');
      }
    });
  }

  function renderNotificationsSettings() {
    const elements = getContextElements();
    const profile = state.profile || tokenService.getUser() || {};
    elements.content.innerHTML = `
      <section class="hero card">
        <div>
          <p class="eyebrow">Preferences</p>
          <h1>Notifications</h1>
          <p class="hero-copy">Choose whether this workspace should notify you about activity and updates.</p>
        </div>
        <div class="hero-metric">
          <span>Current preference</span>
          <strong>${profile.notifications_enabled ? 'Enabled' : 'Disabled'}</strong>
          <small>Updates will be delivered according to this setting.</small>
        </div>
      </section>
      <section class="card settings-card">
        <form id="notificationsForm" class="settings-form">
          <label class="toggle-row">
            <input type="checkbox" name="notifications_enabled" ${profile.notifications_enabled ? 'checked' : ''} />
            <span>Allow notifications for account activity</span>
          </label>
          <div class="form-actions">
            <button class="primary-action" type="submit">Save preferences</button>
            <div id="notificationsFeedback" class="feedback-message"></div>
          </div>
        </form>
      </section>
    `;

    const form = elements.content.querySelector('#notificationsForm');
    form?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const feedback = elements.content.querySelector('#notificationsFeedback');
      try {
        const updated = await authService.updatePreferences({ notifications_enabled: form.querySelector('input[name="notifications_enabled"]').checked });
        state.profile = updated;
        feedback.textContent = 'Notification preferences updated.';
        feedback.classList.add('success');
      } catch (error) {
        feedback.textContent = error.message || 'Unable to update preferences.';
        feedback.classList.add('error');
      }
    });
  }

  function renderPasswordSettings() {
    const elements = getContextElements();
    elements.content.innerHTML = `
      <section class="hero card">
        <div>
          <p class="eyebrow">Security</p>
          <h1>Change password</h1>
          <p class="hero-copy">Use a strong password to help keep your account secure.</p>
        </div>
        <div class="hero-metric">
          <span>Security tip</span>
          <strong>Stay fresh</strong>
          <small>Rotate your password if you suspect unusual activity.</small>
        </div>
      </section>
      <section class="card settings-card">
        <form id="passwordSettingsForm" class="settings-form">
          <label class="field"><span>Current password</span><input type="password" name="current_password" required /></label>
          <div class="field-grid">
            <label class="field"><span>New password</span><input type="password" name="new_password" required /></label>
            <label class="field"><span>Confirm new password</span><input type="password" name="new_password_confirm" required /></label>
          </div>
          <div class="form-actions">
            <button class="primary-action" type="submit">Change password</button>
            <div id="passwordFeedback" class="feedback-message"></div>
          </div>
        </form>
      </section>
    `;

    const form = elements.content.querySelector('#passwordSettingsForm');
    form?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const feedback = elements.content.querySelector('#passwordFeedback');
      try {
        await authService.changePassword({
          current_password: form.querySelector('input[name="current_password"]').value,
          new_password: form.querySelector('input[name="new_password"]').value,
          new_password_confirm: form.querySelector('input[name="new_password_confirm"]').value,
        });
        feedback.textContent = 'Password updated successfully.';
        feedback.classList.add('success');
        form.reset();
      } catch (error) {
        feedback.textContent = error.message || 'Unable to update password.';
        feedback.classList.add('error');
      }
    });
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

    if (normalizedRoute === '/profile') {
      renderProfileSettings();
      return;
    }
    if (normalizedRoute === '/change-password') {
      renderPasswordSettings();
      return;
    }
    if (normalizedRoute === '/notifications') {
      renderNotificationsSettings();
      return;
    }
    if (normalizedRoute === '/staff-management') {
      renderStaffManagement();
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

  function updateFullscreenButtonLabel(elements = getContextElements()) {
    if (!elements.fullscreenToggle) {
      return;
    }
    elements.fullscreenToggle.textContent = document.fullscreenElement ? 'Exit full screen' : 'Full screen';
  }

  async function loadDashboard(route) {
    const elements = getContextElements();
    renderLoader(elements.content);
    try {
      const menuPayload = await dashboardService.getMenu();
      const normalized = menuService.normalizeMenu(menuPayload);
      const extraSidebarFeatures = [
        { name: 'Staff Management', route: '/staff-management' },
        { name: 'Role Management', route: '/role-management' },
      ];
      const existingRoutes = new Set((normalized.menu || []).map((item) => item.route).filter(Boolean));
      const combinedMenu = [...normalized.menu];
      extraSidebarFeatures.forEach((item) => {
        if (!existingRoutes.has(item.route)) {
          combinedMenu.push(item);
          existingRoutes.add(item.route);
        }
      });
      state.menu = combinedMenu;
      state.dashboard = normalized.dashboard;
      state.theme = { mode: 'light' };
      themeService.applyTheme(state.theme);
      renderDashboardShell(elements);
      renderSidebar(state.menu, elements);
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
      state.profile = profile;
      tokenService.setUser(profile);
      await loadDashboard(resolveRoute(window.location.pathname));
    } catch (error) {
      setError(error.message || 'Authentication failed.', '401');
    }

    updateFullscreenButtonLabel(elements);

    elements.sidebarToggle?.addEventListener('click', () => {
      const isCollapsed = document.querySelector('.app-shell')?.classList.contains('sidebar-collapsed');
      setSidebarCollapsed(!isCollapsed);
    });

    elements.backdrop?.addEventListener('click', () => setSidebarOpen(false));
    elements.fullscreenToggle?.addEventListener('click', async () => {
      try {
        if (!document.fullscreenElement) {
          await document.documentElement.requestFullscreen?.();
        } else {
          await document.exitFullscreen?.();
        }
      } catch (error) {
        console.error('Unable to toggle full screen.', error);
      }
    });
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

    document.addEventListener('fullscreenchange', () => updateFullscreenButtonLabel(getContextElements()));
  }

  initialize();
})();
