/* MarkMute — landing page theme switch (default: light). */
"use strict";

(function () {
  const saved = localStorage.getItem("mm-theme") || "light";
  document.documentElement.dataset.theme = saved;
})();

const themeToggle = document.getElementById("theme-toggle");

function renderThemeSwitch() {
  const dark = document.documentElement.dataset.theme === "dark";
  if (themeToggle) themeToggle.setAttribute("aria-checked", dark ? "true" : "false");
}

themeToggle?.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("mm-theme", next);
  renderThemeSwitch();
});

renderThemeSwitch();