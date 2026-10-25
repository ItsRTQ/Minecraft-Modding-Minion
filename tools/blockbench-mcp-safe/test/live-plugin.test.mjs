import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {makeStore} from '../src/storage.mjs';
import {readLive} from '../src/live.mjs';
import {renderModel} from '../src/render.mjs';

test('Mocked Blockbench 5 desktop bridge action writes live read-only snapshots; can disconnect',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-live-'));
 t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const store=await makeStore(root);
 const png=renderModel({elements:[{type:'cube',from:[0,0,0],to:[2,2,2]}]},{size:64,views:['iso']}).png;
 const sandbox={
  Plugin:{register(id,definition){sandbox.plugin=definition;}},
  Action:class {constructor(id,opts){this.options=opts;}delete(){}},
  MenuBar:{menus:{tools:{addAction(){}}}},
  Blockbench:{showQuickMessage(){},showMessageBox(msg){throw Error('Unexpected Blockbench dialog: '+msg.message);}},
  Project:{name:'Demo',format:{id:'geckolib_model'}},
  Cube:{all:[{uuid:'x',name:'Block',from:[0,0,0],to:[2,2,2],origin:[1,1,1]}]},
  Group:{all:[{uuid:'b',name:'body',origin:[0,0,0],rotation:[0,0,0]}]},
  Preview:{selected:{canvas:{toDataURL:()=>`data:image/png;base64,${png.toString('base64')}`}}},
  window:{prompt:()=>root},require:createRequire(import.meta.url),Buffer,console,
  setInterval(){return 99;},clearInterval(){}
 };
 const code=await fs.readFile(path.join(path.dirname(fileURLToPath(import.meta.url)),'..','plugin','blockbench_mcp_safe_bridge.js'),'utf8');
 vm.runInNewContext(code,sandbox,{timeout:1000});
 sandbox.plugin.onload();sandbox.mcpSafeAction;// action is let lexical in vm context, accessible through variable evaluation
 vm.runInNewContext('mcpSafeAction.options.click()',sandbox,{timeout:1000});
 const status=await readLive(store,'app_status');assert.equal(status.project,'Demo');
 const scene=await readLive(store,'app_read_scene');assert.equal(scene.scene.cubes[0].name,'Block');
 const preview=await readLive(store,'app_capture_screenshot');assert.equal(Buffer.from(preview.png,'base64').readUInt32BE(16),64);
 vm.runInNewContext('mcpSafeAction.options.click()',sandbox,{timeout:1000});
 sandbox.plugin.onunload();
});
