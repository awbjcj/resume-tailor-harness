import { readFile, writeFile } from "node:fs/promises";
import { generatedFiles, root } from "./token-tools.mjs";

const check = process.argv.includes("--check");
for (const [path, contents] of await generatedFiles()) {
  const url = new URL(path, root);
  if (check) {
    if (await readFile(url, "utf8") !== contents) throw new Error(`Stale generated file: ${path}`);
  } else {
    await writeFile(url, contents);
  }
  console.log(`${check ? "Verified" : "Generated"} ${path}`);
}
