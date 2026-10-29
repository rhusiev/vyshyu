import { identicon } from "./identicon.js";
import { forgetGoogle, initGoogle, renderGoogleButton } from "./google.js";
import { getLanguage, localize, setLanguage, t, translatePage } from "./i18n.js";

const COOKIE = "wishlist_username";
const COOKIE_MAX_AGE_S = 400 * 24 * 60 * 60; // the longest lifetime browsers allow
const AVATAR_STACK_MAX = 4;
const HTTP_FORBIDDEN = 403;
const HTTP_CONFLICT = 409;

const $ = (selector, root = document) => root.querySelector(selector);
const itemDialog = $("#item-dialog");
const nameDialog = $("#name-dialog");
const nameInput = $("#name-input");

let wishlist = null;
let session = { google_client_id: null, signed_in: false, username: null };
let openItemId = null;

class HttpError extends Error {
  constructor(status) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

async function api(method, path, body) {
  const response = await fetch(`api/${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new HttpError(response.status);
  return response.status === 204 ? null : response.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function normalize(name) {
  return name.split(/\s+/).filter(Boolean).join(" ");
}

function cookieUsername() {
  const entry = document.cookie.split("; ").find((c) => c.startsWith(`${COOKIE}=`));
  return entry ? decodeURIComponent(entry.slice(COOKIE.length + 1)) : null;
}

function setCookieUsername(name) {
  const secure = location.protocol === "https:" ? "; secure" : "";
  const maxAge = name ? COOKIE_MAX_AGE_S : 0;
  document.cookie = `${COOKIE}=${encodeURIComponent(name ?? "")}; max-age=${maxAge}; path=/; samesite=lax${secure}`;
}

function currentUsername() {
  return session.signed_in ? session.username : cookieUsername();
}

// Name dialog: asks for a name, or lets a signed-in visitor rename or sign out

function renderNameDialog() {
  const mode = !session.signed_in ? "anonymous" : session.username ? "account" : "choose";
  $("#name-title").textContent = t(mode === "anonymous" ? "nameTitle" : "accountTitle");
  $("#name-hint").textContent = t({ anonymous: "nameHint", account: "accountHint", choose: "chooseNameHint" }[mode]);
  $("#sign-out").hidden = !session.signed_in;
  const offerGoogle = Boolean(session.google_client_id) && !session.signed_in;
  $("#google-section").hidden = !offerGoogle;
  if (offerGoogle) renderGoogleButton($("#google-button"), getLanguage()).catch(showError);
  updateNamePreview();
}

function updateNamePreview() {
  const name = normalize(nameInput.value);
  $(".avatar-slot", nameDialog).replaceChildren(identicon(name || "?"));
}

function showNameError(key) {
  const box = $("#name-error");
  box.hidden = !key;
  box.textContent = key ? t(key) : "";
}

function askName(errorKey = null) {
  nameInput.value = currentUsername() ?? "";
  showNameError(errorKey);
  renderNameDialog();
  nameDialog.returnValue = "";
  nameDialog.showModal();
  return new Promise((resolve) => {
    nameDialog.addEventListener("close", () => {
      resolve(nameDialog.returnValue === "ok" ? currentUsername() : null);
    }, { once: true });
  });
}

async function saveName(name) {
  if (session.signed_in) {
    session = await api("PUT", "session/username", { username: name });
  } else {
    const { reserved } = await api("GET", `usernames/${encodeURIComponent(name)}`);
    if (reserved) throw new HttpError(HTTP_CONFLICT);
    setCookieUsername(name);
  }
}

async function onNameSubmit(event) {
  if (event.submitter?.value !== "ok") return;
  event.preventDefault();
  const name = normalize(nameInput.value);
  if (!name) return;
  try {
    await saveName(name);
    nameDialog.close("ok");
    render();
  } catch (error) {
    if (error.status === HTTP_CONFLICT) showNameError(session.signed_in ? "nameTaken" : "nameReserved");
    else showError(error);
  }
}

async function onGoogleCredential(credential) {
  try {
    session = await api("POST", "session/google", { credential });
  } catch (error) {
    return showError(error);
  }
  showNameError(null);
  if (session.username) {
    nameDialog.close("ok");
    render();
  } else {
    renderNameDialog();
  }
}

async function signOut() {
  await api("DELETE", "session");
  forgetGoogle();
  setCookieUsername(null);
  session = await api("GET", "session");
  nameDialog.close("cancel");
  render();
}

// The list and the item card

function wantMeter(want) {
  const { min, max } = wishlist.want;
  const meter = el("div", "want");
  meter.title = t("wanted", want - min + 1, max - min + 1);
  meter.setAttribute("aria-label", meter.title);
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
  for (const giver of givers.slice(0, AVATAR_STACK_MAX)) stack.append(identicon(giver.username));
  if (givers.length > AVATAR_STACK_MAX) {
    stack.append(el("span", "more", `+${givers.length - AVATAR_STACK_MAX}`));
  }
  return stack;
}

function isMine(item) {
  const me = currentUsername();
  return me !== null && item.givers.some((giver) => giver.username === me);
}

function renderCard(item) {
  const li = el("li");
  const card = el("button", "card");
  card.type = "button";
  card.classList.toggle("mine", isMine(item));
  card.append(el("h2", "label", localize(item.label)), wantMeter(item.want));
  const description = localize(item.description);
  if (description) card.append(el("p", "description", preview(description)));
  const footer = el("div", "card-footer");
  if (item.givers.length) {
    footer.append(avatarStack(item.givers), el("span", "count", t("gifting", item.givers.length)));
  } else {
    footer.append(el("span", "count free", t("upForGrabs")));
  }
  card.append(footer);
  card.addEventListener("click", () => openItem(item.id));
  li.append(card);
  return li;
}

function protectedBadge() {
  const badge = el("span", "badge", "✓");
  badge.title = t("protectedName");
  return badge;
}

function renderGiver(giver) {
  const me = giver.username === currentUsername();
  const li = el("li", me ? "giver me" : "giver");
  li.append(identicon(giver.username), el("span", "", me ? `${giver.username} (${t("you")})` : giver.username));
  if (giver.protected) li.append(protectedBadge());
  return li;
}

function renderDialog() {
  const item = wishlist.items.find((i) => i.id === openItemId);
  if (!item) return itemDialog.close();
  $(".dialog-label", itemDialog).textContent = localize(item.label);
  $(".want", itemDialog).replaceWith(wantMeter(item.want));
  $(".dialog-description", itemDialog).textContent = localize(item.description);
  $(".givers", itemDialog).replaceChildren(...item.givers.map(renderGiver));
  $(".no-givers", itemDialog).hidden = item.givers.length > 0;
  const pledged = isMine(item);
  const button = $(".pledge", itemDialog);
  button.textContent = t(pledged ? "unpledge" : "pledge");
  button.classList.toggle("primary", !pledged);
}

function renderWhoami() {
  const name = currentUsername();
  const button = $("#whoami");
  button.hidden = !name;
  if (!name) return;
  $(".avatar-slot", button).replaceChildren(identicon(name));
  $(".whoami-name", button).textContent = name;
  button.querySelector(".badge")?.remove();
  if (session.signed_in) button.append(protectedBadge());
  button.title = t("changeName");
}

function renderLanguages() {
  for (const button of document.querySelectorAll("[data-language]")) {
    button.setAttribute("aria-pressed", button.dataset.language === getLanguage());
  }
}

function render() {
  translatePage();
  renderLanguages();
  renderWhoami();
  if (!wishlist) return;
  const title = localize(wishlist.title);
  document.title = title;
  $("#title").textContent = title;
  $("#subtitle").textContent = localize(wishlist.subtitle);
  $("#items").replaceChildren(...wishlist.items.map(renderCard));
  if (openItemId) renderDialog();
  if (nameDialog.open) renderNameDialog();
}

function openItem(id) {
  openItemId = id;
  renderDialog();
  itemDialog.showModal();
}

async function loadWishlist() {
  wishlist = await api("GET", "wishlist");
  render();
}

async function togglePledge() {
  const username = currentUsername() ?? (await askName());
  if (!username) return;
  const item = wishlist.items.find((i) => i.id === openItemId);
  const button = $(".pledge", itemDialog);
  button.disabled = true;
  try {
    await api(isMine(item) ? "DELETE" : "POST", `items/${encodeURIComponent(item.id)}/pledges`, { username });
    await loadWishlist();
  } catch (error) {
    if (error.status === HTTP_FORBIDDEN) askName("nameReserved");
    else showError(error);
  } finally {
    button.disabled = false;
  }
}

function showError(error) {
  const box = $("#error");
  box.textContent = `${t("failed")}: ${error.message}`;
  box.hidden = false;
}

$(".pledge", itemDialog).addEventListener("click", togglePledge);
itemDialog.addEventListener("close", () => { openItemId = null; });
// Dialogs have no padding of their own, so a click landing on the dialog is on the backdrop
for (const dialog of [itemDialog, nameDialog]) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close("cancel");
  });
}
nameInput.addEventListener("input", updateNamePreview);
$("#name-form").addEventListener("submit", onNameSubmit);
$("#sign-out").addEventListener("click", () => signOut().catch(showError));
$("#whoami").addEventListener("click", () => askName());
for (const button of document.querySelectorAll("[data-language]")) {
  button.addEventListener("click", () => {
    setLanguage(button.dataset.language);
    render();
  });
}

async function start() {
  render();
  session = await api("GET", "session");
  if (session.google_client_id) initGoogle(session.google_client_id, onGoogleCredential).catch(showError);
  await loadWishlist();
}

start().catch(showError);
