// Test-only TypeScript loading using this standalone package's existing compiler.
// No runtime build, installed app, external repository, or network is involved.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('../node_modules/typescript');
const sourceRoot = path.resolve(__dirname, '../src');
const priorResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...rest) {
  const ownParent = parent?.filename?.startsWith(sourceRoot + path.sep);
  return priorResolve.call(this, ownParent && request.startsWith('@/')
    ? path.join(sourceRoot, request.slice(2)) : request, parent, ...rest);
};
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => {
    if (!filename.startsWith(sourceRoot + path.sep)) throw Error('Test source escaped standalone src');
    const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      fileName: filename,
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    });
    module._compile(result.outputText, filename);
  };
}
// Static-render tests inspect HTML, while the real stylesheet is checked in the native UI.
require.extensions['.css'] = () => {};
require.extensions['.png'] = (module,filename) => {module.exports=filename;};
module.exports = relative => require(path.join(sourceRoot, relative));
