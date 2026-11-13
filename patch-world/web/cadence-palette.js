// The demos site's brain palette, read once from its theme (--brain-<role> as "r,g,b"); the page by
// itself, without the site's theme, gets the same colours from the defaults below. A copy of the
// site's /cadence-palette.js with those defaults, so a page imports it as ./cadence-palette.js.
const DEFAULTS = {
  signal: '73,221,228', inhibit: '156,145,224', memory: '241,191,98', recall: '102,216,171',
  white: '220,243,244', dim: '132,158,165', rest: '18,34,39', trace: '171,145,207',
};
const tokens = getComputedStyle(document.documentElement);
const read = (role) => (tokens.getPropertyValue(`--brain-${role}`).trim() || DEFAULTS[role] || '200,200,200');
export const brainColor = (role) => read(role).split(',').map(Number);
export const brainUnit = (role) => brainColor(role).map((v) => v / 255);
export const brainHex = (role) => '#' + brainColor(role).map((v) => v.toString(16).padStart(2, '0')).join('');
