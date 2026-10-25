import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {makeStore,readRaw} from '../src/storage.mjs';
import {runTool} from '../src/tools.mjs';
import {handle} from '../src/server.mjs';
import {pngSize} from '../src/png.mjs';
import {samplePose} from '../src/pose.mjs';

async function setup(t,gecko=true){
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-04-'));
 t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const store=await makeStore(root);
 const made=await runTool(store,true,gecko?'bbmodel_geckolib_create':'bbmodel_create',gecko?
   {file:'mob.bbmodel',modid:'mob',identifier:'creature',texture_width:64,texture_height:64}:
   {file:'mob.bbmodel',name:'Creature',texture_width:64,texture_height:64});
 const bone=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:made.revision,operations:[{op:'add_group',name:'body',origin:[0,10,0]}]});
 const cube=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:bone.revision,operations:[{op:'add_cube',name:'Body',group_uuid:bone.changes[0].uuid,from:[-4,7,-2],to:[4,13,2],uv_offset:[0,0]}]});
 return {root,store,revision:cube.revision,bone:bone.changes[0].uuid,cube:cube.changes[0].uuid};
}

test('sample_pose correctly interpolates rotation and wraps looping clips',async t=>{
  const {store,revision}=await setup(t);
  const clips=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:revision,name:'animation.mob.walk',length:2,loop:'loop',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0]},{time:1,value:[0,0,50]},{time:2,value:[0,0,0]}]}]});
  const mid=await runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',animation:'animation.mob.walk',time:.5});
  assert.ok(Math.abs(mid.bones[0].rotation[2]-25)<1e-7);
  const wrapped=await runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',animation:'animation.mob.walk',time:2.5});
  assert.equal(wrapped.sampled_time,.5);assert.equal(wrapped.bones[0].rotation[2],25);
  const notWrapped=await runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',animation:'animation.mob.walk',time:2.5,wrap:false});
  assert.equal(notWrapped.bones[0].rotation[2],0);
  assert.match(clips.revision,/^[0-9a-f]{64}$/);
});
test('easeInOutSine and catmullrom numeric sampling are bounded and deterministic', async t=>{
  const {store,revision}=await setup(t);
  let clip=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:revision,name:'animation.mob.ease',length:2,loop:'once',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0],interpolation:'easeInOutSine'},{time:2,value:[0,0,90]}]}]});
  const p=await runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',animation:'animation.mob.ease',time:.5});
  assert.ok(p.bones[0].rotation[2]>0&&p.bones[0].rotation[2]<45);
  clip=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:clip.revision,name:'animation.mob.ease',replace:true,length:2,loop:'once',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0],interpolation:'catmullrom'},{time:1,value:[0,0,45]},{time:2,value:[0,0,90]}]}]});
  const cp=await runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',animation:'animation.mob.ease',time:.5});
  assert.ok(cp.bones[0].rotation[2]>0&&cp.bones[0].rotation[2]<45);
});
test('quality gates flag bounds and proportions without mutations',async t=>{
 const {store,revision}=await setup(t);
 const a=await runTool(store,false,'bbmodel_quality_gates',{file:'mob.bbmodel',max_span:5,max_axis_ratio:1.3,min_thickness:5});
 assert.equal(a.valid,false);assert.ok(a.errors.some(e=>e.includes('BOUNDS_EXCEEDED')));
 assert.ok(a.errors.some(e=>e.includes('EXTREME_PROPORTION')));
 assert.equal((await readRaw(store,'mob.bbmodel')).revision,revision);
 await assert.rejects(runTool(store,false,'bbmodel_quality_gates',{file:'mob.bbmodel',max_span:-1}),/positive finite/);
});
test('render returns a valid CPU PNG, contact sheet image MCP content, optional atomic write and safe no-overwrite',async t=>{
 const {store,root}=await setup(t);
 const content=await handle({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'bbmodel_render',arguments:{file:'mob.bbmodel',size:96,views:['front','right','iso','top']}}},store,false);
 assert.equal(content.result.isError,false);
 assert.equal(content.result.content[1].mimeType,'image/png');
 assert.deepEqual(pngSize(Buffer.from(content.result.content[1].data,'base64')),{width:192,height:192});
 const saved=await runTool(store,true,'bbmodel_render',{file:'mob.bbmodel',size:64,output_file:'views.png'});
 assert.equal(saved.overwritten,false); assert.equal((await fs.readFile(path.join(root,'views.png'))).readUInt32BE(16),128);
 await assert.rejects(runTool(store,true,'bbmodel_render',{file:'mob.bbmodel',size:64,output_file:'views.png'}),/already exists/);
 await assert.rejects(runTool(store,false,'bbmodel_render',{file:'mob.bbmodel',output_file:'extra.png'}),/Write access disabled/);
 const overwrite=await runTool(store,true,'bbmodel_render',{file:'mob.bbmodel',size:64,output_file:'views.png',overwrite:true});
 assert.equal(overwrite.overwritten,true);
});
test('per-face UV geometry export and deliberate face omissions',async t=>{
 const {store,revision,cube}=await setup(t);
 const edit=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:revision,operations:[{op:'update_cube',uuid:cube,uv_faces:{north:{uv:[0,0,4,6]},south:{uv:[4,0,8,6]},up:{uv:[8,0,12,4]},down:{uv:[12,0,16,4],enabled:false}}}]});
 const out=await runTool(store,false,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel'});
 const geom=out.output['minecraft:geometry'][0].bones[0].cubes[0];
 assert.deepEqual(geom.uv.north,{uv:[0,0],uv_size:[4,6]});
 assert.deepEqual(geom.uv.up,{uv:[12,4],uv_size:[-4,-4]});
 assert.ok(!Object.hasOwn(geom.uv,'down'));
 assert.equal((await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel'})).valid,true);
 await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:edit.revision,operations:[{op:'update_cube',uuid:cube,uv_faces:{north:{uv:[0,0,99,3]}}}]}),/UV_OUTSIDE_TEXTURE/);
});
test('mesh authoring works in Generic .bbmodel; refuses GeckoLib mesh export path',async t=>{
 const {store,revision,bone}=await setup(t,false);
 const mesh={op:'add_mesh',name:'Triangle',group_uuid:bone,vertices:{a:[0,0,0],b:[3,0,0],c:[0,4,0]},faces:{tri:{vertices:['a','b','c'],uv:{a:[0,0],b:[3,0],c:[0,4]}}}};
 const edited=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:revision,operations:[mesh]});
 const model=JSON.parse((await readRaw(store,'mob.bbmodel')).raw);
 assert.equal(model.elements.filter(e=>e.type==='mesh').length,1);
 assert.equal((await runTool(store,false,'bbmodel_validate',{file:'mob.bbmodel'})).valid,true);
 const preview=await runTool(store,false,'bbmodel_render',{file:'mob.bbmodel',size:64});
 assert.match(preview.__mcpImage,/^[A-Za-z0-9+/=]+$/);
 await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:edited.revision,operations:[{...mesh,vertices:{a:[0,0,0],b:[0,0,0],c:[0,0,0]}}]}),/Mesh faces|invalid|Degenerate/i);
});
test('live bridge disabled by default; enabled snapshot read-only and symlink guarded',async t=>{
 const {store,root}=await setup(t);
 const res=await handle({jsonrpc:'2.0',id:2,method:'tools/list'},store,false);
 assert.equal(res.result.tools.some(t=>t.name==='app_status'),false);
 await assert.rejects(runTool(store,false,'app_status',{}),/Live tools disabled/);
 const bridge=path.join(root,'.bbms-live');await fs.mkdir(bridge,{mode:0o700});
 await fs.writeFile(path.join(bridge,'status.json'),JSON.stringify({timestamp:Date.now(),project:'Demo'}));
 await fs.writeFile(path.join(bridge,'scene.json'),JSON.stringify({timestamp:Date.now(),bones:[],cubes:[]}));
 const result=await runTool(store,false,'app_read_scene',{},true);
 assert.equal(result.scene.bones.length,0);
 await fs.unlink(path.join(bridge,'scene.json'));
 await fs.symlink(path.join(bridge,'status.json'),path.join(bridge,'scene.json'));
 await assert.rejects(runTool(store,false,'app_read_scene',{},true),/Unsafe live snapshot/);
});
