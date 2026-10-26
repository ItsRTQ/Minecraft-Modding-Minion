// Read-only bridge protocol. Optional Blockbench desktop plugin writes snapshots to --root/.bbms-live.
// NO sockets, listeners, dynamic commands, subprocesses, or file paths from MCP arguments.
import fs from 'node:fs/promises';
import path from 'node:path';
import {constants} from 'node:fs';
const MAX=768*1024;
async function snapshot(store,filename){
  const directory=path.join(store.root,'.bbms-live');
  const dir=await fs.lstat(directory);
  if(!dir.isDirectory()||dir.isSymbolicLink()||(await fs.realpath(directory))!==directory)throw Error('Invalid live bridge directory');
  const file=path.join(directory,filename);
  const initial=await fs.lstat(file);
  if(!initial.isFile()||initial.nlink!==1||initial.size>MAX)throw Error('Unsafe live snapshot file');
  const fh=await fs.open(file,constants.O_RDONLY|(constants.O_NOFOLLOW||0));
  try{
    const st=await fh.stat();if(!st.isFile()||st.nlink!==1||st.dev!==initial.dev||st.ino!==initial.ino||st.size>MAX)throw Error('Live snapshot replaced or too large');
    const contents=await fh.readFile();if(contents.length>MAX)throw Error('Snapshot too large');return contents;
  }finally{await fh.close();}
}
function liveAge(info){
  if(typeof info.timestamp!=='number'||Math.abs(Date.now()-info.timestamp)>10000)throw Error('Blockbench bridge is not active (snapshot older than 10 s)');
}
export async function readLive(store,action){
  let state;
  try{state=JSON.parse((await snapshot(store,'status.json')).toString('utf8'));}
  catch(e){throw Error('Live bridge unavailable: '+e.message+'; load plugin blockbench_mcp_safe_bridge.js and connect the same --root');}
  liveAge(state);
  if(action==='app_status')return {connected:true,...state};
  if(action==='app_read_scene'){
    const scene=JSON.parse((await snapshot(store,'scene.json')).toString('utf8'));
    liveAge(scene);
    return {connected:true,scene};
  }
  if(action==='app_capture_screenshot'){
    if(typeof state.screenshot_at!=='number'||Math.abs(Date.now()-state.screenshot_at)>10000)throw Error('Blockbench viewport screenshot is unavailable or stale');
    const raw=await snapshot(store,'preview.png');
    if(!raw.subarray(0,8).equals(Buffer.from('89504e470d0a1a0a','hex')))throw Error('No valid Blockbench viewport PNG snapshot');
    return {connected:true,png:raw.toString('base64'),timestamp:state.timestamp};
  }
  throw Error('Unknown read-only live action');
}
