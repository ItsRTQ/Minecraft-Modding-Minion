import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {makeStore,readRaw} from '../src/storage.mjs';
import {runTool} from '../src/tools.mjs';
import {parseModel} from '../src/model.mjs';
import {exportGeometry,exportAnimations,validateGecko} from '../src/geckolib.mjs';

async function workspace(t) {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-geo-'));
  t.after(()=>fs.rm(root,{force:true,recursive:true}));
  return {root,store:await makeStore(root)};
}
async function project(store,name='mob') {
  return runTool(store,true,'bbmodel_geckolib_create',{file:`${name}.bbmodel`,name:'Example Mob',modid:'test_mod',identifier:name,texture_width:64,texture_height:64});
}
async function addRig(store, rev,file='mob.bbmodel') {
  return runTool(store,true,'bbmodel_edit',{file,expected_revision:rev,operations:[
    {op:'add_group',name:'root',origin:[0,0,0]},
    {op:'add_group',name:'body',origin:[0,12,0]},
    {op:'add_group',name:'left_leg',origin:[-3,12,0]}
  ]});
}
const idle=[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0]},{time:0.5,value:[2,0,0]},{time:1,value:[0,0,0]}]}];
const walk=[{bone:'left_leg',channel:'rotation',keyframes:[{time:0,value:[30,0,0]},{time:0.25,value:[-30,0,0]},{time:0.5,value:[30,0,0]}]}];

test('GeckoLib end-to-end: .bbmodel rig and animation exports have proper namespace, hierarchy and X mirror',async t=>{
  const {root,store}=await workspace(t);
  const made=await project(store);
  const rigRoot=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:made.revision,operations:[{op:'add_group',name:'root',origin:[1,0,2]}]});
  const rootId=rigRoot.changes[0].uuid;
  const rigBody=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:rigRoot.revision,operations:[{op:'add_group',name:'body',origin:[0,12,0],parent_group_uuid:rootId}]});
  const bodyId=rigBody.changes[0].uuid;
  const rigLeg=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:rigBody.revision,operations:[{op:'add_group',name:'left_leg',origin:[-3,12,0],parent_group_uuid:bodyId}]});
  const legId=rigLeg.changes[0].uuid;
  const bones=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:rigLeg.revision,operations:[
    {op:'add_cube',name:'torso',from:[-4,12,-2],to:[4,24,2],group_uuid:bodyId,uv_offset:[0,0]},
    {op:'add_cube',name:'leg',from:[-5,0,-2],to:[-1,12,2],group_uuid:legId,uv_offset:[0,16],inflate:0.1}
  ]});
  const animIdle=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:bones.revision,name:'animation.mob.idle',length:1,loop:'loop',channels:idle});
  const animWalk=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:animIdle.revision,name:'animation.mob.walk',length:0.5,loop:'loop',channels:walk});
  const validation=await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel'});
  assert.equal(validation.valid,true,JSON.stringify(validation.errors));
  assert.equal(validation.counts.bones,3);
  const geo=(await runTool(store,false,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel'})).output;
  assert.equal(geo.format_version,'1.12.0');
  assert.equal(geo['minecraft:geometry'][0].description.identifier,'geometry.mob');
  const outBones=geo['minecraft:geometry'][0].bones;
  assert.deepEqual(outBones.map(b=>b.name),['root','body','left_leg']);
  assert.deepEqual(outBones[0].pivot,[-1,0,2]);
  assert.equal(outBones[1].parent,'root');
  assert.equal(outBones[2].parent,'body');
  assert.deepEqual(outBones[2].cubes[0].origin,[1,0,-2]);
  assert.deepEqual(outBones[2].cubes[0].size,[4,12,4]);
  assert.deepEqual(outBones[2].cubes[0].uv,[0,16]);
  const animations=(await runTool(store,false,'bbmodel_geckolib_export_animations',{file:'mob.bbmodel'})).output;
  assert.equal(animations.format_version,'1.8.0');
  assert.equal(animations.geckolib_format_version,2);
  assert.deepEqual(Object.keys(animations.animations),['animation.mob.idle','animation.mob.walk']);
  assert.deepEqual(animations.animations['animation.mob.walk'].bones.left_leg.rotation['0.0'].vector,[-30,0,0]);
  const eg=await runTool(store,true,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel',output_file:'mob.geo.json'});
  const ea=await runTool(store,true,'bbmodel_geckolib_export_animations',{file:'mob.bbmodel',output_file:'mob.animation.json'});
  assert.ok(eg.revision && ea.revision);
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(root,'mob.geo.json'),'utf8')),geo);
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(root,'mob.animation.json'),'utf8')),JSON.parse(JSON.stringify(animations)));
  await assert.rejects(runTool(store,true,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel',output_file:'mob.geo.json'}),{code:'EEXIST'});
});

test('Read-only mode can compile exports but cannot write exports',async t=>{
  const {store}=await workspace(t);
  await project(store);
  assert.equal((await runTool(store,false,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel'})).output.format_version,'1.12.0');
  await assert.rejects(runTool(store,false,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel',output_file:'some.geo.json'}),/Write access disabled/);
  await assert.rejects(runTool(store,false,'bbmodel_geckolib_create',{file:'new.bbmodel',modid:'x',identifier:'new'}),/Write access disabled/);
});

test('Invalid namespace, identifier, bones and unparented cube rejected without changes',async t=>{
  const {store}=await workspace(t);
  for(const modid of ['Bad-Mod','../escape','a:b','A']) await assert.rejects(runTool(store,true,'bbmodel_geckolib_create',{file:'bad.bbmodel',identifier:'mob',modid}));
  const made=await project(store);
  const rev=made.revision;
  for(const operations of [[{op:'add_group',name:'space bone'}],[{op:'add_cube',name:'invalid',from:[0,0,0],to:[1,1,1]}],[{op:'add_group',name:'same'},{op:'add_group',name:'same'}]]) {
    await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:rev,operations}));
    assert.equal((await runTool(store,false,'bbmodel_info',{file:'mob.bbmodel'})).revision,rev);
  }
  const badExports=['../escape.geo.json','nested/f.geo.json','C:\\temp\\f.geo.json','malicious.animation.json','.hidden.geo.json','foo..geo.json'];
  for (const output_file of badExports) await assert.rejects(runTool(store,true,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel',output_file}));
});

test('Loop seams, nonexistent bone, duplicate channels and wrong keyframes rejected atomically',async t=>{
  const {store}=await workspace(t);
  const made=await project(store);
  const rig=await addRig(store,made.revision);
  const bad=[
    {name:'animation.mob.bad',length:1,loop:'loop',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0]},{time:1,value:[1,0,0]}]}]},
    {name:'animation.mob.bad',length:1,loop:'loop',channels:[{bone:'not_found',channel:'rotation',keyframes:[{time:0,value:[0,0,0]},{time:1,value:[0,0,0]}]}]},
    {name:'animation.mob.bad',length:1,loop:'once',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0.5,value:[1,0,0]},{time:0.2,value:[2,0,0]}]}]},
    {name:'animation.mob.bad',length:1,loop:'once',channels:[{bone:'body',channel:'scale',keyframes:[{time:0,value:[-1,1,1]}]}]},
    {name:'animation.mob.bad',length:1,loop:'once',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0]}]},{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0]}]}]}
  ];
  for(const b of bad) {
    await assert.rejects(runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:rig.revision,...b}));
    assert.equal((await runTool(store,false,'bbmodel_info',{file:'mob.bbmodel'})).revision,rig.revision);
  }
});

test('Validator refuses unknown geometry & unsupported keyframe interpolation instead of silently discarding',async t=>{
  const {store}=await workspace(t);
  const made=await project(store);
  const rig=await addRig(store,made.revision);
  const bb=parseModel((await readRaw(store,'mob.bbmodel')).raw);
  bb.elements.push({uuid:'unsupported-mesh',type:'mesh'});
  bb.outliner.push('unsupported-mesh');
  const result=validateGecko(bb);
  assert.equal(result.valid,false);
  assert.ok(result.errors.some(e=>e.includes('CUBE_GEOMETRY')));
  assert.throws(()=>exportGeometry(bb),/validation failed/);
  assert.throws(()=>exportAnimations(bb),/validation failed/);
});

test('GeckoLib expected idle/walk clips must be present when explicitly required',async t=>{
  const {store}=await workspace(t);
  await project(store);
  const result=await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel',required_animations:['animation.mob.idle','animation.mob.walk']});
  assert.equal(result.valid,false);
  assert.equal(result.errors.filter(x=>x.startsWith('REQUIRED_ANIMATION_MISSING')).length,2);
});

test('GeckoLib unknown interpolation in existing animation is rejected instead of silently exported',async t=>{
  const {store,root}=await workspace(t);
  const made=await project(store);
  const rig=await addRig(store,made.revision);
  const anim=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:rig.revision,name:'animation.mob.idle',length:1,loop:'once',channels:idle});
  const corrupted=parseModel((await readRaw(store,'mob.bbmodel')).raw);
  const keyframe=Object.values(corrupted.animations[0].animators)[0].keyframes[0];
  keyframe.interpolation='bezier';
  const {saveExisting}=await import('../src/storage.mjs');
  await saveExisting(store,'mob.bbmodel',JSON.stringify(corrupted),anim.revision);
  const result=await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel'});
  assert.equal(result.valid,false);
  assert.ok(result.errors.some(x=>x.includes('KEYFRAME_INVALID')));
  await assert.rejects(runTool(store,false,'bbmodel_geckolib_export_animations',{file:'mob.bbmodel'}),/validation failed/);
});

test('GeckoLib MCP tools are discoverable and enforce read-only via JSON-RPC',async t=>{
  const {store}=await workspace(t);
  const {handle}=await import('../src/server.mjs');
  const list=await handle({jsonrpc:'2.0',id:1,method:'tools/list'},store,false);
  assert.equal(list.result.tools.some(x=>x.name==='bbmodel_geckolib_export_geometry'),true);
  assert.equal(list.result.tools.some(x=>x.name==='bbmodel_geckolib_upsert_animation'),false);
  const create=await handle({jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'bbmodel_geckolib_create',arguments:{file:'x.bbmodel',modid:'a',identifier:'x'}}},store,false);
  assert.equal(create.result.isError,true);
  const createAllowed=await handle({jsonrpc:'2.0',id:3,method:'tools/call',params:{name:'bbmodel_geckolib_create',arguments:{file:'x.bbmodel',modid:'a',identifier:'x'}}},store,true);
  assert.equal(createAllowed.result.isError,false);
  const compile=await handle({jsonrpc:'2.0',id:4,method:'tools/call',params:{name:'bbmodel_geckolib_export_geometry',arguments:{file:'x.bbmodel'}}},store,false);
  assert.equal(compile.result.isError,false);
  assert.equal(JSON.parse(compile.result.content[0].text).output.format_version,'1.12.0');
});
