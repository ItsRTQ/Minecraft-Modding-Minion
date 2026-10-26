import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {createModel} from '../src/model.mjs';
import {renderModel,encodePng} from '../src/render.mjs';
import {decodePngRGBA} from '../src/texture-render.mjs';
import {makeStore} from '../src/storage.mjs';
import {runTool} from '../src/tools.mjs';

const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
function atlas(size=16){
  const pixels=Buffer.alloc(size*size*4);
  for(let y=0;y<size;y++)for(let x=0;x<size;x++){
    const off=(y*size+x)*4;
    const red=x>=12&&y>=4&&y<8,green=x>=4&&x<8&&y>=4&&y<8;
    pixels[off]=red?255:0;pixels[off+1]=green?255:0;pixels[off+2]=!red&&!green?255:0;pixels[off+3]=255;
  }
  return encodePng(pixels,size,size);
}
function cubeModel(){
  const m=createModel('Texture Test',16,16),uuid='cube';
  m.elements=[{uuid,type:'cube',from:[0,0,0],to:[4,4,4],origin:[2,2,2],rotation:[0,0,0],box_uv:true,uv_offset:[0,0],faces:{}}];
  m.outliner=[uuid];
  m.textures=[{uuid:'t0',source:'data:image/png;base64,'+atlas().toString('base64')}];
  return m;
}
function at(result,x,y){const d=decodePngRGBA(result.png);const i=4*(y*d.width+x);return [...d.pixels.subarray(i,i+4)];}

test('PNG decoder round-trip preserves expected colors, not just dimensions',()=>{
  const d=decodePngRGBA(atlas());
  assert.equal(d.width,16);
  assert.deepEqual([...d.pixels.subarray((5*16+13)*4,(5*16+13)*4+4)],[255,0,0,255]);
  assert.deepEqual([...d.pixels.subarray((5*16+5)*4,(5*16+5)*4+4)],[0,255,0,255]);
});
test('renderer samples box UV atlas: south/front red, north/back green, toggle textures',()=>{
  const m=cubeModel();
  const front=renderModel(m,{views:['front'],size:96}),back=renderModel(m,{views:['back'],size:96});
  const a=at(front,48,48),b=at(back,48,48);
  assert.ok(a[0]>a[1]*2 && a[0]>a[2]*2,`front color ${a}`);
  assert.ok(b[1]>b[0]*2 && b[1]>b[2]*2,`back color ${b}`);
  assert.equal(front.texture_applied,true);
  const flat=renderModel(m,{views:['front'],size:96,textures:false});
  assert.notEqual(hash(flat.png),hash(front.png));assert.equal(flat.texture_applied,false);
});
test('per-face UV rect and 90-degree rotation produce different textured pixels',()=>{
  const m=cubeModel(),cube=m.elements[0];
  cube.box_uv=false; cube.faces={south:{uv:[12,4,16,8],texture:'t0'}};
  const baseline=renderModel(m,{views:['front'],size:96});
  // Asymmetric image is required to detect rotation: diagonal red/blue pattern.
  const rgba=Buffer.alloc(16*16*4);
  for(let i=0;i<rgba.length;i+=4){rgba[i+2]=220;rgba[i+3]=255;}
  for(let y=4;y<8;y++)for(let x=12;x<16;x++)if(x-12<y-4){const p=(y*16+x)*4;rgba[p]=255;rgba[p+2]=0;}
  m.textures[0].source='data:image/png;base64,'+encodePng(rgba,16,16).toString('base64');
  const unrotated=renderModel(m,{views:['front'],size:96});
  cube.faces.south.rotation=90;
  const rotated=renderModel(m,{views:['front'],size:96});
  assert.notEqual(hash(unrotated.png),hash(rotated.png));
  assert.equal(baseline.triangles,2); // disabled other faces have no triangles
});
test('reject malformed embedded textures and invalid animation inputs without loading external files',()=>{
  const m=cubeModel();
  m.textures[0].source='https://example.com/external.png';
  assert.throws(()=>renderModel(m),/embedded PNG texture/);
  m.textures[0].source='data:image/png;base64,'+atlas().toString('base64');
  assert.throws(()=>renderModel(m,{animation:'animation.unknown',time:1}),/geckolib_model/);
  assert.throws(()=>renderModel(m,{time:1}),/time requires an animation/);
  assert.throws(()=>renderModel(m,{textures:'true'}),/must be boolean/);
});
test('MCP render samples a real stored GeckoLib bone clip at different times, keeps read-only default',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-05-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const store=await makeStore(root);
  let res=await runTool(store,true,'bbmodel_geckolib_create',{file:'mob.bbmodel',name:'Preview',identifier:'preview',modid:'example',texture_width:16,texture_height:16});
  res=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:res.revision,operations:[{op:'add_group',name:'leg',origin:[0,0,0]}]});
  const bone=res.changes[0].uuid;
  res=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:res.revision,operations:[{op:'add_cube',name:'Leg',group_uuid:bone,from:[4,0,0],to:[6,6,2],uv_offset:[0,0]}]});
  await fs.writeFile(path.join(root,'color.png'),atlas());
  res=await runTool(store,true,'bbmodel_geckolib_set_texture',{file:'mob.bbmodel',png_file:'color.png',expected_revision:res.revision});
  res=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:res.revision,name:'animation.mob.walk',length:1,loop:'once',channels:[{bone:'leg',channel:'rotation',keyframes:[{time:0,value:[0,0,0]},{time:1,value:[0,0,90]}]}]});
  const one=await runTool(store,false,'bbmodel_render',{file:'mob.bbmodel',size:96,views:['front'],animation:'animation.mob.walk',time:0});
  const two=await runTool(store,false,'bbmodel_render',{file:'mob.bbmodel',size:96,views:['front'],animation:'animation.mob.walk',time:1});
  assert.equal(two.sampled_time,1);assert.equal(one.texture_applied,true);
  assert.notEqual(hash(Buffer.from(one.__mcpImage,'base64')),hash(Buffer.from(two.__mcpImage,'base64')));
  assert.equal(one.revision,res.revision);
  const output=await runTool(store,true,'bbmodel_render',{file:'mob.bbmodel',size:96,views:['front'],animation:'animation.mob.walk',time:.5,output_file:'walk-half.png'});
  assert.equal(output.animation,'animation.mob.walk');assert.equal(output.sampled_time,.5);
  assert.equal((await fs.readFile(path.join(root,'walk-half.png'))).readUInt32BE(16),96);
  await assert.rejects(runTool(store,false,'bbmodel_render',{file:'mob.bbmodel',output_file:'blocked.png',animation:'animation.mob.walk',time:0}),/Write access disabled/);
  await assert.rejects(runTool(store,false,'bbmodel_render',{file:'mob.bbmodel',animation:'animation.unknown'}),/Animation not found/);
});

test('PNG filter types 1-4 decode correctly, including rows with nonzero previous scanline',async()=>{
  const {deflateSync,inflateSync}=await import('node:zlib');
  const pix=Buffer.alloc(4*3*4);
  for(let i=0;i<pix.length;i++)pix[i]=(i*37+11)&255;
  const source=encodePng(pix,4,3);
  const dataLength=source.readUInt32BE(33),raw=inflateSync(source.subarray(41,41+dataLength));
  const crcTable=Array.from({length:256},(_,i)=>{let c=i;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;return c>>>0;});
  const chunk=(type,body)=>{const name=Buffer.from(type),raw=Buffer.concat([name,body]),out=Buffer.alloc(raw.length+8);out.writeUInt32BE(body.length,0);raw.copy(out,4);let c=0xffffffff;for(const b of raw)c=crcTable[(c^b)&255]^(c>>>8);out.writeUInt32BE((c^0xffffffff)>>>0,raw.length+4);return out;};
  const paeth=(a,b,c)=>{const p=a+b-c;return Math.abs(p-a)<=Math.abs(p-b)&&Math.abs(p-a)<=Math.abs(p-c)?a:Math.abs(p-b)<=Math.abs(p-c)?b:c;};
  for(const filter of [1,2,3,4]){
    const changed=Buffer.from(raw),stride=16;
    for(let y=0;y<3;y++){
      const off=y*(stride+1),row=raw.subarray(off+1,off+1+stride),prev=y?raw.subarray(off-stride,off):Buffer.alloc(stride);
      changed[off]=filter;
      for(let i=0;i<stride;i++){
        const a=i>=4?row[i-4]:0,b=prev[i],c=i>=4?prev[i-4]:0;
        changed[off+i+1]=(row[i]-[0,a,b,Math.floor((a+b)/2),paeth(a,b,c)][filter])&255;
      }
    }
    const png=Buffer.concat([source.subarray(0,33),chunk('IDAT',deflateSync(changed)),chunk('IEND',Buffer.alloc(0))]);
    assert.deepEqual(decodePngRGBA(png).pixels,pix,`PNG filter ${filter}`);
  }
});

test('parent bone rotation propagates to child cube, keeping texture image unchanged',()=>{
  const model=cubeModel();model.meta.model_format='geckolib_model';
  model.elements[0].to=[4,7,3];model.elements[0].origin=[2,3.5,1.5];
  model.groups=[{uuid:'parent',name:'parent',origin:[0,0,0],rotation:[0,0,0]},{uuid:'child',name:'child',origin:[0,0,0],rotation:[0,0,0]}];
  model.outliner=[{uuid:'parent',children:[{uuid:'child',children:['cube']}]}];
  model.animations=[{name:'animation.test.walk',length:1,loop:'once',animators:{parent:{keyframes:[{time:0,channel:'rotation',data_points:[{x:0,y:0,z:0}]},{time:1,channel:'rotation',data_points:[{x:0,y:0,z:90}]}]}}}];
  const first=renderModel(model,{views:['front'],size:96,animation:'animation.test.walk',time:0});
  const last=renderModel(model,{views:['front'],size:96,animation:'animation.test.walk',time:1});
  assert.notEqual(hash(first.png),hash(last.png));
  assert.equal(first.texture_applied,true);assert.equal(last.sampled_time,1);
});
