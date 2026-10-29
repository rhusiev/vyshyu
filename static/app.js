import { identicon } from "./identicon.js";

const COOKIE = "wishlist_username";
const COOKIE_MAX_AGE_S = 400 * 24 * 60 * 60; // the longest lifetime browsers allow
const AVATAR_STACK_MAX = 4;

const $ = (selector, root = document) => root.querySelector(selector);
const itemDialog = $("#item-dialog");
const nameDialog = $("#name-dialog");
const nameInput = $("#name-input");

let wishlist = null;
let openItemId = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function getUsername() {
  const entry = document.cookie.split("; ").find((c) => c.startsWith(`${COOKIE}=`));
  return entry ? decodeURIComponent(entry.slice(COOKIE.length + 1)) : null;
}

function setUsername(name) {
  const secure = location.protocol === "https:" ? "; secure" : "";
  document.cookie = `${COOKIE}=${encodeURIComponent(name)}; max-age=${COOKIE_MAX_AGE_S}; path=/; samesite=lax${secure}`;
  renderWhoami();
}

function normalize(name) {
  return name.split(/\s+/).filter(Boolean).join(" ");
}

function askName() {
  const current = getUsername() ?? "";
  nameInput.value = current;
  updateNamePreview();
  nameDialog.showModal();
  return new Promise((resolve) => {
    nameDialog.addEventListener("close", () => {
      const name = normalize(nameInput.value);
      if (nameDialog.returnValue === "ok" && name) {
        setUsername(name);
        resolve(name);
      } else {
        resolve(null);
      }
    }, { once: true });
  });
}

function updateNamePreview() {
  const name = normalize(nameInput.value);
  $(".avatar-slot", nameDialog).replaceChildren(identicon(name || "?"));
}

function renderWhoami() {
  const name = getUsername();
  const button = $("#whoami");
  button.hidden = !name;
  if (!name) return;
  $(".avatar-slot", button).replaceChildren(identicon(name));
  $(".whoami-name", button).textContent = name;
  button.title = "Change your name";
}

function wantMeter(want) {
  const { min, max } = wishlist.want;
  const meter = el("div", "want");
  meter.setAttribute("aria-label", `wanted ${want - min + 1} of ${max - min + 1}`);
  for (let level = min; level <= max; level++) {
    meter.append(el("span", level <= want ? "heart on" : "heart", "♥"));
  }
  return meter;
}

function preview(text) {
  const limit = wishlist.preview_chars;
  return text.length <= limit ? text : `${text.slice(0, limit).trimEnd()}…`;
}

function avatarStack(givers) {
  const stack = el("div", "stack");
  for (const name of givers.slice(0, AVATAR_STACK_MAX)) stack.append(identicon(name));
  if (givers.length > AVATAR_STACK_MAX) {
    stack.append(el("span", "more", `+${givers.length - AVATAR_STACK_MAX}`));
  }
  return stack;
}

function renderCard(item) {
  const me = getUsername();
  const li = el("li");
  const card = el("button", "card");
  card.type = "button";
  if (item.givers.length) card.classList.add("taken");
  if (me && item.givers.includes(me)) card.classList.add("mine");
  card.append(el("h2", "label", item.label), wantMeter(item.want));
  if (item.description) card.append(el("p", "description", preview(item.description)));
  const footer = el("div", "card-footer");
  if (item.givers.length) {
    const count = item.givers.length === 1 ? "1 gifting" : `${item.givers.length} gifting`;
    footer.append(avatarStack(item.givers), el("span", "count", count));
  } else {
    footer.append(el("span", "count free", "Up for grabs"));
  }
  card.append(footer);
  card.addEventListener("click", () => openItem(item.id));
  li.append(card);
  return li;
}

function render() {
  document.title = wishlist.title;
  $("#title").textContent = wishlist.title;
  $("#subtitle").textContent = wishlist.subtitle;
  $("#items").replaceChildren(...wishlist.items.map(renderCard));
  renderWhoami();
  if (openItemId) renderDialog();
}

function renderDialog() {
  const item = wishlist.items.find((i) => i.id === openItemId);
  if (!item) return itemDialog.close();
  const me = getUsername();
  $(".dialog-label", itemDialog).textContent = item.label;
  $(".want", itemDialog).replaceWith(wantMeter(item.want));
  $(".dialog-description", itemDialog).textContent = item.description;
  const givers = item.givers.map((name) => {
    const li = el("li", name === me ? "giver me" : "giver");
    li.append(identicon(name), el("span", "", name === me ? `${name} (you)` : name));
    return li;
  });
  $(".givers", itemDialog).replaceChildren(...givers);
  $(".no-givers", itemDialog).hidden = item.givers.length > 0;
  const pledged = me !== null && item.givers.includes(me);
  const button = $(".pledge", itemDialog);
  button.textContent = pledged ? "I changed my mind" : "I'll gift this 🎁";
  button.classList.toggle("primary", !pledged);
}

function openItem(id) {
  openItemId = id;
  renderDialog();
  itemDialog.showModal();
}

async function load() {
  const response = await fetch("api/wishlist");
  if (!response.ok) throw new Error(`could not load the wishlist (${response.status})`);
  wishlist = await response.json();
  render();
}

async function togglePledge() {
  const username = getUsername() ?? (await askName());
  if (!username) return;
  const item = wishlist.items.find((i) => i.id === openItemId);
  const method = item.givers.includes(username) ? "DELETE" : "POST";
  const button = $(".pledge", itemDialog);
  button.disabled = true;
  try {
    const response = await fetch(`api/items/${encodeURIComponent(item.id)}/pledges`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    if (!response.ok) throw new Error(`saving failed (${response.status})`);
    await load();
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
}

function showError(error) {
  const box = $("#error");
  box.textContent = `Something went wrong: ${error.message}`;
  box.hidden = false;
}

$(".pledge", itemDialog).addEventListener("click", togglePledge);
itemDialog.addEventListener("close", () => { openItemId = null; });
itemDialog.addEventListener("click", (event) => {
  if (event.target === itemDialog) itemDialog.close();
});
nameInput.addEventListener("input", updateNamePreview);
$("#whoami").addEventListener("click", async () => {
  if (await askName()) render();
});

load().catch(showError);
