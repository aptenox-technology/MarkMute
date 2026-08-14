/* MarkMute — landing page theme toggle (default: light). */
"use strict";

(function () {
  const saved = localStorage.getItem("mm-theme") || "light";
  document.documentElement.dataset.theme = saved;
})();

const themeToggle = document.getElementById("theme-toggle");
const themeIconSun = document.getElementById("theme-icon-sun");
const themeIconMoon = document.getElementById("theme-icon-moon");

function renderThemeIcons() {
  const dark = document.documentElement.dataset.theme === "dark";
  if (themeIconSun) themeIconSun.classList.toggle("hidden", !dark);
  if (themeIconMoon) themeIconMoon.classList.toggle("hidden", dark);
}

themeToggle?.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("mm-theme", next);
  renderThemeIcons();
});

renderThemeIcons();