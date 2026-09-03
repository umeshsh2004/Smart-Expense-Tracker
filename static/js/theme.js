(function () {
  const STORAGE_KEY = "expense-tracker-theme";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const label = theme === "dark" ? "🌙 Dark" : "🌞 Light";
    document.querySelectorAll(".theme-toggle").forEach((btn) => {
      btn.textContent = label;
    });
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const saved = localStorage.getItem(STORAGE_KEY) || "light";
    applyTheme(saved);

    document.querySelectorAll(".theme-toggle").forEach((btn) => {
      btn.addEventListener("click", toggleTheme);
    });

    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebar = document.getElementById("sidebar");
    if (sidebarToggle && sidebar) {
      sidebarToggle.addEventListener("click", () => {
        sidebar.classList.toggle("open");
      });
    }
  });
})();
