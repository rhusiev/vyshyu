// GitHub-style identicon: a mirrored 5x5 grid whose cells and hue come from a
// hash of the username, so the same name draws the same picture on every device

const GRID = 5;
const HALF = Math.ceil(GRID / 2);
const CELL = 10;
// Avatars are clipped to a circle: the grid's corners must stay inside it
const PADDING = 11;
const SIZE = GRID * CELL + 2 * PADDING;
const SVG_NS = "http://www.w3.org/2000/svg";

// FNV-1a over UTF-8 bytes, seeded so two independent 32-bit words can be drawn
function fnv1a(text, seed) {
  let hash = 0x811c9dc5 ^ seed;
  for (const byte of new TextEncoder().encode(text)) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export function identicon(username) {
  const cellBits = fnv1a(username, 0);
  const hue = fnv1a(username, 0x9e3779b9) % 360;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${SIZE} ${SIZE}`);
  svg.setAttribute("class", "avatar");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", username);
  const background = document.createElementNS(SVG_NS, "rect");
  background.setAttribute("width", SIZE);
  background.setAttribute("height", SIZE);
  background.setAttribute("fill", `hsl(${hue} 60% 91%)`);
  svg.append(background);
  for (let col = 0; col < HALF; col++) {
    for (let row = 0; row < GRID; row++) {
      if (!((cellBits >>> (col * GRID + row)) & 1)) continue;
      for (const x of new Set([col, GRID - 1 - col])) {
        const cell = document.createElementNS(SVG_NS, "rect");
        cell.setAttribute("x", PADDING + x * CELL);
        cell.setAttribute("y", PADDING + row * CELL);
        cell.setAttribute("width", CELL);
        cell.setAttribute("height", CELL);
        cell.setAttribute("fill", `hsl(${hue} 55% 52%)`);
        svg.append(cell);
      }
    }
  }
  const title = document.createElementNS(SVG_NS, "title");
  title.textContent = username;
  svg.append(title);
  return svg;
}
