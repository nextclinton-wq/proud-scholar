const appShell = document.querySelector('.app-shell');
const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
const backdrop = document.querySelector('[data-sidebar-close]');
const themeToggle = document.querySelector('[data-theme-toggle]');
const fullscreenToggle = document.querySelector('[data-fullscreen-toggle]');
const dropdownButtons = document.querySelectorAll('[data-panel-toggle]');
const sidebarMenuToggle = document.querySelector('[data-menu-toggle="dashboards"]');
const sidebarSubmenu = document.querySelector('[data-menu="dashboards"]');
const sidebarSubmenuLinks = Array.from(document.querySelectorAll('.menu-subitem'));
const sidebarMenu = document.querySelector('.menu');
const createDashboardButton = document.querySelector('[data-create-dashboard]');
const creatorPanel = document.querySelector('[data-creator-panel]');
const creatorCloseButton = document.querySelector('[data-creator-close]');
const dashboardForm = document.querySelector('[data-dashboard-form]');
const cardToggleButtons = document.querySelectorAll('[data-card-toggle]');
const chatForm = document.querySelector('[data-chat-form]');
const chatThread = document.querySelector('.chat-thread');
const chartBars = Array.from(document.querySelectorAll('.chart-bars span'));
const chartSection = document.querySelector('#sales');
const widgetsSection = document.querySelector('#widgets');
const pagesSection = document.querySelector('#pages');
const menuLinks = Array.from(document.querySelectorAll('.menu-item[href], .menu-subitem'));
const toastStack = document.querySelector('.toast-stack');
const content = document.querySelector('.content');

const themeKey = 'adminlte-inspired-theme';
const savedTheme = localStorage.getItem(themeKey);
const panels = new Map(
  Array.from(document.querySelectorAll('.dropdown-panel')).map((panel) => [panel.dataset.panel, panel])
);
let sectionObserver = null;
let activeViewId = 'dashboard';

const getViewTarget = (viewId) => {
  if (viewId === 'widgets') {
    return widgetsSection;
  }

  if (viewId === 'pages') {
    return pagesSection;
  }

  if (viewId === 'dashboard') {
    return null;
  }

  return document.getElementById(viewId);
};

const setHiddenState = (element, isHidden) => {
  if (element && element !== creatorPanel) {
    element.hidden = isHidden;
  }
};

const updateNavigationState = (viewId) => {
  menuLinks.forEach((menuItem) => {
    const href = menuItem.getAttribute('href');
    menuItem.classList.toggle('active', href === `#${viewId}`);
  });

  document.querySelectorAll('[data-dashboard-slug]').forEach((node) => {
    const groupSlug = node.dataset.dashboardSlug;
    const isActiveGroup = Boolean(groupSlug) && (viewId === groupSlug || viewId.startsWith(`${groupSlug}-`));

    if (node.matches('button')) {
      node.classList.toggle('active', isActiveGroup);
      node.setAttribute('aria-expanded', String(isActiveGroup));
    }

    if (node.matches('.menu-submenu')) {
      node.hidden = !isActiveGroup && node.hidden;
    }
  });

  const dashboardSectionActive =
    viewId === 'dashboard' ||
    viewId === 'widgets' ||
    viewId === 'pages' ||
    viewId === 'sales' ||
    viewId === 'messages' ||
    viewId === 'forms' ||
    viewId === 'tables' ||
    viewId.startsWith('dashboard-');

  sidebarMenuToggle?.classList.toggle('active', dashboardSectionActive);

  if (dashboardSectionActive) {
    setSidebarSubmenuOpen(true);
  }
};

const applyViewMode = (viewId) => {
  if (!content) {
    return;
  }

  activeViewId = viewId;

  if (viewId === 'dashboard') {
    Array.from(content.querySelectorAll('[hidden]')).forEach((node) => setHiddenState(node, false));
    updateNavigationState(viewId);
    return;
  }

  const target = getViewTarget(viewId);
  if (!target) {
    return;
  }

  Array.from(content.children).forEach((child) => {
    if (child !== creatorPanel) {
      child.hidden = true;
    }
  });

  let current = target;
  let parent = current.parentElement;

  while (current && parent && parent !== content) {
    Array.from(parent.children).forEach((sibling) => {
      if (sibling !== current) {
        sibling.hidden = true;
      }
    });

    current.hidden = false;
    current = parent;
    parent = current.parentElement;
  }

  if (current && current !== creatorPanel) {
    current.hidden = false;
  }

  updateNavigationState(viewId);
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const setSidebarOpen = (isOpen) => {
  appShell.classList.toggle('sidebar-open', isOpen);
};

const setSidebarCollapsed = (isCollapsed) => {
  appShell.classList.toggle('sidebar-collapsed', isCollapsed);
};

const setSidebarSubmenuOpen = (isOpen) => {
  if (!sidebarMenuToggle || !sidebarSubmenu) {
    return;
  }

  sidebarMenuToggle.setAttribute('aria-expanded', String(isOpen));
  sidebarSubmenu.hidden = !isOpen;
};

const setCreatorPanelOpen = (isOpen) => {
  if (!creatorPanel) {
    return;
  }

  creatorPanel.hidden = !isOpen;
};

const getSelectedFeatures = (form) => Array.from(form.querySelectorAll('input[name="features"]:checked')).map((input) => input.value);

const showToast = (title, message) => {
  if (!toastStack) {
    return;
  }

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<strong>${title}</strong><p>${message}</p>`;
  toastStack.append(toast);

  window.setTimeout(() => {
    toast.remove();
  }, 2600);
};

const closePanels = () => {
  dropdownButtons.forEach((button) => button.setAttribute('aria-expanded', 'false'));
  panels.forEach((panel) => {
    panel.hidden = true;
  });
};

const togglePanel = (name) => {
  const panel = panels.get(name);
  if (!panel) {
    return;
  }

  const button = document.querySelector(`[data-panel-toggle="${name}"]`);
  const isOpen = !panel.hidden;
  closePanels();
  panel.hidden = isOpen;
  button?.setAttribute('aria-expanded', String(!isOpen));
};

const syncThemeToggleLabel = () => {
  if (!themeToggle) {
    return;
  }

  themeToggle.textContent = document.documentElement.dataset.theme === 'dark'
    ? 'Switch to light'
    : 'Toggle color scheme';
};

const setTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(themeKey, theme);
  syncThemeToggleLabel();
};

const randomizeChart = () => {
  chartBars.forEach((bar, index) => {
    const value = Math.max(28, Math.min(96, 38 + Math.round(Math.sin(Date.now() / 240 + index) * 24) + Math.floor(Math.random() * 18)));
    bar.style.setProperty('--value', `${value}%`);
  });

  showToast('Sales refreshed', 'Chart values were regenerated with fresh sample data.');
};

const setCardCollapsed = (button, isCollapsed) => {
  const targetId = button.dataset.cardToggle;
  const card = document.getElementById(targetId);
  if (!card) {
    return;
  }

  card.classList.toggle('is-collapsed', isCollapsed);
  button.setAttribute('aria-expanded', String(!isCollapsed));
  button.textContent = isCollapsed ? 'Expand' : 'Collapse';
};

const createMenuLink = (label, href) => {
  const link = document.createElement('a');
  link.className = 'menu-subitem';
  link.href = href;
  link.textContent = label;
  link.addEventListener('click', () => {
    if (window.innerWidth < 980) {
      setSidebarOpen(false);
    }
  });
  return link;
};

const handleMenuNavigation = (event) => {
  const link = event.currentTarget;
  const href = link.getAttribute('href');
  if (!href || !href.startsWith('#')) {
    return;
  }

  event.preventDefault();
  const viewId = href.slice(1);
  applyViewMode(viewId);

  if (window.innerWidth < 980) {
    setSidebarOpen(false);
  }

  history.replaceState(null, '', href);
};

const createGeneratedDashboardGroup = ({ dashboardName, slug, features }) => {
  if (!sidebarMenu) {
    return null;
  }

  const group = document.createElement('div');
  group.className = 'menu-group generated-dashboard-group';

  const toggle = document.createElement('button');
  toggle.className = 'menu-item menu-toggle generated-dashboard-toggle active';
  toggle.type = 'button';
  toggle.dataset.dashboardSlug = slug;
  toggle.setAttribute('aria-expanded', 'true');
  toggle.innerHTML = `<span>${dashboardName}</span><strong>${features.length}</strong>`;

  const submenu = document.createElement('div');
  submenu.className = 'menu-submenu generated-dashboard-submenu';
  submenu.dataset.dashboardSlug = slug;
  submenu.hidden = false;

  const overviewLink = createMenuLink('Summary', `#${slug}`);
  submenu.appendChild(overviewLink);
  menuLinks.push(overviewLink);

  features.forEach((feature) => {
    const featureSlug = `${slug}-${feature.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
    const featureLink = createMenuLink(feature, `#${featureSlug}`);
    featureLink.dataset.dashboardSlug = slug;
    submenu.appendChild(featureLink);
    menuLinks.push(featureLink);
  });

  toggle.addEventListener('click', () => {
    const isOpen = submenu.hidden;
    submenu.hidden = !isOpen;
    toggle.setAttribute('aria-expanded', String(isOpen));
  });

  group.append(toggle, submenu);
  sidebarMenu.appendChild(group);

  return { group, toggle, submenu, overviewLink };
};

const createDashboardSection = ({ dashboardName, primaryColor, accentColor, features, roleName }) => {
  if (!content || !sidebarSubmenu) {
    return;
  }

  const safeName = dashboardName.trim();
  const slugBase = safeName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  const slug = `dashboard-${slugBase || 'custom'}`;

  if (document.getElementById(slug)) {
    showToast('Dashboard exists', 'That dashboard already exists on the page.');
    document.getElementById(slug)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }

  const generatedGroup = createGeneratedDashboardGroup({
    dashboardName: safeName,
    slug,
    features,
  });

  if (generatedGroup) {
    sidebarSubmenuLinks.push(generatedGroup.overviewLink);
  }

  const section = document.createElement('section');
  section.className = 'card custom-dashboard';
  section.id = slug;
  section.innerHTML = `
    <div class="section-head">
      <div>
        <p class="eyebrow">Custom Dashboard</p>
        <h2>${safeName}</h2>
      </div>
      <span class="badge badge-soft">New</span>
    </div>
    <p class="hero-copy">Role: ${roleName}</p>
    <p class="hero-copy">
      This dashboard was created on demand. Use it as a starting point for a new set of widgets, reports, or workflows.
    </p>
    <div class="custom-dashboard-grid">
      ${features
        .map(
          (feature, index) => `
            <article class="custom-feature-card" id="${slug}-${feature.toLowerCase().replace(/[^a-z0-9]+/g, '-')}">
              <h3>${feature}</h3>
              <p>${safeName} includes the ${feature.toLowerCase()} surface for the ${roleName} role.</p>
              <div class="feature-pills">
                <span class="feature-pill" style="background:${primaryColor}">Primary</span>
                <span class="feature-pill" style="background:${accentColor}">Accent</span>
                <span class="feature-pill" style="background: ${index % 2 === 0 ? primaryColor : accentColor}">${feature}</span>
              </div>
            </article>
          `
        )
        .join('')}
    </div>
  `;

  section.style.setProperty('--dashboard-primary', primaryColor);
  section.style.setProperty('--dashboard-accent', accentColor);

  content.append(section);
  sectionObserver?.observe(section);
  showToast('Dashboard created', `${safeName} was added to the dashboard list.`);
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

if (savedTheme === 'dark') {
  document.documentElement.dataset.theme = 'dark';
}

syncThemeToggleLabel();

sidebarToggle?.addEventListener('click', () => {
  if (window.innerWidth < 980) {
    setSidebarOpen(!appShell.classList.contains('sidebar-open'));
    return;
  }

  setSidebarCollapsed(!appShell.classList.contains('sidebar-collapsed'));
});

backdrop?.addEventListener('click', () => {
  setSidebarOpen(false);
  closePanels();
});

themeToggle?.addEventListener('click', () => {
  const isDark = document.documentElement.dataset.theme === 'dark';
  setTheme(isDark ? 'light' : 'dark');
  showToast('Theme updated', `Switched to ${isDark ? 'light' : 'dark'} mode.`);
});

fullscreenToggle?.addEventListener('click', async () => {
  try {
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen();
      showToast('Fullscreen enabled', 'The dashboard is now in fullscreen mode.');
    } else {
      await document.exitFullscreen();
      showToast('Fullscreen exited', 'Returned to the normal browser window.');
    }
  } catch {
    showToast('Fullscreen unavailable', 'Your browser blocked fullscreen for this page.');
  }
});

dropdownButtons.forEach((button) => {
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    togglePanel(button.dataset.panelToggle);
  });
});

cardToggleButtons.forEach((button) => {
  const targetId = button.dataset.cardToggle;
  const card = document.getElementById(targetId);
  if (card?.classList.contains('is-collapsed')) {
    button.textContent = 'Expand';
    button.setAttribute('aria-expanded', 'false');
  }

  button.addEventListener('click', () => {
    const isCollapsed = !card?.classList.contains('is-collapsed');
    setCardCollapsed(button, isCollapsed);
  });
});

chatForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  const input = chatForm.querySelector('input');
  const text = input?.value.trim();

  if (!text || !chatThread) {
    return;
  }

  const outgoing = document.createElement('div');
  outgoing.className = 'message outgoing';
  const now = new Date();
  const time = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

  const messageBody = document.createElement('div');
  const author = document.createElement('strong');
  const body = document.createElement('p');
  const timestamp = document.createElement('time');
  const avatar = document.createElement('img');

  author.textContent = 'You';
  body.textContent = text;
  timestamp.textContent = time;
  avatar.src = 'https://adminlte.io/themes/v4/assets/img/user8-128x128.jpg';
  avatar.alt = 'You';

  messageBody.append(author, body, timestamp);
  outgoing.append(messageBody, avatar);

  chatThread.append(outgoing);
  input.value = '';
  showToast('Message sent', 'Your chat message was added to the conversation.');
});

chartSection?.querySelector('[data-chart-refresh]')?.addEventListener('click', randomizeChart);

createDashboardButton?.addEventListener('click', () => {
  setCreatorPanelOpen(true);
  creatorPanel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

creatorCloseButton?.addEventListener('click', () => {
  setCreatorPanelOpen(false);
});

dashboardForm?.addEventListener('submit', (event) => {
  event.preventDefault();

  const formData = new FormData(dashboardForm);
  const roleName = String(formData.get('roleName') || '').trim();
  const primaryColor = String(formData.get('primaryColor') || '#3c8dbc');
  const accentColor = String(formData.get('accentColor') || '#00a65a');
  const mode = String(formData.get('mode') || 'light');
  const features = getSelectedFeatures(dashboardForm);

  if (!roleName) {
    showToast('Role name required', 'Please provide a role name for the dashboard.');
    return;
  }

  if (features.length === 0) {
    showToast('Select features', 'Choose at least one sidebar feature.');
    return;
  }

  createDashboardSection({
    dashboardName: roleName,
    roleName,
    primaryColor,
    accentColor,
    features,
  });

  setTheme(mode);
  showToast('Mode applied', `The dashboard was created in ${mode} mode.`);

  dashboardForm.reset();
  dashboardForm.querySelector('input[name="roleName"]')?.focus();
});

sidebarMenuToggle?.addEventListener('click', (event) => {
  event.stopPropagation();
  setSidebarSubmenuOpen(sidebarSubmenu?.hidden ?? true);
});

sidebarSubmenuLinks.forEach((item) => {
  item.addEventListener('click', () => {
    setSidebarSubmenuOpen(true);
    if (window.innerWidth < 980) {
      setSidebarOpen(false);
    }
  });
});

menuLinks.forEach((item) => {
  item.addEventListener('click', handleMenuNavigation);
});

const sectionIds = ['dashboard', 'widgets', 'sales', 'messages', 'forms', 'tables', 'pages'];
const sectionElements = sectionIds
  .map((sectionId) => document.getElementById(sectionId))
  .filter(Boolean);

if ('IntersectionObserver' in window) {
  sectionObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) {
        return;
      }

      const activeId = visible.target.id;
      if (activeId && activeId !== activeViewId) {
        updateNavigationState(activeId);
      }
    },
    {
      rootMargin: '-35% 0px -45% 0px',
      threshold: [0.15, 0.35, 0.55],
    }
  );

  sectionElements.forEach((section) => sectionObserver.observe(section));
}

window.addEventListener('click', () => {
  closePanels();
});

window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    setSidebarOpen(false);
    setSidebarCollapsed(false);
    closePanels();
  }
});

window.addEventListener('fullscreenchange', syncThemeToggleLabel);

setSidebarSubmenuOpen(false);
applyViewMode(location.hash ? location.hash.slice(1) : 'dashboard');
