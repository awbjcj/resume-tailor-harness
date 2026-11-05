import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { runInNewContext } from "node:vm";
import assert from "node:assert/strict";
import { root } from "./token-tools.mjs";

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}
const artifactPath = fileURLToPath(root);
const require = createRequire(pathToFileURL(resolve(option("--modules-from", resolve(artifactPath, "package.json")))));
const evidencePath = resolve(option("--evidence", resolve(artifactPath, "evidence")));
await mkdir(evidencePath, { recursive: true });
const report = { timestamp: new Date().toISOString(), checks: [] };
try {
  const ts = require("typescript");
  const reactTypes = dirname(require.resolve("@types/react/package.json"));
  const options = {
    target: ts.ScriptTarget.ES2022,
    lib: ["lib.es2022.d.ts", "lib.dom.d.ts"],
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    jsx: ts.JsxEmit.ReactJSX,
    noEmit: true,
    strict: true,
    noUnusedLocals: true,
    noUnusedParameters: true,
    skipLibCheck: true,
    types: ["react"],
    typeRoots: [dirname(reactTypes)],
    paths: { react: [resolve(reactTypes, "index.d.ts")], "react/jsx-runtime": [resolve(reactTypes, "jsx-runtime.d.ts")] },
  };
  const program = ts.createProgram([resolve(artifactPath, "adapters/react.tsx"), resolve(artifactPath, "examples/Workspace.tsx")], options);
  const diagnostics = ts.getPreEmitDiagnostics(program);
  assert.equal(diagnostics.length, 0, ts.formatDiagnosticsWithColorAndContext(diagnostics, { getCurrentDirectory: () => artifactPath, getCanonicalFileName: (path) => path, getNewLine: () => "\n" }));
  report.checks.push("React adapter and Workspace example pass strict TypeScript with unused-symbol checks");

  const source = await readFile(new URL("adapters/react.tsx", root), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  runInNewContext(compiled, { require, exports, module: { exports } });
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const markup = renderToStaticMarkup(React.createElement("div", null,
    React.createElement(exports.TextField, { label: "Name", hint: "Recognizable name", error: "Enter a name", required: true }),
    React.createElement(exports.TextField, { label: "Second name", hint: "Distinct identifier" }),
    React.createElement(exports.Button, { loading: true, loadingLabel: "Saving" }, "Save"),
  ));
  const ids = [...markup.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length, "Duplicate field IDs");
  for (const match of markup.matchAll(/\b(?:for|aria-describedby)="([^"]+)"/g)) for (const id of match[1].split(" ")) assert.ok(ids.includes(id), `Unbound field reference: ${id}`);
  for (const attribute of ['aria-invalid="true"', 'aria-busy="true"', 'disabled=""', 'type="button"']) assert.ok(markup.includes(attribute), `Missing ${attribute}`);
  report.checks.push("Server-rendered fields have distinct linked IDs and errors; loading buttons expose busy/disabled state");

  const { compile } = require("tailwindcss");
  const adapter = await readFile(new URL("adapters/tailwind-v4.css", root), "utf8");
  const tokens = await readFile(new URL("styles/tokens.css", root), "utf8");
  const compiler = await compile(`${tokens}\n${adapter}\n@tailwind utilities;`);
  const css = compiler.build(["bg-ti-primary", "text-ti-foreground", "rounded-ti-lg", "font-ti-ui", "shadow-ti-card", "dark:bg-ti-card"]);
  for (const selector of [".bg-ti-primary", ".text-ti-foreground", ".rounded-ti-lg", ".font-ti-ui", ".shadow-ti-card"]) assert.ok(css.includes(selector), `Missing compiled utility ${selector}`);
  assert.ok(css.includes("background-color: var(--ti-color-primary)"));
  assert.ok(css.includes('[data-ti-theme="dark"]'));
  report.checks.push("Tailwind v4 compiles six utility variants with semantic CSS variable references");
  report.versions = { typescript: ts.version, react: React.version, tailwind: require("tailwindcss/package.json").version };
  report.status = "pass";
  console.log(`PASS ${report.checks.length} integration checks: TypeScript ${report.versions.typescript}, React ${report.versions.react}, Tailwind ${report.versions.tailwind}`);
} catch (error) {
  report.status = "fail";
  report.failure = error.stack;
  console.error(error);
  process.exitCode = 1;
} finally {
  await writeFile(resolve(evidencePath, "integration-report.json"), JSON.stringify(report, null, 2) + "\n");
}
