const STORAGE_KEY = "wishlist_language";
export const LANGUAGES = ["en", "uk"];

const STRINGS = {
  en: {
    close: "Close",
    heartsHint: "Hearts show how much I want something - the more hearts, the more I want it",
    wanted: (level, levels) => `Wanted: ${level} of ${levels}`,
    upForGrabs: "Up for grabs",
    gifting: (count) => `${count} gifting`,
    givingHeading: "Going to gift it",
    nobodyYet: "Nobody yet - it's up for grabs",
    pledge: "I'll gift this",
    unpledge: "I changed my mind",
    you: "you",
    protectedName: "Name protected by Google sign-in",
    changeName: "Change your name",
    nameTitle: "What's your name?",
    nameHint: "So others know who's bringing what. It's remembered on this device",
    accountTitle: "Your name",
    accountHint: "You're signed in with Google, so this name is yours - nobody else can use it",
    chooseNameHint: "You're signed in with Google. Choose the name you want to reserve",
    cancel: "Cancel",
    save: "Save",
    or: "or",
    googleWhy: "Signing in with Google is optional. It reserves your name: nobody else can use it, " +
      "and only you can change your choices - from any device. We keep only an anonymous " +
      "account id, not your email or photo",
    signOut: "Sign out",
    nameReserved: "Someone protected this name with Google sign-in. Pick another one, or sign in if it's yours",
    nameTaken: "Someone already uses this name, so it can't be reserved. Pick another one",
    failed: "Something went wrong",
  },
  uk: {
    close: "Закрити",
    heartsHint: "Сердечка показують, наскільки мені чогось хочеться - що більше сердечок, то сильніше",
    wanted: (level, levels) => `Бажаність: ${level} з ${levels}`,
    upForGrabs: "Ще ніхто не обрав",
    gifting: (count) => `Дарують: ${count}`,
    givingHeading: "Збираються подарувати",
    nobodyYet: "Поки ніхто - можна обрати",
    pledge: "Я подарую це",
    unpledge: "Скасувати мій вибір",
    you: "ви",
    protectedName: "Ім'я захищене входом через Google",
    changeName: "Змінити ім'я",
    nameTitle: "Як вас звати?",
    nameHint: "Щоб інші бачили, хто що дарує. Ім'я запам'ятається на цьому пристрої",
    accountTitle: "Ваше ім'я",
    accountHint: "Ви увійшли через Google, тож це ім'я ваше - ніхто інший не зможе ним скористатися",
    chooseNameHint: "Ви увійшли через Google. Оберіть ім'я, яке хочете закріпити за собою",
    cancel: "Скасувати",
    save: "Зберегти",
    or: "або",
    googleWhy: "Вхід через Google необов'язковий. Він закріплює ваше ім'я: ніхто інший не зможе " +
      "ним скористатися, і лише ви зможете змінювати свій вибір - з будь-якого пристрою. " +
      "Ми зберігаємо лише анонімний ідентифікатор облікового запису, без пошти й фото",
    signOut: "Вийти",
    nameReserved: "Хтось захистив це ім'я входом через Google. Оберіть інше або увійдіть, якщо воно ваше",
    nameTaken: "Цим ім'ям уже хтось користується, тож закріпити його не можна. Оберіть інше",
    failed: "Щось пішло не так",
  },
};

function savedLanguage() {
  const saved = localStorage.getItem(STORAGE_KEY);
  return LANGUAGES.includes(saved) ? saved : null;
}

function browserLanguage() {
  const preferred = navigator.languages.map((tag) => tag.slice(0, 2).toLowerCase());
  return preferred.find((code) => LANGUAGES.includes(code)) ?? "en";
}

let language = savedLanguage() ?? browserLanguage();

// The wishlist owner's default beats the browser guess, never the visitor's own choice
export function applyDefaultLanguage(code) {
  if (code && !savedLanguage()) language = code;
}

export function getLanguage() {
  return language;
}

export function setLanguage(code) {
  language = code;
  localStorage.setItem(STORAGE_KEY, code);
}

export function t(key, ...args) {
  const entry = STRINGS[language][key];
  return typeof entry === "function" ? entry(...args) : entry;
}

// Config text is either one string or a table with a string per language code
export function localize(text) {
  if (typeof text === "string") return text;
  return text[language] ?? text.en ?? Object.values(text)[0] ?? "";
}

export function translatePage() {
  document.documentElement.lang = language;
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nLabel));
  }
}
