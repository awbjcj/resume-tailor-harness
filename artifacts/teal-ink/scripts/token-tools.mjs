import { readFile } from "node:fs/promises";

export const root = new URL("../", import.meta.url);

export async function readJSON(path) {
  return JSON.parse(await readFile(new URL(path, root), "utf8"));
}

export function flatten(group, path = [], result = new Map()) {
  for (const [key, value] of Object.entries(group)) {
    if (key.startsWith("$")) continue;
    const next = [...path, key];
    if (value && typeof value === "object" && "$value" in value) {
      result.set(next.join("."), value);
    } else {
      flatten(value, next, result);
    }
  }
  return result;
}

export function cssName(path) {
  const [layer, ...parts] = path.split(".");
  return `--ti-${layer === "primitive" ? "p-" : ""}${parts.join("-")}`;
}

export function reference(value) {
  return typeof value === "string" && /^\{[^{}]+\}$/.test(value)
    ? value.slice(1, -1)
    : null;
}

export function resolve(path, tokens, stack = []) {
  if (stack.includes(path)) throw new Error(`Circular token: ${[...stack, path].join(" -> ")}`);
  const token = tokens.get(path);
  if (!token) throw new Error(`Missing token: ${path}`);
  const target = reference(token.$value);
  if (target) {
    const resolved = resolve(target, tokens, [...stack, path]);
    if (token.$type !== resolved.$type) throw new Error(`Type mismatch: ${path} -> ${target}`);
    return resolved;
  }
  return token;
}

function color(value) {
  if (value.colorSpace !== "srgb" || value.components.length !== 3) throw new Error("Expected an sRGB color");
  const channels = value.components.map((part) => Math.round(part * 255));
  if (value.alpha === undefined || value.alpha === 1) {
    return `#${channels.map((part) => part.toString(16).padStart(2, "0")).join("")}`;
  }
  return `rgb(${channels.join(" ")} / ${value.alpha})`;
}

export function serialize(token, aliases = true) {
  const value = token.$value;
  const target = reference(value);
  if (target && aliases) return `var(${cssName(target)})`;
  if (target) throw new Error("Resolve aliases before serializing a literal");
  switch (token.$type) {
    case "color": return color(value);
    case "dimension": return `${value.value}${value.unit}`;
    case "duration": return `${value.value}${value.unit}`;
    case "fontFamily": return (Array.isArray(value) ? value : [value]).map((font) => font.includes(" ") ? `"${font}"` : font).join(", ");
    case "fontWeight":
    case "number": return String(value);
    case "cubicBezier": return `cubic-bezier(${value.join(", ")})`;
    case "shadow": return (Array.isArray(value) ? value : [value]).map((shadow) => [
      ...(shadow.inset ? ["inset"] : []),
      ...["offsetX", "offsetY", "blur", "spread"].map((key) => `${shadow[key].value}${shadow[key].unit}`),
      color(shadow.color),
    ].join(" ")).join(", ");
    default: throw new Error(`Unsupported token type: ${token.$type}`);
  }
}

export async function loadThemes() {
  const base = flatten(await readJSON("tokens/base.tokens.json"));
  const dark = flatten(await readJSON("tokens/dark.tokens.json"));
  const gateway = flatten(await readJSON("tokens/gateway.tokens.json"));
  return {
    base,
    themes: {
      light: new Map(base),
      dark: new Map([...base, ...dark]),
      gateway: new Map([...base, ...gateway]),
    },
  };
}

export async function generatedFiles() {
  const { base, themes } = await loadThemes();
  for (const theme of Object.values(themes)) for (const path of theme.keys()) resolve(path, theme);
  const declarations = (tokens, predicate = () => true) => [...tokens]
    .filter(([path]) => predicate(path))
    .map(([path, token]) => `  ${cssName(path)}: ${serialize(token)};`).join("\n");
  // Re-declare aliases at each explicit boundary: inherited CSS aliases resolve
  // at their declaration site, so changing only a descendant semantic token
  // would otherwise leave inherited component tokens bound to the outer theme.
  const themed = (theme) => declarations(theme, (path) => !path.startsWith("primitive."));
  const darkSelectors = ':root.dark:not([data-ti-theme]), .ti-root.dark:not([data-ti-theme]), [data-ti-theme="dark"]';
  const css = `/* Generated from tokens/*.tokens.json. Edit tokens, then run npm run build. */\n\n:root {\n${declarations(base, (path) => path.startsWith("primitive."))}\n}\n\n:root, [data-ti-theme] {\n${themed(base)}\n  color-scheme: light;\n}\n\n${darkSelectors} {\n${themed(themes.dark)}\n  color-scheme: dark;\n}\n\n@media (prefers-color-scheme: dark) {\n  :root:not([data-ti-theme]):not(.light), [data-ti-theme="system"] {\n${themed(themes.dark).split("\n").map((line) => `  ${line}`).join("\n")}\n    color-scheme: dark;\n  }\n}\n\n[data-ti-theme="gateway"] {\n${themed(themes.gateway)}\n  color-scheme: dark;\n}\n`;
  const catalog = Object.fromEntries(Object.entries(themes).map(([theme, tokens]) => [theme, [...tokens].map(([path, token]) => ({
    path,
    css: cssName(path),
    type: token.$type,
    value: serialize(resolve(path, tokens), false),
    alias: reference(token.$value),
    description: token.$description,
  }))]));
  return new Map([
    ["styles/tokens.css", css],
    ["tokens/catalog.js", `/* Generated for the offline preview. */\nwindow.TEAL_INK_TOKENS = ${JSON.stringify(catalog)};\n`],
  ]);
}
