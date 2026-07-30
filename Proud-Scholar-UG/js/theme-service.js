(function () {
  class ThemeService {
    applyTheme(theme) {
      if (!theme) {
        return;
      }
      document.documentElement.style.setProperty('--dashboard-primary', theme.primary_color || '#3c8dbc');
      document.documentElement.style.setProperty('--dashboard-secondary', theme.secondary_color || '#00a65a');
      document.documentElement.style.setProperty('--dashboard-font', theme.font || 'Inter');
      document.body.dataset.theme = theme.mode || 'light';
    }
  }

  window.ThemeService = ThemeService;
})();
