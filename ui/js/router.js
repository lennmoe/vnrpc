import { $, $$, el } from "./dom.js";

const pages = new Map();
let current = null;

export function register(page) {
  pages.set(page.id, page);
}

export function currentPage() {
  return current;
}

export function show(id, params = {}) {
  const page = pages.get(id);
  if (!page) {
    return;
  }

  if (!page.root) {
    page.root = el("section", { class: `page ${page.fill ? "fill" : ""}`, id: `page-${id}` });
    $("#content").append(page.root);
    page.build(page.root);
  }

  for (const other of pages.values()) {
    other.root?.classList.toggle("active", other === page);
  }
  for (const button of $$("nav button")) {
    button.classList.toggle("active", button.dataset.page === (page.nav || page.id));
  }

  current = page;
  $("#content").scrollTop = 0;
  page.show?.(params);
}

document.addEventListener("keydown", (event) => {
  const typing = event.target.closest?.("input, textarea, select");
  if (!typing && current?.onKey) {
    current.onKey(event);
  }
});
