import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {makeStore} from '../src/storage.mjs';
import {runTool} from '../src/tools.mjs';

const fixture=path.join(path.dirname(fileURLToPath(import.meta.url)),'fixtures','blockbench5_geckolib_min.bbmodel');
const exists=await fs.access(fixture).then(()=>true,()=>false);
test('Real Blockbench 5.x GeckoLib fixture structural compatibility (human-supplied only)',{skip:!exists?'Human-generated Blockbench 5 fixture has not been supplied':false},async t=>{
  const native=JSON.parse(await fs.readFile(fixture,'utf8'));
  assert.equal(native.meta.model_format,'geckolib_model');
  assert.ok(native.elements.length>=1&&native.animations.length>=1);
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-fixture-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const store=await makeStore(root);
  const made=await runTool(store,true,'bbmodel_geckolib_create',{file:'fixture.bbmodel',name:'Fixture',identifier:'fixture',modid:'fixture',texture_width:64,texture_height:64});
  const bone=await runTool(store,true,'bbmodel_edit',{file:'fixture.bbmodel',expected_revision:made.revision,operations:[{op:'add_group',name:'body',origin:[0,0,0]}]});
  const cube=await runTool(store,true,'bbmodel_edit',{file:'fixture.bbmodel',expected_revision:bone.revision,operations:[{op:'add_cube',name:'part',from:[0,0,0],to:[2,2,2],group_uuid:bone.changes[0].uuid,uv_offset:[0,0]}]});
  await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'fixture.bbmodel',expected_revision:cube.revision,name:'animation.fixture.idle',length:1,loop:'once',channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0]}]}]});
  const ours=JSON.parse(await fs.readFile(path.join(root,'fixture.bbmodel'),'utf8'));
  const keys=x=>Object.keys(x||{}).sort();
  assert.deepEqual(keys(ours.meta),keys(native.meta),'meta keys');
  assert.deepEqual(keys(ours.elements[0]),keys(native.elements[0]),'cube element keys');
  assert.deepEqual(keys(ours.animations[0]),keys(native.animations[0]),'animation keys');
  assert.deepEqual(keys(ours.elements[0].faces),keys(native.elements[0].faces),'face names');
  const nativeAnimator=Object.values(native.animations[0].animators).find(x=>Array.isArray(x.keyframes));
  const ourAnimator=Object.values(ours.animations[0].animators)[0];
  if(nativeAnimator) {
    assert.deepEqual(keys(ourAnimator),keys(nativeAnimator),'animator keys');
    if(nativeAnimator.keyframes.length)assert.deepEqual(keys(ourAnimator.keyframes[0]),keys(nativeAnimator.keyframes[0]),'keyframe keys');
  }
});
