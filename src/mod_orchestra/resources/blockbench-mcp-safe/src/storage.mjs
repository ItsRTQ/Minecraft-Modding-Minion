import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

export const MAX_MODEL_BYTES = 5 * 1024 * 1024;
const FILE_RE = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}\.bbmodel$/i;
const WINDOWS_RESERVED = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i;

export function filename(name) {
  if (typeof name !== 'string' || !FILE_RE.test(name) || name.includes('..') || WINDOWS_RESERVED.test(name)) {
    throw new Error('Invalid file name. Use one basename ending in .bbmodel (letters, digits, _, -, . only).');
  }
  return name;
}

export async function makeStore(rootArgument) {
  if (typeof rootArgument !== 'string' || !path.isAbsolute(rootArgument)) throw new Error('--root must be an absolute directory path');
  const root = await fs.realpath(rootArgument);
  if (!(await fs.stat(root)).isDirectory()) throw new Error('--root must point to a directory');
  return {root};
}

export function targetPath(store, name) {
  filename(name);
  const full = path.resolve(store.root, name);
  if (path.dirname(full) !== store.root) throw new Error('Outside workspace');
  return full;
}

export function revision(raw) { return crypto.createHash('sha256').update(raw).digest('hex'); }

async function assertRegularFile(full) {
  const st = await fs.lstat(full);
  if (!st.isFile() || st.nlink !== 1) throw new Error('Refusing symlink, hardlink, or non-regular file');
  if (st.size > MAX_MODEL_BYTES) throw new Error('Model exceeds 5 MiB limit');
  return st;
}

export async function readRaw(store, name) {
  const full = targetPath(store, name);
  const before = await assertRegularFile(full);
  const fh = await fs.open(full, constants.O_RDONLY | (constants.O_NOFOLLOW || 0) | (constants.O_NONBLOCK || 0));
  try {
    const st = await fh.stat();
    if (!st.isFile() || st.nlink !== 1 || st.size > MAX_MODEL_BYTES || st.dev !== before.dev || st.ino !== before.ino) throw new Error('Refusing replaced, unsafe or oversized model');
    const buffer = await fh.readFile();
    if (buffer.byteLength > MAX_MODEL_BYTES) throw new Error('Model exceeds 5 MiB limit');
    return {raw:buffer.toString('utf8'), revision:revision(buffer)};
  } finally { await fh.close(); }
}

export async function listFiles(store) {
  const entries = await fs.readdir(store.root, {withFileTypes:true});
  return entries.filter(e => e.isFile() && FILE_RE.test(e.name) && !e.name.includes('..') && !WINDOWS_RESERVED.test(e.name))
    .map(e => e.name).sort().slice(0, 250);
}

async function withExclusiveLock(full, task) {
  const lock = `${full}.lock`;
  try { await fs.mkdir(lock, {mode:0o700}); }
  catch (err) {
    if (err.code === 'EEXIST') throw new Error(`Model locked: ${path.basename(full)} (check for another writer; remove stale .lock manually only when no writer is active)`);
    throw err;
  }
  try { return await task(); }
  finally { await fs.rmdir(lock).catch(() => {}); }
}

async function writeTemp(store, raw) {
  const temp = path.join(store.root, `.bbms-${crypto.randomBytes(16).toString('hex')}.tmp`);
  const fh = await fs.open(temp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW || 0), 0o600);
  try { await fh.writeFile(raw, 'utf8'); await fh.sync(); }
  catch (err) { await fh.close(); await fs.unlink(temp).catch(() => {}); throw err; }
  await fh.close();
  return temp;
}

export async function saveNew(store, name, raw) {
  const full = targetPath(store, name);
  if (Buffer.byteLength(raw, 'utf8') > MAX_MODEL_BYTES) throw new Error('Model exceeds 5 MiB limit');
  return withExclusiveLock(full, async () => {
    const temp = await writeTemp(store, raw);
    try {
      // Hardlink creation is atomic and fails if the target already exists.
      await fs.link(temp, full);
      return revision(raw);
    } finally { await fs.unlink(temp).catch(() => {}); }
  });
}

export async function saveExisting(store, name, raw, expectedRevision) {
  const full = targetPath(store, name);
  if (typeof expectedRevision !== 'string' || !/^[a-f0-9]{64}$/.test(expectedRevision)) throw new Error('expected_revision (SHA-256) required to edit');
  if (Buffer.byteLength(raw, 'utf8') > MAX_MODEL_BYTES) throw new Error('Model exceeds 5 MiB limit');
  return withExclusiveLock(full, async () => {
    const current = await readRaw(store, name);
    if (current.revision !== expectedRevision) throw new Error('Revision conflict: model was modified; reread before editing');
    const temp = await writeTemp(store, raw);
    try {
      // Recheck immediately before rename. All cooperating writers respect the lock.
      if ((await readRaw(store, name)).revision !== expectedRevision) throw new Error('Revision conflict before rename');
      await fs.rename(temp, full);
      return revision(raw);
    } finally { await fs.unlink(temp).catch(() => {}); }
  });
}

const EXPORT_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(?:geo|animation)\.json$/;
export async function saveExportNew(store,name,raw,kind) {
  if(typeof name!=='string' || !EXPORT_RE.test(name) || name.includes('..') || WINDOWS_RESERVED.test(name) || !name.endsWith(`.${kind}.json`)) throw new Error('Output must be one safe basename ending in .'+kind+'.json');
  if(Buffer.byteLength(raw,'utf8')>MAX_MODEL_BYTES) throw new Error('Export exceeds size limit');
  const full=path.resolve(store.root,name);
  if(path.dirname(full)!==store.root) throw new Error('Outside workspace');
  return withExclusiveLock(full,async()=>{
    const temp=await writeTemp(store,raw);
    try {await fs.link(temp,full);return revision(raw);}
    finally {await fs.unlink(temp).catch(()=>{});}
  });
}

const PNG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.png$/i;
export async function readWorkspacePng(store, name) {
  if(typeof name!=='string' || !PNG_RE.test(name) || name.includes('..') || WINDOWS_RESERVED.test(name)) throw new Error('png_file must be a single safe .png basename inside --root');
  const full=path.resolve(store.root,name);
  if(path.dirname(full)!==store.root) throw new Error('PNG outside workspace');
  const before=await fs.lstat(full);
  if(!before.isFile() || before.nlink!==1 || before.size>2*1024*1024) throw new Error('Refusing unsafe PNG, symlink, hardlink or file >2 MiB');
  const fh=await fs.open(full,constants.O_RDONLY|(constants.O_NOFOLLOW||0)|(constants.O_NONBLOCK||0));
  try {
    const st=await fh.stat();
    if(!st.isFile()||st.nlink!==1||st.dev!==before.dev||st.ino!==before.ino||st.size>2*1024*1024) throw new Error('PNG was replaced or is unsafe');
    const buf=await fh.readFile();
    if(buf.length>2*1024*1024) throw new Error('PNG exceeds size limit');
    return buf;
  } finally {await fh.close();}
}

export async function saveExport(store,name,raw,kind,overwrite=false) {
  if(typeof name!=='string'||!EXPORT_RE.test(name)||name.includes('..')||WINDOWS_RESERVED.test(name)||!name.endsWith(`.${kind}.json`)) throw new Error('Output must be one safe basename ending in .'+kind+'.json');
  if(typeof overwrite!=='boolean') throw new Error('overwrite must be boolean');
  if(Buffer.byteLength(raw,'utf8')>MAX_MODEL_BYTES) throw new Error('Export exceeds 5 MiB limit');
  const full=path.resolve(store.root,name);
  if(path.dirname(full)!==store.root) throw new Error('Outside workspace');
  return withExclusiveLock(full,async()=>{
    if(!overwrite) {
      const temp=await writeTemp(store,raw);
      try {await fs.link(temp,full);return {path:name,overwritten:false,sha256:revision(raw)};}
      finally {await fs.unlink(temp).catch(()=>{});}
    }
    let original;
    try {
      const before=await fs.lstat(full);
      if(!before.isFile()||before.nlink!==1||before.size>MAX_MODEL_BYTES) throw new Error('Refusing unsafe export target (symlink/hardlink/nonregular/oversized)');
      const fh=await fs.open(full,constants.O_RDONLY|(constants.O_NOFOLLOW||0)|(constants.O_NONBLOCK||0));
      try {const st=await fh.stat();if(!st.isFile()||st.nlink!==1||st.dev!==before.dev||st.ino!==before.ino||st.size>MAX_MODEL_BYTES) throw new Error('Export target changed during read');original={dev:st.dev,ino:st.ino};}
      finally {await fh.close();}
    } catch(e) {
      if(e.code==='ENOENT') return saveNewExportUnderLock(store,full,name,raw);
      throw e;
    }
    const temp=await writeTemp(store,raw);
    try {
      const current=await fs.lstat(full);
      if(!current.isFile()||current.nlink!==1||current.dev!==original.dev||current.ino!==original.ino) throw new Error('Export target changed before atomic rename');
      await fs.rename(temp,full);
      return {path:name,overwritten:true,sha256:revision(raw)};
    } finally {await fs.unlink(temp).catch(()=>{});}
  });
}
async function saveNewExportUnderLock(store,full,name,raw) {
  const temp=await writeTemp(store,raw);
  try {await fs.link(temp,full);return {path:name,overwritten:false,sha256:revision(raw)};}
  finally {await fs.unlink(temp).catch(()=>{});}
}

// Save PNG preview with the same exclusive lock/atomic hardlink or safe rename policy as JSON exports.
export async function savePreview(store,name,buffer,overwrite=false){
  if(typeof name!=='string'||!PNG_RE.test(name)||name.includes('..')||WINDOWS_RESERVED.test(name))throw Error('output_file must be a safe .png basename');
  if(!Buffer.isBuffer(buffer)||buffer.length>2*1024*1024)throw Error('Invalid or oversized render PNG');
  if(typeof overwrite!=='boolean')throw Error('overwrite must be boolean');
  const full=path.resolve(store.root,name);
  if(path.dirname(full)!==store.root)throw Error('Outside workspace');
  return withExclusiveLock(full,async()=>{
    let previous=null;
    try{
      const prior=await fs.lstat(full);
      if(!prior.isFile()||prior.nlink!==1||prior.size>2*1024*1024)throw Error('Unsafe PNG export target');
      const fh=await fs.open(full,constants.O_RDONLY|(constants.O_NOFOLLOW||0));
      try{const now=await fh.stat();if(!now.isFile()||now.nlink!==1||now.dev!==prior.dev||now.ino!==prior.ino)throw Error('PNG export target changed');previous={dev:now.dev,ino:now.ino};}
      finally{await fh.close();}
    }catch(e){if(e.code!=='ENOENT')throw e;}
    if(previous&&!overwrite)throw Error('Output PNG already exists (set overwrite: true intentionally)');
    const temp=path.join(store.root,'.bbms-'+crypto.randomBytes(16).toString('hex')+'.tmp');
    const fh=await fs.open(temp,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|(constants.O_NOFOLLOW||0),0o600);
    try{await fh.writeFile(buffer);await fh.sync();}finally{await fh.close();}
    try{
      if(previous){const check=await fs.lstat(full);if(check.dev!==previous.dev||check.ino!==previous.ino||!check.isFile()||check.nlink!==1)throw Error('PNG export target changed');await fs.rename(temp,full);}
      else await fs.link(temp,full);
      return {path:name,overwritten:!!previous,sha256:revision(buffer)};
    }finally{await fs.unlink(temp).catch(()=>{});}
  });
}
