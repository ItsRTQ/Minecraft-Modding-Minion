#!/usr/bin/env node
import {makeStore} from './storage.mjs';
import {TOOLS,runTool} from './tools.mjs';
import {pathToFileURL} from 'node:url';

const MAX_REQUEST_BYTES = 1024 * 1024;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const PROTOCOL_VERSION = '2025-06-18';

function usage() {
  process.stdout.write(`Blockbench MCP Safe (stdio only)\n\nUsage:\n  node src/server.mjs --root ABSOLUTE_DIRECTORY [--allow-write] [--enable-live]\n\nWrites DISABLED by default. No HTTP, network fetching, code execution or subprocess spawning.\nNode.js >=20. Directory must already exist. Only top-level *.bbmodel files.\n`);
}
function parseArgs(argv) {
  let root, allowWrite=false, enableLive=false;
  for (let i=0; i<argv.length; i++) {
    const arg=argv[i];
    if (arg==='--help' || arg==='-h') return {help:true};
    if (arg==='--root') {
      if (root || !argv[i+1]) throw new Error('--root must be provided once with a value');
      root=argv[++i];
    } else if (arg==='--allow-write') allowWrite=true;
    else if(arg==='--enable-live') enableLive=true;
    else throw new Error(`Unknown CLI option: ${arg}`);
  }
  if (!root) throw new Error('--root ABSOLUTE_DIRECTORY is required');
  return {root,allowWrite,enableLive};
}
function send(value) {
  let raw=JSON.stringify(value);
  if (Buffer.byteLength(raw,'utf8') > MAX_RESPONSE_BYTES) {
    raw=JSON.stringify({jsonrpc:'2.0',id:value?.id ?? null,error:{code:-32603,message:'Response exceeds 1 MiB'}});
  }
  process.stdout.write(`${raw}\n`);
}
const err = (id,code,message) => ({jsonrpc:'2.0',id,error:{code,message}});
const ok = (id,result) => ({jsonrpc:'2.0',id,result});

export async function handle(message,store,allowWrite,enableLive=false) {
  if (!message || Array.isArray(message) || typeof message!=='object' || message.jsonrpc!=='2.0' || typeof message.method!=='string') return err(message?.id ?? null,-32600,'Invalid JSON-RPC request');
  const hasId = Object.hasOwn(message,'id');
  if (!hasId) return null; // notifications (including initialized) never receive replies
  const {id,method} = message;
  if (!(typeof id==='string' || (typeof id==='number' && Number.isFinite(id)) || id===null)) return err(null,-32600,'Invalid JSON-RPC id');
  if (method==='initialize') {
    const requested=message.params?.protocolVersion;
    const supported=['2024-11-05','2025-03-26','2025-06-18'];
    return ok(id,{protocolVersion:supported.includes(requested)?requested:PROTOCOL_VERSION,
      capabilities:{tools:{listChanged:false}},instructions:'Safe GeckoLib flow: bbmodel_geckolib_create -> bbmodel_edit (add bones with origin pivots, then cubes with group_uuid and uv_offset) -> bbmodel_geckolib_set_texture (optional PNG) -> bbmodel_geckolib_upsert_animation (idle and walk) -> bbmodel_geckolib_validate {require_idle_walk:true} -> bbmodel_geckolib_export_geometry and bbmodel_geckolib_export_animations. ALWAYS use the revision returned by the latest mutation as expected_revision for the next edit; reread after conflicts. Geometry and animation exports mirror the X coordinate convention of Blockbench/Bedrock; do not mirror coordinates manually. Use animation (not name) for both bbmodel_sample_pose and bbmodel_render; use bbmodel_quality_gates for numeric QA and bbmodel_render with animation + time for pose-aware textured PNG contact sheets. Models with an embedded PNG render textured by default; set textures:false for flat shading. Live bridge app_* snapshots are opt-in and read-only with --enable-live. Generic model meshes are not exportable to GeckoLib because Bedrock poly_mesh is deprecated. Exports do not include PNG image bytes; ship the texture separately.',serverInfo:{name:'blockbench-mcp-safe',version:'0.5.1'}});
  }
  if (method==='ping') return ok(id,{});
  if (method==='tools/list') return ok(id,{tools:TOOLS.filter(t=>(allowWrite||!t.writes)&&(enableLive||!t.live)).map(({writes,live,...rest})=>rest)});
  if (method==='resources/list') return ok(id,{resources:[]});
  if (method==='prompts/list') return ok(id,{prompts:[]});
  if (method==='tools/call') {
    const name=message.params?.name;
    if (typeof name!=='string') return err(id,-32602,'Missing tool name');
    try {
      const result=await runTool(store,allowWrite,name,message.params?.arguments,enableLive);
      const image=result?.__mcpImage;
      if(image)delete result.__mcpImage;
      const content=[{type:'text',text:JSON.stringify(result)}];
      if(image)content.push({type:'image',data:image,mimeType:'image/png'});
      return ok(id,{content,isError:false});
    } catch (e) {
      // Errors reported as MCP tool errors, never stack traces or arbitrary filesystem paths.
      const text=String(e?.message || 'Tool error').slice(0,500);
      return ok(id,{content:[{type:'text',text}],isError:true});
    }
  }
  return err(id,-32601,'Method not found');
}

export async function main(argv=process.argv.slice(2)) {
  let config;
  try { config=parseArgs(argv); }
  catch (e) { process.stderr.write(`Configuration error: ${e.message}\n`);process.exitCode=2;return; }
  if (config.help) {usage();return;}
  let store;
  try { store=await makeStore(config.root); }
  catch (e) {process.stderr.write(`Workspace error: ${e.message}\n`);process.exitCode=2;return;}
  process.stderr.write(`[blockbench-mcp-safe] stdio ready; writes ${config.allowWrite?'ENABLED':'DISABLED'}, live ${config.enableLive?'ENABLED':'DISABLED'}\n`);
  process.stdin.setEncoding('utf8');
  let buffered='';
  // Sequential processing preserves message order and avoids races within a single client.
  for await (const chunk of process.stdin) {
    buffered+=chunk;
    if (Buffer.byteLength(buffered,'utf8')>MAX_REQUEST_BYTES && !buffered.includes('\n')) {
      process.stderr.write('Oversized request; terminating connection\n');return;
    }
    let ix;
    while ((ix=buffered.indexOf('\n'))>=0) {
      const line=buffered.slice(0,ix);buffered=buffered.slice(ix+1);
      if (!line.trim()) continue;
      if (Buffer.byteLength(line,'utf8')>MAX_REQUEST_BYTES) {send(err(null,-32700,'Request too large'));continue;}
      let msg;
      try { msg=JSON.parse(line); }
      catch {send(err(null,-32700,'Malformed JSON'));continue;}
      try { const response=await handle(msg,store,config.allowWrite,config.enableLive); if (response!==null) send(response); }
      catch {send(err(msg?.id??null,-32603,'Internal error'));}
    }
    if (Buffer.byteLength(buffered,'utf8')>MAX_REQUEST_BYTES) {
      process.stderr.write('Oversized request; terminating connection\n');return;
    }
  }
}

if (process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  main().catch(()=>{process.stderr.write('Fatal server error\n');process.exitCode=1;});
}
