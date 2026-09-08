"use strict";
(() => {
  const root = document.body;
  const links = [...document.querySelectorAll("[data-language]")];
  const available = links.map(link => link.dataset.language);
  const store = "panelnest.language";
  let saved;
  try { saved = localStorage.getItem(store); } catch (_) { /* Storage is optional. */ }
  if (root.dataset.autoLanguage === "true") {
    const preferred = available.includes(saved) ? saved : (navigator.languages || [navigator.language]).map(code => code.toLowerCase().split("-")[0]).find(code => available.includes(code));
    if (preferred && preferred !== "en") location.replace(root.dataset.base + preferred + "/" + location.hash);
  }
  links.forEach(link => link.addEventListener("click", () => {
    try { localStorage.setItem(store, link.dataset.language); } catch (_) { /* Links still work. */ }
  }));
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") document.querySelectorAll("details[open]").forEach(detail => { detail.open = false; detail.querySelector("summary").focus(); });
  });
  const copy = document.getElementById("copy-url");
  copy.hidden = false;
  copy.addEventListener("click", async () => {
    const code = document.getElementById("list-url");
    const status = document.getElementById("copy-status");
    try {
      await navigator.clipboard.writeText(code.textContent);
      status.textContent = copy.dataset.success;
    } catch (_) {
      const range = document.createRange(); range.selectNodeContents(code);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      code.focus(); status.textContent = copy.dataset.failure;
    }
  });
})();
