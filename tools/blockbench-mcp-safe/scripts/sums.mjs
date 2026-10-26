// Deterministic SHA256 manifest for source files. No dependencies or subprocesses.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const ignored=new Set(['.git','node_modules','.DS_Store','SHA256SUMS.txt']);
const files=[];
async function walk(dir,relative='') {
  for(const entry of await fs.readdir(dir,{withFileTypes:true})) {
    if(ignored.has(entry.name))continue;
    const rel=relative?relative+'/'+entry.name:entry.name;
    if(entry.isDirectory())await walk(path.join(dir,entry.name),rel);
    else if(entry.isFile())files.push(rel);
    else throw new Error('Unrecognized or symlinked file in checksum manifest: '+rel);
  }
}
await walk(root);
const results=[];
for(const rel of files.sort()) {
  const buf=await fs.readFile(path.join(root,...rel.split('/')));
  results.push(createHash('sha256').update(buf).digest('hex')+'  '+rel);
}
await fs.writeFile(path.join(root,'SHA256SUMS.txt'),results.join('\n')+'\n');
process.stdout.write(`Wrote checksums for ${results.length} files\n`);
