import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const siteDir = path.resolve(__dirname, "..");
const srcDir = path.join(siteDir, "src");
const distDir = path.join(siteDir, "dist");

let errorCount = 0;

function logError(file, lineNum, msg) {
  console.error(`[ERROR] ${path.relative(siteDir, file)}:${lineNum ?? ""}: ${msg}`);
  errorCount++;
}

// Block-level HTML tags that can enclose content in Markdown
const BLOCK_TAGS = new Set([
  "div", "section", "article", "table", "thead", "tbody", "tr", "td", "th",
  "ul", "ol", "li", "p", "aside", "nav", "main", "header", "footer", "figure", "figcaption"
]);

function getMarkdownFiles(dir) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...getMarkdownFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(full);
    }
  }
  return files;
}

function getHtmlFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...getHtmlFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".html")) {
      files.push(full);
    }
  }
  return files;
}

function getParquetFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...getParquetFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".parquet")) {
      files.push(full);
    }
  }
  return files;
}

// 1. Check markdown files for indented ```js or ```js inside HTML
const mdFiles = getMarkdownFiles(srcDir);
for (const file of mdFiles) {
  const content = fs.readFileSync(file, "utf-8");
  const lines = content.split(/\r?\n/);
  const tagStack = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;

    // Check for indented ```js or ```javascript
    if (/^\s+```(?:js|javascript)\b/.test(line)) {
      logError(file, lineNum, "```js code fence is indented. Fences must be at column 0.");
    }

    // Check if fence appears inside an open HTML tag
    if (line.trimStart().startsWith("```js") || line.trimStart().startsWith("```javascript")) {
      if (tagStack.length > 0) {
        logError(
          file,
          lineNum,
          `\`\`\`js fence is nested inside unclosed HTML element(s): <${tagStack.join("> <")}>`
        );
      }
    }

    // Track HTML tags on this line (simple balanced scanner)
    const tagMatches = line.matchAll(/<\/?([a-zA-Z0-9]+)(\s[^>]*)?(\/?)>/g);
    for (const match of tagMatches) {
      const isClosing = match[0].startsWith("</");
      const isSelfClosing = match[3] === "/" || match[0].endsWith("/>");
      const tagName = match[1].toLowerCase();

      if (!BLOCK_TAGS.has(tagName) || isSelfClosing) {
        continue;
      }

      if (isClosing) {
        const idx = tagStack.lastIndexOf(tagName);
        if (idx !== -1) {
          tagStack.splice(idx, 1);
        }
      } else {
        const closingTag = `</${tagName}>`;
        const restOfLine = line.slice(match.index + match[0].length);
        if (!restOfLine.includes(closingTag)) {
          tagStack.push(tagName);
        }
      }
    }
  }
}

// 2. Check built HTML files for literal "```js" and syntax-check module scripts
const htmlFiles = getHtmlFiles(distDir);
let moduleScriptCount = 0;
for (const file of htmlFiles) {
  const content = fs.readFileSync(file, "utf-8");
  if (content.includes("```js") || content.includes("```javascript")) {
    logError(file, null, "Built HTML contains literal '```js' text indicating an unparsed fence.");
  }

  // Extract each compiled <script type="module"> and run node --check
  const scriptRegex = /<script\s+type=["']module["']>([\s\S]*?)<\/script>/gi;
  let match;
  let fileScriptIdx = 0;
  while ((match = scriptRegex.exec(content)) !== null) {
    fileScriptIdx++;
    moduleScriptCount++;
    const scriptCode = match[1];
    const tempFile = path.join(
      os.tmpdir(),
      `obs_check_${path.basename(file, ".html")}_${fileScriptIdx}_${Date.now()}.mjs`
    );
    try {
      fs.writeFileSync(tempFile, scriptCode, "utf-8");
      execFileSync(process.execPath, ["--check", tempFile], { stdio: "pipe" });
    } catch (err) {
      logError(
        file,
        null,
        `Compiled <script type="module"> #${fileScriptIdx} failed node --check:\n${err.stderr?.toString() || err.message}`
      );
    } finally {
      if (fs.existsSync(tempFile)) {
        try {
          fs.unlinkSync(tempFile);
        } catch {}
      }
    }
  }
}

// 3. Check every built .parquet file in dist: must start and end with "PAR1"
const distParquetFiles = getParquetFiles(distDir);
let parquetFileCount = 0;
for (const file of distParquetFiles) {
  parquetFileCount++;
  const buf = fs.readFileSync(file);
  if (buf.length < 8) {
    logError(file, null, `Parquet file size (${buf.length} bytes) is less than 8 bytes.`);
    continue;
  }
  const startMagic = buf.subarray(0, 4).toString("utf-8");
  const endMagic = buf.subarray(buf.length - 4).toString("utf-8");
  if (startMagic !== "PAR1" || endMagic !== "PAR1") {
    logError(
      file,
      null,
      `Parquet magic mismatch: starts with '${startMagic}' and ends with '${endMagic}' (expected 'PAR1')`
    );
  }
}

if (errorCount > 0) {
  console.error(`\ncheck_md: FAILED with ${errorCount} error(s).`);
  process.exit(1);
} else {
  console.log(
    `check_md: PASSED. Scanned ${mdFiles.length} markdown file(s), ${htmlFiles.length} built HTML file(s), verified ${moduleScriptCount} module script(s), verified ${parquetFileCount} parquet file(s).`
  );
  process.exit(0);
}
