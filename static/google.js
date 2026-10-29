// "Sign in with Google" through Google Identity Services. The button hands back an ID
// token (the credential), which the server verifies before trusting the account
const SCRIPT_URL = "https://accounts.google.com/gsi/client";
const BUTTON_WIDTH_PX = 280;

let ready = null;

export function initGoogle(clientId, onCredential) {
  ready ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.async = true;
    script.onload = () => {
      google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => onCredential(response.credential),
      });
      resolve();
    };
    script.onerror = () => reject(new Error("could not load Google sign-in"));
    document.head.append(script);
  });
  return ready;
}

export async function renderGoogleButton(container, locale) {
  await ready;
  container.replaceChildren();
  google.accounts.id.renderButton(container, {
    theme: "outline",
    size: "large",
    shape: "pill",
    text: "signin_with",
    width: BUTTON_WIDTH_PX,
    locale,
  });
}

export function forgetGoogle() {
  if (ready) ready.then(() => google.accounts.id.disableAutoSelect());
}
