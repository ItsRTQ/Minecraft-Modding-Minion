// Generate a fully self-contained GeckoLib example inside examples/.
// Requires no libraries and never overwrites existing files.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {makeStore} from '../src/storage.mjs';
import {runTool} from '../src/tools.mjs';
const exampleRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../examples');
await fs.mkdir(exampleRoot,{recursive:true});
const store=await makeStore(exampleRoot);
const name='gecko_test_mob';
const file=`${name}.bbmodel`;
const mk=await runTool(store,true,'bbmodel_geckolib_create',{file,name:'Gecko Test Mob',modid:'examplemod',identifier:name,model_type:'Entity',texture_width:64,texture_height:64});
let rev=mk.revision;
async function edit(operations) {
  const v=await runTool(store,true,'bbmodel_edit',{file,expected_revision:rev,operations});rev=v.revision;return v.changes;
}
const [root]=await edit([{op:'add_group',name:'root',origin:[0,0,0]}]);
const [body]=await edit([{op:'add_group',name:'body',origin:[0,12,0],parent_group_uuid:root.uuid}]);
const [head]=await edit([{op:'add_group',name:'head',origin:[0,22,0],parent_group_uuid:body.uuid}]);
const [leftArm]=await edit([{op:'add_group',name:'left_arm',origin:[-5,20,0],parent_group_uuid:body.uuid}]);
const [rightArm]=await edit([{op:'add_group',name:'right_arm',origin:[5,20,0],parent_group_uuid:body.uuid}]);
const [leftLeg]=await edit([{op:'add_group',name:'left_leg',origin:[-2,12,0],parent_group_uuid:root.uuid}]);
const [rightLeg]=await edit([{op:'add_group',name:'right_leg',origin:[2,12,0],parent_group_uuid:root.uuid}]);
await edit([
  {op:'add_cube',name:'torso',group_uuid:body.uuid,from:[-4,12,-2],to:[4,22,2],uv_offset:[0,0]},
  {op:'add_cube',name:'skull',group_uuid:head.uuid,from:[-4,22,-4],to:[4,30,4],uv_offset:[24,0]},
  {op:'add_cube',name:'arm_l',group_uuid:leftArm.uuid,from:[-7,10,-2],to:[-4,20,2],uv_offset:[0,16]},
  {op:'add_cube',name:'arm_r',group_uuid:rightArm.uuid,from:[4,10,-2],to:[7,20,2],uv_offset:[14,16]},
  {op:'add_cube',name:'leg_l',group_uuid:leftLeg.uuid,from:[-4,0,-2],to:[-1,12,2],uv_offset:[0,32]},
  {op:'add_cube',name:'leg_r',group_uuid:rightLeg.uuid,from:[1,0,-2],to:[4,12,2],uv_offset:[14,32]}
]);
const kf=(times,angles)=>times.map((time,i)=>({time,value:[angles[i],0,0]}));
const idle=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file,expected_revision:rev,name:'animation.gecko_test_mob.idle',length:1,loop:'loop',channels:[
  {bone:'body',channel:'rotation',keyframes:kf([0,0.5,1],[0,2,0])},
  {bone:'head',channel:'rotation',keyframes:kf([0,0.5,1],[0,-1,0])}
]});rev=idle.revision;
const walk=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file,expected_revision:rev,name:'animation.gecko_test_mob.walk',length:1,loop:'loop',channels:[
  {bone:'left_leg',channel:'rotation',keyframes:kf([0,0.25,0.5,0.75,1],[0,30,0,-30,0])},
  {bone:'right_leg',channel:'rotation',keyframes:kf([0,0.25,0.5,0.75,1],[0,-30,0,30,0])},
  {bone:'left_arm',channel:'rotation',keyframes:kf([0,0.25,0.5,0.75,1],[0,-20,0,20,0])},
  {bone:'right_arm',channel:'rotation',keyframes:kf([0,0.25,0.5,0.75,1],[0,20,0,-20,0])}
]});
const checked=await runTool(store,false,'bbmodel_geckolib_validate',{file});
if(!checked.valid) throw Error('Demo validation failed: '+checked.errors.join('; '));
await runTool(store,true,'bbmodel_geckolib_export_geometry',{file,output_file:`${name}.geo.json`});
await runTool(store,true,'bbmodel_geckolib_export_animations',{file,output_file:`${name}.animation.json`});
process.stdout.write(`Generated ${file} + geo.json + animation.json; ${checked.counts.bones} bones, ${checked.counts.animations} animations\n`);
