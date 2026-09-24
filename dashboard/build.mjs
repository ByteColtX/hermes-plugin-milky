import { build } from "esbuild";
import { readFile, writeFile, mkdir } from "node:fs/promises";
const result = await build({
  entryPoints: ["src/index.jsx"],
  bundle: true,
  format: "iife",
  target: "es2022",
  write: false,
  minify: true,
  legalComments: "none",
  jsxFactory: "React.createElement",
});
const files = new Map([
  ["dist/index.js", result.outputFiles[0].contents],
  ["dist/style.css", await readFile("src/style.css")],
]);
await mkdir("dist", { recursive: true });
for (const [path, data] of files) {
  if (process.argv.includes("--check")) {
    if (!(await readFile(path)).equals(Buffer.from(data)))
      throw new Error("构建资源未同步");
  } else await writeFile(path, data);
}
