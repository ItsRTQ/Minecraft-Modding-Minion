import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {makeStore} from '../src/storage.mjs';
import {runTool,TOOLS} from '../src/tools.mjs';
import {handle} from '../src/server.mjs';
import {inspect,parseModel} from '../src/model.mjs';
import {renderModel} from '../src/render.mjs';

const examples=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../examples');

test('sample_pose and render advertise the same animation parameter in MCP tools/list',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-051-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const store=await makeStore(root);
  const listed=await handle({jsonrpc:'2.0',id:1,method:'tools/list'},store,false);
  const tools=listed.result.tools;
  assert.equal(tools.length,TOOLS.filter(x=>!x.writes&&!x.live).length);
  for(const key of ['bbmodel_sample_pose','bbmodel_render']) {
    const props=tools.find(x=>x.name===key).inputSchema.properties;
    assert.equal(props.animation.type,'string');
    assert.equal(Object.hasOwn(props,'name'),false);
  }
  const sample=tools.find(x=>x.name==='bbmodel_sample_pose');
  assert.ok(sample.inputSchema.required.includes('animation'));
  const init=await handle({jsonrpc:'2.0',id:2,method:'initialize',params:{protocolVersion:'2025-06-18'}},store,false);
  assert.equal(init.result.serverInfo.version,'0.5.1');
  assert.match(init.result.instructions,/animation \(not name\)/);
});

test('sample_pose accepts animation and rejects legacy name with actionable error',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-051-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const store=await makeStore(root);
  let out=await runTool(store,true,'bbmodel_geckolib_create',{file:'mob.bbmodel',modid:'mob',identifier:'mob'});
  out=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:out.revision,operations:[{op:'add_group',name:'body',origin:[0,8,0]}]});
  await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:out.revision,name:'animation.mob.walk',length:1,loop:'once',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0]},{time:1,value:[0,0,90]}]}]});
  const pose=await runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',animation:'animation.mob.walk',time:.5});
  assert.equal(pose.animation,'animation.mob.walk');
  assert.equal(pose.bones[0].rotation[2],45);
  const render=await runTool(store,false,'bbmodel_render',{file:'mob.bbmodel',animation:'animation.mob.walk',time:.5,size:64,views:['front']});
  assert.equal(render.animation,pose.animation);
  assert.equal(render.sampled_time,pose.sampled_time);
  await assert.rejects(runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',name:'animation.mob.walk',time:.5}),/Unexpected argument: name\. Valid fields: file, animation, time, wrap/);
  await assert.rejects(runTool(store,false,'bbmodel_sample_pose',{file:'mob.bbmodel',time:.5}),/Missing required argument: animation/);
});

test('validate does not warn that embedded PNG is unparsed or unrendered; warns only on unsupported sources',async()=>{
  const raw=await fs.readFile(path.join(examples,'gecko_test_mob_textured.bbmodel'),'utf8');
  const model=parseModel(raw);
  const result=inspect(model);
  assert.equal(result.valid,true);
  assert.ok(result.warnings.every(w=>!w.includes('not fetched, parsed or rendered')));
  assert.ok(!result.warnings.some(w=>w.includes('TEXTURE_')),JSON.stringify(result.warnings));
  const preview=renderModel(model,{views:['front'],size:64});
  assert.equal(preview.texture_applied,true);
  model.textures[0].source='textures/mob.png';
  assert.match(inspect(model).warnings.join(' '),/TEXTURE_EXTERNAL_UNSUPPORTED/);
  model.textures[0].source='data:image/png;base64,invalid!';
  assert.match(inspect(model).warnings.join(' '),/TEXTURE_EXTERNAL_UNSUPPORTED/);
  model.textures.push({...model.textures[0],uuid:'different'});
  assert.match(inspect(model).warnings.join(' '),/TEXTURE_PREVIEW_LIMIT/);
});
