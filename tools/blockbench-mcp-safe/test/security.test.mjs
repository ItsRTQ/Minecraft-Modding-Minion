import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {makeStore,filename,readRaw,MAX_MODEL_BYTES} from '../src/storage.mjs';
import {runTool,TOOLS} from '../src/tools.mjs';
import {handle} from '../src/server.mjs';

async function sandbox(t) {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  return {store:await makeStore(root),root};
}
const cube = {op:'add_cube',name:'torso',from:[-4,0,-2],to:[4,8,2]};

test('No code-execution, HTTP, remote import, subprocess or unauthorized live tools exposed',() => {
  const names=TOOLS.map(t=>t.name);
  for (const dangerous of ['risky_eval','trigger_action','bbmodel_import_url','exec','shell','blockbench_launch']) assert.ok(!names.includes(dangerous));
  assert.equal(TOOLS.filter(t=>t.writes).length,8);
});

test('Read-only mode rejects ALL write operations; advertised tools restricted',async t=>{
  const {store}=await sandbox(t);
  await assert.rejects(runTool(store,false,'bbmodel_create',{file:'x.bbmodel'}),/Write access disabled/);
  await assert.rejects(runTool(store,false,'bbmodel_edit',{file:'x.bbmodel',expected_revision:'0'.repeat(64),operations:[cube]}),/Write access disabled/);
  await assert.rejects(runTool(store,false,'bbmodel_duplicate',{file:'x.bbmodel',new_file:'y.bbmodel'}),/Write access disabled/);
  const res=await handle({jsonrpc:'2.0',id:1,method:'tools/list'},store,false);
  assert.equal(res.result.tools.filter(x=>x.name==='bbmodel_create').length,0);
  assert.equal(res.result.tools.filter(x=>x.name==='bbmodel_info').length,1);
});

test('Strict file names: path traversal / absolute paths / Windows separators / reserved names',()=> {
  const bad=['../secret.bbmodel','a/../../foo.bbmodel','/etc/passwd','C:\\Windows\\foo.bbmodel','folder\\model.bbmodel','..bbmodel','.hidden.bbmodel','con.bbmodel','AUX.bbmodel','a..b.bbmodel','a.bbmodel/../../x.bbmodel','bad\0.bbmodel','foo.json','other.bbmodel:stream','a'.repeat(130)+'.bbmodel'];
  for (const input of bad) assert.throws(()=>filename(input),undefined,`input=${input}`);
  assert.equal(filename('safe-01.bbmodel'),'safe-01.bbmodel');
});

test('CRUD, group hierarchy, atomic edit, content revision, duplicate, overwrite refusal',async t=>{
  const {store,root}=await sandbox(t);
  const made=await runTool(store,true,'bbmodel_create',{file:'hero.bbmodel',name:'hero'});
  assert.equal(made.created,'hero.bbmodel');
  const info=await runTool(store,true,'bbmodel_info',{file:'hero.bbmodel'});
  assert.equal(info.cubes,0);
  const g=await runTool(store,true,'bbmodel_edit',{file:'hero.bbmodel',expected_revision:info.revision,operations:[{op:'add_group',name:'torso'}]});
  const uuid=g.changes[0].uuid;
  const e=await runTool(store,true,'bbmodel_edit',{file:'hero.bbmodel',expected_revision:g.revision,operations:[{...cube,group_uuid:uuid}]});
  const cubeId=e.changes[0].uuid;
  const scene=await runTool(store,true,'bbmodel_read_scene',{file:'hero.bbmodel'});
  assert.equal(scene.cubes,1);
  assert.equal(scene.outliner[0].children[0],cubeId);
  assert.deepEqual(scene.elements_detail[0].from,[-4,0,-2]);
  assert.equal((await runTool(store,true,'bbmodel_validate',{file:'hero.bbmodel'})).valid,true);
  await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'hero.bbmodel',expected_revision:g.revision,operations:[{...cube,name:'stale'}]}),/Revision conflict/);
  const updated=await runTool(store,true,'bbmodel_edit',{file:'hero.bbmodel',expected_revision:e.revision,operations:[{op:'update_cube',uuid:cubeId,name:'Chest',to:[4,9,2]}]});
  assert.equal((await runTool(store,true,'bbmodel_info',{file:'hero.bbmodel'})).cubes,1);
  const duplicated=await runTool(store,true,'bbmodel_duplicate',{file:'hero.bbmodel',new_file:'clone.bbmodel'});
  assert.ok(duplicated.revision);
  await assert.rejects(runTool(store,true,'bbmodel_create',{file:'hero.bbmodel'}),{code:'EEXIST'});
  await assert.rejects(runTool(store,true,'bbmodel_duplicate',{file:'hero.bbmodel',new_file:'clone.bbmodel'}),{code:'EEXIST'});
  const removed=await runTool(store,true,'bbmodel_edit',{file:'hero.bbmodel',expected_revision:updated.revision,operations:[{op:'remove_cube',uuid:cubeId},{op:'remove_empty_group',uuid}]});
  assert.equal((await runTool(store,true,'bbmodel_info',{file:'hero.bbmodel'})).cubes,0);
  assert.ok(removed.revision);
  const disk=JSON.parse(await fs.readFile(path.join(root,'hero.bbmodel'),'utf8'));
  assert.equal(disk.meta.format_version,'5.0');
  assert.deepEqual(disk.outliner,[]);
});

test('Invalid operations are all-or-nothing and preserve existing revision',async t=>{
  const {store}=await sandbox(t);
  const made=await runTool(store,true,'bbmodel_create',{file:'work.bbmodel'});
  const edits=[cube,{op:'add_cube',name:'invalid',from:[0,0,0],to:[0,5,5]}];
  await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'work.bbmodel',expected_revision:made.revision,operations:edits}),/smaller/);
  assert.equal((await runTool(store,true,'bbmodel_info',{file:'work.bbmodel'})).revision,made.revision);
  await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'work.bbmodel',expected_revision:made.revision,operations:[{op:'add_cube',name:'hack',from:[0,0,0],to:[1,1,1],unknown:'not allowed'}]}),/Unexpected argument/);
  assert.equal((await runTool(store,true,'bbmodel_info',{file:'work.bbmodel'})).cubes,0);
});

test('Existing symlink and hardlink are rejected; neither read nor edit follows',async t=>{
  const {store,root}=await sandbox(t);
  const outside=path.join(await fs.mkdtemp(path.join(os.tmpdir(),'bbms-outside-')),'private.bbmodel');
  t.after(()=>fs.rm(path.dirname(outside),{recursive:true,force:true}));
  await fs.writeFile(outside,JSON.stringify({meta:{},elements:[],outliner:[]}));
  try {await fs.symlink(outside,path.join(root,'symlink.bbmodel'));}
  catch (err) { if (['EPERM','EACCES','ENOTSUP'].includes(err.code)) return; throw err; }
  await assert.rejects(readRaw(store,'symlink.bbmodel'),/symlink/);
  assert.deepEqual((await runTool(store,false,'bbmodel_list_files',{})).files,[]);
  await assert.rejects(runTool(store,true,'bbmodel_duplicate',{file:'symlink.bbmodel',new_file:'copy.bbmodel'}),/symlink/);
  await fs.link(outside,path.join(root,'hardlink.bbmodel'));
  await assert.rejects(readRaw(store,'hardlink.bbmodel'),/hardlink/);
});

test('Workspace lock fails closed without auto-stealing',async t=>{
  const {store,root}=await sandbox(t);
  await fs.mkdir(path.join(root,'busy.bbmodel.lock'));
  await assert.rejects(runTool(store,true,'bbmodel_create',{file:'busy.bbmodel'}),/locked/);
  assert.deepEqual(await fs.readdir(root),['busy.bbmodel.lock']);
});

test('Reject oversized model and malformed JSON',async t=>{
  const {store,root}=await sandbox(t);
  await fs.writeFile(path.join(root,'large.bbmodel'),'x'.repeat(MAX_MODEL_BYTES+1));
  await assert.rejects(readRaw(store,'large.bbmodel'),/exceeds/);
  await fs.writeFile(path.join(root,'broken.bbmodel'),'{not json');
  await assert.rejects(runTool(store,false,'bbmodel_info',{file:'broken.bbmodel'}),/Invalid.*JSON/);
});

test('Reject deep unsafe keys and outliner abuse without writing',async t=>{
  const {store,root}=await sandbox(t);
  await fs.writeFile(path.join(root,'evil.bbmodel'),'{{');
  const evil='{"meta":{"format_version":"5.0","model_format":"free"},"elements":[],"outliner":[],"__proto__":{"x":1}}';
  await fs.writeFile(path.join(root,'evil.bbmodel'),evil);
  await assert.rejects(runTool(store,false,'bbmodel_info',{file:'evil.bbmodel'}),/Unsafe JSON key/);
});

test('MCP errors are structured, no stacks; malformed requests do not trigger code execution',async t=>{
  const {store}=await sandbox(t);
  const message={jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'risky_eval',arguments:{code:'process.exit(1)'}}};
  const res=await handle(message,store,true);
  assert.equal(res.result.isError,true);
  assert.match(res.result.content[0].text,/Unknown tool/);
  assert.equal(await handle({jsonrpc:'2.0',method:'notifications/initialized'},store,true),null);
  assert.equal((await handle({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2024-11-05'}},store,true)).result.protocolVersion,'2024-11-05');
});

test('Concurrent writers with same revision: only one succeeds',async t=>{
  const {store}=await sandbox(t);
  const made=await runTool(store,true,'bbmodel_create',{file:'shared.bbmodel'});
  const makeArgs=name=>({file:'shared.bbmodel',expected_revision:made.revision,operations:[{...cube,name}]});
  const outcomes=await Promise.allSettled([
    runTool(store,true,'bbmodel_edit',makeArgs('one')),
    runTool(store,true,'bbmodel_edit',makeArgs('two'))
  ]);
  assert.equal(outcomes.filter(o=>o.status==='fulfilled').length,1);
  assert.equal(outcomes.filter(o=>o.status==='rejected').length,1);
  assert.equal((await runTool(store,false,'bbmodel_info',{file:'shared.bbmodel'})).cubes,1);
});

test('Negative tests: coordinates, invalid types and malformed revisions',async t=>{
  const {store}=await sandbox(t);
  const made=await runTool(store,true,'bbmodel_create',{file:'bounds.bbmodel'});
  const invalids=[
    {...cube,from:[-9999,0,0]},
    {...cube,to:[Infinity,3,3]},
    {...cube,rotation:[0,361,0]},
    {...cube,name:'bad\nname'},
    {...cube,from:[1,1,1],to:[0,0,0]},
    {op:'add_group',name:'new',parent_group_uuid:'not-found'},
    {op:'unknown'}
  ];
  for (const op of invalids) {
    await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'bounds.bbmodel',expected_revision:made.revision,operations:[op]}));
  }
  assert.equal((await runTool(store,true,'bbmodel_info',{file:'bounds.bbmodel'})).revision,made.revision);
});
