// Parse the actual standalone import graph, including type and dynamic imports.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

export function collectSourceGraph(directory,config='vite.local-tools.config.ts'){
 const root=fs.realpathSync(directory),require=createRequire(path.join(root,'package.json')),ts=require('typescript');
 const files=new Set(),edges=[],external=new Set(),pending=['local-tools-standalone.html','src/vite-env.d.ts',config];
 const forbidden=name=>name.split('/').some(part=>part.startsWith('.')&&part!=='.')||/^(?:public|supabase|api|n8n|output|backend)\//.test(name)||/\.(?:pem|p12|pfx)$/i.test(name);
 function plain(candidate){
  const relative=path.relative(root,candidate);
  if(relative.startsWith('..')||path.isAbsolute(relative))throw Error('Source reference escapes repository');
  for(let current=candidate;current!==root;current=path.dirname(current))if(fs.lstatSync(current).isSymbolicLink())throw Error('Source symlink rejected: '+relative);
  if(!fs.statSync(candidate).isFile())throw Error('Source is not a file: '+relative);
  return relative.split(path.sep).join('/');
 }
 function resolve(source,specifier,kind){
  if(!specifier||/^(?:https?:|data:|node:|#)/.test(specifier))return;
  let candidate;
  if(specifier.startsWith('@/'))candidate=path.join(root,'src',specifier.slice(2));
  else if(specifier.startsWith('/src/'))candidate=path.join(root,specifier.slice(1));
  else if(specifier.startsWith('.'))candidate=path.resolve(root,path.dirname(source),specifier);
  else {external.add(specifier);return;}
  candidate=candidate.split('?')[0].split('#')[0];
  // The Vite alias new URL('./src', import.meta.url) names a directory, not all source.
  if(kind==='url'&&fs.existsSync(candidate)&&fs.statSync(candidate).isDirectory())return;
  const choices=[candidate,...['.ts','.tsx','.mts','.cts','.js','.mjs','.cjs','.json','.css'].map(suffix=>candidate+suffix),...['index.ts','index.tsx','index.js'].map(file=>path.join(candidate,file))];
  const target=choices.find(file=>fs.existsSync(file)&&fs.statSync(file).isFile());
  if(!target)throw Error('Missing '+kind+' source reference: '+source+' -> '+specifier);
  const name=plain(target);if(forbidden(name))throw Error('Excluded source reference: '+name);
  edges.push({source,specifier,target:name,kind});if(!files.has(name))pending.push(name);
 }
 while(pending.length){
  const name=pending.pop();if(files.has(name))continue;if(forbidden(name))throw Error('Excluded source: '+name);
  const file=path.join(root,name);plain(file);files.add(name);const text=fs.readFileSync(file,'utf8');
  if(/\.(?:[cm]?ts|tsx|[cm]?js|jsx)$/.test(name)){
   const source=ts.createSourceFile(name,text,ts.ScriptTarget.Latest,true);
   const literal=node=>node&&(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node))?node.text:undefined;
   function visit(node){
    if((ts.isImportDeclaration(node)||ts.isExportDeclaration(node))&&node.moduleSpecifier)resolve(name,literal(node.moduleSpecifier),'module');
    else if(ts.isImportTypeNode(node)&&ts.isLiteralTypeNode(node.argument))resolve(name,literal(node.argument.literal),'type');
    else if(ts.isCallExpression(node)&&node.expression.kind===ts.SyntaxKind.ImportKeyword){const specifier=literal(node.arguments[0]);if(!specifier)throw Error('Computed dynamic import cannot be audited: '+name);resolve(name,specifier,'dynamic');}
    else if(ts.isCallExpression(node)&&ts.isIdentifier(node.expression)&&node.expression.text==='require')resolve(name,literal(node.arguments[0]),'require');
    else if(ts.isNewExpression(node)&&ts.isIdentifier(node.expression)&&node.expression.text==='URL'){
     const specifier=literal(node.arguments?.[0]);if(specifier?.startsWith('.'))resolve(name,specifier,'url');
    }
    ts.forEachChild(node,visit);
   }
   visit(source);
  }else if(name.endsWith('.css')){
   const css=text.replace(/\/\*[\s\S]*?\*\//g,'');
   for(const match of css.matchAll(/@import\s+(?:url\(\s*)?['"]([^'"]+)['"]/g))resolve(name,match[1],'css');
   for(const match of css.matchAll(/url\(\s*['"]?([^'"\s)]+)['"]?\s*\)/g))resolve(name,match[1],'asset');
  }else if(name.endsWith('.html')){
   for(const match of text.matchAll(/<(?:script|link|img)\b[^>]*?\b(?:src|href)=['"]([^'"]+)['"]/g))resolve(name,match[1],'html');
  }
 }
 return {schemaVersion:1,files:[...files].sort(),edges,external:[...external].sort()};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)process.stdout.write(JSON.stringify(collectSourceGraph(process.argv[2],process.argv[3])));
