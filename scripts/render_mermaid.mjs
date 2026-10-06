import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { argv, env } from "node:process";
import { execFileSync } from "node:child_process";

const [, , inputPath, outputPath, executablePath] = argv;
if (!inputPath || !outputPath || !executablePath) {
  throw new Error("Usage: render_mermaid.mjs <input> <output> <browser>");
}

const globalRoot = env.MERMAID_CLI_ROOT ?? execFileSync("npm", ["root", "-g"], {
  encoding: "utf8",
}).trim();
const cliRoot = join(globalRoot, "@mermaid-js", "mermaid-cli");
const requireFromCli = createRequire(join(cliRoot, "package.json"));
const puppeteer = requireFromCli("puppeteer-core");
const mermaidBundle = join(cliRoot, "node_modules", "mermaid", "dist", "mermaid.min.js");
const definition = await readFile(inputPath, "utf8");

const browser = await puppeteer.launch({
  executablePath,
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
});

try {
  const page = await browser.newPage();
  await page.setContent(
    "<!doctype html><html><body><div id=\"container\"></div></body></html>",
  );
  await page.addScriptTag({ path: mermaidBundle });
  const svg = await page.$eval(
    "#container",
    async (container, source) => {
      globalThis.mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
      const result = await globalThis.mermaid.render("diagram", source, container);
      return result.svg;
    },
    definition,
  );
  await writeFile(outputPath, svg, "utf8");
} finally {
  await browser.close();
}
