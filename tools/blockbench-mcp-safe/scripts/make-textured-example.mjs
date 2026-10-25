// Generate a tiny, deterministic non-production checkerboard PNG and textured .bbmodel example.
// Requires zero external packages and does not overwrite any existing example.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {deflateSync} from 'node:zlib';
import {makeStore} from '../src/storage.mjs';
import {runTool} from '../src/tools.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../examples');
const store=await makeStore(root);
function crc32(bytes){let c=0xffffffff;for(const b of bytes){c^=b;for(let i=0;i<8;i++)c=c&1?(c>>>1)^0xedb88320:c>>>1;}return (c^0xffffffff)>>>0;}
function chunk(type,data){const b=Buffer.from(type),n=Buffer.alloc(4),c=Buffer.alloc(4);n.writeUInt32BE(data.length);c.writeUInt32BE(crc32(Buffer.concat([b,data])));return Buffer.concat([n,b,data,c]);}
const w=64,h=64,scanlines=Buffer.alloc((w*4+1)*h);
for(let y=0;y<h;y++)for(let x=0;x<w;x++){
  const v=((x>>3)^(y>>3))&1, i=y*(w*4+1)+1+x*4;
  scanlines[i]=v?40:170;scanlines[i+1]=v?190:40;scanlines[i+2]=v?215:190;scanlines[i+3]=255;
}
const ihdr=Buffer.alloc(13);ihdr.writeUInt32BE(w);ihdr.writeUInt32BE(h,4);ihdr[8]=8;ihdr[9]=6;
const png=Buffer.concat([Buffer.from('89504e470d0a1a0a','hex'),chunk('IHDR',ihdr),chunk('IDAT',deflateSync(scanlines)),chunk('IEND',Buffer.alloc(0))]);
await fs.writeFile(path.join(root,'checker_64.png'),png,{flag:'wx'});
const copied=await runTool(store,true,'bbmodel_duplicate',{file:'gecko_test_mob.bbmodel',new_file:'gecko_test_mob_textured.bbmodel'});
await runTool(store,true,'bbmodel_geckolib_set_texture',{file:'gecko_test_mob_textured.bbmodel',expected_revision:copied.revision,png_file:'checker_64.png'});
await runTool(store,true,'bbmodel_geckolib_export_geometry',{file:'gecko_test_mob_textured.bbmodel',output_file:'gecko_test_mob_textured.geo.json'});
await runTool(store,true,'bbmodel_geckolib_export_animations',{file:'gecko_test_mob_textured.bbmodel',output_file:'gecko_test_mob_textured.animation.json'});
process.stdout.write('Generated textured example and PNG\n');
