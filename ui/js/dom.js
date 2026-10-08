export const $ = (selector, root = document) => root.querySelector(selector);

export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);

  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) {
      continue;
    }
    if (name === "class") {
      node.className = value;
    } else if (name === "style" && typeof value === "object") {
      Object.assign(node.style, value);
    } else if (name.startsWith("on")) {
      node.addEventListener(name.slice(2), value);
    } else {
      node.setAttribute(name, value === true ? "" : value);
    }
  }

  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) {
      node.append(child);
    }
  }
  return node;
}

export function svg(tag, attrs = {}, text = "") {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attrs)) {
    node.setAttribute(name, value);
  }
  if (text) {
    node.textContent = text;
  }
  return node;
}

export function html(markup) {
  const template = document.createElement("template");
  template.innerHTML = markup.trim();
  return template.content;
}
