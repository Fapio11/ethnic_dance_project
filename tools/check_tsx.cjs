const fs = require("fs");
const ts = require("../web/node_modules/typescript/lib/typescript.js");

const file = process.argv[2];
const source = fs.readFileSync(file, "utf8");
const result = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.ESNext,
    jsx: ts.JsxEmit.ReactJSX,
  },
  fileName: file,
  reportDiagnostics: true,
});

const errors = (result.diagnostics || []).filter(
  (diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error,
);

if (errors.length) {
  for (const diagnostic of errors) {
    console.error(ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n"));
  }
  process.exit(1);
}

console.log(`TSX syntax OK: ${file}`);
