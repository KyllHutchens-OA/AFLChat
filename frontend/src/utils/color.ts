// Small colour-contrast helpers used wherever a club colour becomes a
// background (badges, guernsey chips, chart lines) and we need to pick a
// text colour or line brightness that stays legible against it.

const hexToRgb = (hex: string): [number, number, number] => {
  const clean = hex.replace('#', '');
  const full = clean.length === 3 ? clean.split('').map((c) => c + c).join('') : clean;
  const num = parseInt(full, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
};

// WCAG relative luminance.
const relativeLuminance = ([r, g, b]: [number, number, number]) => {
  const srgb = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2];
};

export const contrastRatio = (hexA: string, hexB: string) => {
  const lA = relativeLuminance(hexToRgb(hexA));
  const lB = relativeLuminance(hexToRgb(hexB));
  const [lighter, darker] = lA > lB ? [lA, lB] : [lB, lA];
  return (lighter + 0.05) / (darker + 0.05);
};

// Picks whichever of ink or white reads best on the given background,
// so a club badge never pairs its own two colours in a losing combination
// (e.g. Brisbane's navy secondary on its maroon primary, ~2.3:1).
export const contrastText = (bgHex: string, ink = '#16130F', white = '#FFFFFF') => {
  const toInk = contrastRatio(bgHex, ink);
  const toWhite = contrastRatio(bgHex, white);
  return toInk >= toWhite ? ink : white;
};

// Lightens a colour that is too dark to read against a near-black surface
// (the landing scoreboard's ink background), by mixing it toward white
// until it clears a minimum contrast ratio. Bright club colours pass through
// unchanged.
export const legibleOnDark = (hex: string, bgHex = '#16130F', minRatio = 2.6) => {
  let [r, g, b] = hexToRgb(hex);
  let current = contrastRatio(rgbToHex(r, g, b), bgHex);
  let mix = 0;
  while (current < minRatio && mix < 0.9) {
    mix += 0.08;
    r = Math.round(hexToRgb(hex)[0] * (1 - mix) + 255 * mix);
    g = Math.round(hexToRgb(hex)[1] * (1 - mix) + 255 * mix);
    b = Math.round(hexToRgb(hex)[2] * (1 - mix) + 255 * mix);
    current = contrastRatio(rgbToHex(r, g, b), bgHex);
  }
  return rgbToHex(r, g, b);
};

function rgbToHex(r: number, g: number, b: number) {
  return `#${[r, g, b].map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')).join('')}`;
}
