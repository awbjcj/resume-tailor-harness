import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { generatedFiles, loadThemes, readJSON, reference, resolve, root, serialize } from "./token-tools.mjs";

const { base, themes } = await loadThemes();
const names = new Set();
for (const [themeName, theme] of Object.entries(themes)) {
  for (const [path, token] of theme) {
    assert.ok(token.$description?.trim(), `${themeName}:${path} needs a description`);
    assert.ok(token.$type, `${path} needs a type`);
    const target = reference(token.$value);
    if (path.startsWith("primitive.")) assert.equal(target, null, `Primitive alias: ${path}`);
    if (path.startsWith("semantic.")) assert.ok(target?.startsWith("primitive."), `Semantic must reference primitive: ${path}`);
    if (path.startsWith("component.")) assert.ok(target?.startsWith("semantic."), `Component must reference semantic: ${path}`);
    const resolved = resolve(path, theme);
    serialize(resolved, false);
    const value = resolved.$value;
    if (resolved.$type === "color") {
      assert.equal(value.colorSpace, "srgb");
      assert.equal(value.components.length, 3);
      assert.ok(value.components.every((channel) => Number.isFinite(channel) && channel >= 0 && channel <= 1), path);
      assert.ok(value.alpha >= 0 && value.alpha <= 1, path);
    }
    if (resolved.$type === "dimension") {
      assert.ok(["px", "rem"].includes(value.unit), path);
      assert.ok(Number.isFinite(value.value), path);
    }
    if (resolved.$type === "duration") {
      assert.ok(["ms", "s"].includes(value.unit), path);
      assert.ok(Number.isFinite(value.value) && value.value >= 0, path);
    }
  }
}

function luminance(color) {
  const channels = color.components.map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
}
function contrast(a, b) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + .05) / (values[1] + .05);
}
const pairs = [
  ["foreground", "background", 4.5], ["card-foreground", "card", 4.5],
  ["muted-foreground", "background", 4.5], ["muted-foreground", "card", 4.5],
  ["on-muted", "muted", 4.5], ["primary-foreground", "primary", 4.5],
  ["accent-foreground", "accent", 4.5], ["primary", "card", 4.5],
  ["field-border", "card", 3], ["ring", "background", 3],
];
let contrastCount = 0;
for (const [name, theme] of Object.entries(themes)) {
  for (const [foreground, background, minimum] of pairs) {
    const ratio = contrast(resolve(`semantic.color.${foreground}`, theme).$value, resolve(`semantic.color.${background}`, theme).$value);
    assert.ok(ratio >= minimum, `${name}: ${foreground} on ${background} = ${ratio.toFixed(2)} < ${minimum}`);
    contrastCount++;
  }
}

const manifest = await readJSON("source-manifest.json");
let fidelityCount = 0;
for (const mode of ["light", "dark"]) {
  for (const [key, raw] of Object.entries(manifest.sourceThemes[mode])) {
    if (!raw.startsWith("#")) continue;
    const exported = serialize(resolve(`semantic.color.${key}`, themes[mode]), false);
    assert.equal(exported.toLowerCase(), raw.toLowerCase(), `Source drift: ${mode}.${key}`);
    fidelityCount++;
  }
}

for (const [path, contents] of await generatedFiles()) {
  assert.equal(await readFile(new URL(path, root), "utf8"), contents, `Stale generated output: ${path}`);
}
const html = await readFile(new URL("preview.html", root), "utf8");
for (const match of html.matchAll(/<(?:link|script|a|img)\b[^>]*\b(?:href|src)="([^"#]+)"/g)) {
  if (/^(?:https?:|data:|mailto:)/.test(match[1])) continue;
  const target = new URL(match[1].split("#")[0], root);
  assert.ok(target.href.startsWith(root.href), `Escaping local asset: ${match[1]}`);
  await access(target);
}
for (const path of ["README.md", "DESIGN-BRIEF.md", "docs/DESIGN-SYSTEM.md", "docs/ADOPTION.md", "docs/SOURCE-AUDIT.md", "docs/VERIFICATION.md", "CHANGELOG.md"]) {
  const text = await readFile(new URL(path, root), "utf8");
  for (const match of text.matchAll(/\]\(([^)]+)\)/g)) {
    const link = match[1];
    if (/^(?:https?:|#)/.test(link)) continue;
    await access(new URL(link.split("#")[0], new URL(path, root)));
  }
}
for (const path of ["styles/components.css", "styles/preview.css"]) {
  const text = await readFile(new URL(path, root), "utf8");
  assert.ok(!/#[\da-f]{3,8}\b|\brgba?\s*\(/i.test(text), `Hardcoded color in ${path}`);
}
const { cssName } = await import("./token-tools.mjs");
for (const path of base.keys()) {
  assert.ok(!names.has(cssName(path)), `Duplicate CSS variable: ${path}`);
  names.add(cssName(path));
}
// These guards verify that token edits cannot silently create broken exports.
assert.throws(() => resolve("missing", base), /Missing token/);
assert.throws(() => resolve("a", new Map([["a", { $type: "number", $value: "{b}" }], ["b", { $type: "number", $value: "{a}" }]])), /Circular token/);
assert.throws(() => resolve("a", new Map([["a", { $type: "number", $value: "{b}" }], ["b", { $type: "color", $value: { colorSpace: "srgb", components: [0, 0, 0], alpha: 1 } }]])), /Type mismatch/);
console.log(`PASS ${base.size} base tokens, ${Object.keys(themes).length} themes, ${contrastCount} contrast pairs, ${fidelityCount} exact source colors, fresh exports, and local artifact links.`);
console.log(`Artifact: ${fileURLToPath(root)}`);
