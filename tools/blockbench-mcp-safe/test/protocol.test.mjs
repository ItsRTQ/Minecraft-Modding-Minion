import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import readline from 'node:readline';

const entry=path.resolve('src/server.mjs');

test('Real MCP stdio process: initialize, tools/list, create, read and revision error',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-stdio-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const child=spawn(process.execPath,[entry,'--root',root,'--allow-write'],{stdio:['pipe','pipe','pipe']});
  t.after(()=>{child.kill();});
  const rl=readline.createInterface({input:child.stdout});
  let counter=0;
  const messages=[];
  rl.on('line',line=>messages.push(JSON.parse(line)));
  async function request(method,params) {
    const id=++counter;
    child.stdin.write(`${JSON.stringify({jsonrpc:'2.0',id,method,params})}\n`);
    const start=Date.now();
    while(Date.now()-start<2000) {
      const idx=messages.findIndex(m=>m.id===id);
      if (idx>=0) return messages.splice(idx,1)[0];
      await new Promise(r=>setTimeout(r,5));
    }
    throw new Error(`Timed out waiting for response: ${method}`);
  }
  const init=await request('initialize',{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'integration-test',version:'1.0'}});
  assert.equal(init.result.serverInfo.name,'blockbench-mcp-safe');
  child.stdin.write(`${JSON.stringify({jsonrpc:'2.0',method:'notifications/initialized'})}\n`);
  const list=await request('tools/list');
  assert.ok(list.result.tools.some(x=>x.name==='bbmodel_edit'));
  const mk=await request('tools/call',{name:'bbmodel_create',arguments:{file:'test.bbmodel'}});
  assert.equal(mk.result.isError,false);
  const info=await request('tools/call',{name:'bbmodel_info',arguments:{file:'test.bbmodel'}});
  assert.equal(info.result.isError,false);
  const rev=JSON.parse(info.result.content[0].text).revision;
  const edit=await request('tools/call',{name:'bbmodel_edit',arguments:{file:'test.bbmodel',expected_revision:rev,operations:[{op:'add_cube',name:'body',from:[0,0,0],to:[16,16,16]}]}});
  assert.equal(edit.result.isError,false);
  const stale=await request('tools/call',{name:'bbmodel_edit',arguments:{file:'test.bbmodel',expected_revision:rev,operations:[{op:'add_cube',name:'bad',from:[0,0,0],to:[1,1,1]}]}});
  assert.equal(stale.result.isError,true);
  assert.match(stale.result.content[0].text,/Revision conflict/);
  child.stdin.end();
});
