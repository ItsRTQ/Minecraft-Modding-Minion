import {randomUUID} from 'node:crypto';

const MAX_NODES = 60000;
const MAX_CUBES = 1000;
const MAX_MESH_VERTICES = 256;
const MAX_MESH_FACES = 256;
const MAX_GROUPS = 300;
const MAX_OPS = 64;
const SIDES = ['north','south','east','west','up','down'];

function object(x) { return x !== null && typeof x === 'object' && !Array.isArray(x); }
function fail(message) { throw new Error(message); }
function text(x, what, max = 80) {
  if (typeof x !== 'string' || x.length < 1 || x.length > max || /[\x00-\x1F\x7F]/.test(x)) fail(`${what} must be a nonempty, short string without control characters`);
  return x;
}
function coords(x, what, max = 2048) {
  if (!Array.isArray(x) || x.length !== 3 || !x.every(v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= max)) fail(`${what} must be 3 finite coordinates within ±${max}`);
  return [...x];
}
function number(x, what, min, max) {
  if (typeof x !== 'number' || !Number.isFinite(x) || x < min || x > max) fail(`${what} out of range ${min}..${max}`);
  return x;
}
function cleanJson(value) {
  const stack = [{v:value,depth:0}];
  let nodes = 0;
  while (stack.length) {
    const {v,depth} = stack.pop();
    if (++nodes > MAX_NODES || depth > 40) fail('JSON too complex');
    if (object(v)) {
      for (const [key, item] of Object.entries(v)) {
        if (key === '__proto__' || key === 'constructor' || key === 'prototype') fail('Unsafe JSON key');
        stack.push({v:item, depth:depth+1});
      }
    } else if (Array.isArray(v)) {
      for (const item of v) stack.push({v:item,depth:depth+1});
    }
  }
}
export function parseModel(raw) {
  let m;
  try { m = JSON.parse(raw); } catch { fail('Invalid .bbmodel JSON'); }
  cleanJson(m);
  if (!object(m) || !object(m.meta) || !Array.isArray(m.elements) || !Array.isArray(m.outliner)) fail('Not a supported .bbmodel structure');
  return m;
}
export function createModel(name, textureWidth = 16, textureHeight = 16) {
  text(name,'name');
  for (const [v,k] of [[textureWidth,'texture_width'],[textureHeight,'texture_height']]) {
    if (!Number.isInteger(v) || v < 1 || v > 2048) fail(`${k} must be an integer 1..2048`);
  }
  return {meta:{format_version:'5.0',model_format:'free',box_uv:true},
    name, resolution:{width:textureWidth,height:textureHeight},
    elements:[], groups:[], outliner:[], textures:[]};
}
function assertEditable(m) {
  if (!['free','geckolib_model'].includes(m.meta.model_format) || !String(m.meta.format_version || '').startsWith('5.') || !Array.isArray(m.groups)) {
    fail('Editing limited to Blockbench 5.x Generic or GeckoLib models with groups[]');
  }
  if (m.elements.length > MAX_CUBES || m.groups.length > MAX_GROUPS) fail('Model exceeds safe element limit');
  const findings = inspect(m);
  if (findings.errors.length) fail(`Invalid model structure; first problem: ${findings.errors[0]}`);
}
function findGroupTree(outliner, uuid) {
  const stack = [...outliner];
  let iterations = 0;
  while (stack.length) {
    if (++iterations > MAX_NODES) fail('Outliner too complex');
    const e = stack.pop();
    if (object(e)) {
      if (e.uuid === uuid) return e;
      if (Array.isArray(e.children)) stack.push(...e.children);
    }
  }
  return null;
}
function removeFromTree(outliner, uuid) {
  for (let i = outliner.length - 1; i >= 0; i--) {
    const e = outliner[i];
    if (e === uuid || (object(e) && e.uuid === uuid)) { outliner.splice(i,1); return true; }
    if (object(e) && Array.isArray(e.children) && removeFromTree(e.children, uuid)) return true;
  }
  return false;
}
function groupParent(m, id) {
  if (id === undefined || id === null) return m.outliner;
  text(id,'group_uuid');
  const group = findGroupTree(m.outliner, id);
  if (!group || !Array.isArray(group.children) || !m.groups.some(g => g.uuid === id)) fail(`Group not found: ${id}`);
  return group.children;
}
function newCube(op) {
  text(op.name,'cube name');
  const from = coords(op.from,'from');
  const to = coords(op.to,'to');
  if (!from.every((v,i) => v < to[i])) fail('Each from coordinate must be smaller than to');
  const origin = op.origin === undefined ? from.map((v,i) => (v+to[i])/2) : coords(op.origin,'origin');
  const rotation = op.rotation === undefined ? [0,0,0] : coords(op.rotation,'rotation',360);
  const faces = Object.fromEntries(SIDES.map(side => [side,{uv:[0,0,16,16],texture:null}]));
  const uv_offset = uvOffset(op.uv_offset);
  const inflate = op.inflate === undefined ? 0 : number(op.inflate,'inflate',-16,16);
  if (op.mirror !== undefined && typeof op.mirror !== 'boolean') fail('mirror must be boolean');
  if(op.uv_faces!==undefined&&op.uv_offset!==undefined)fail('Use uv_faces OR uv_offset, not both');
  return {name:op.name,type:'cube',uuid:randomUUID(),from,to,origin,rotation,inflate,
    box_uv:op.uv_faces===undefined,uv_offset,mirror_uv:op.mirror??false,faces:op.uv_faces===undefined?faces:uvFaces(op.uv_faces,faces)};
}
const sides = new Set(SIDES);
function uvFaces(input, existing) {
  if (!object(input) || Object.keys(input).some(k=>!sides.has(k))) fail('uv_faces must be an object keyed by north, south, east, west, up, down');
  const faces=structuredClone(existing||Object.fromEntries(SIDES.map(k=>[k,{uv:[0,0,0,0],texture:null}])));
  for(const [side, data] of Object.entries(input)) {
    if(!object(data)||Object.keys(data).some(k=>!['uv','rotation','enabled'].includes(k)))fail('uv_faces.'+side+' valid fields: uv, rotation, enabled');
    if(data.enabled!==undefined&&typeof data.enabled!=='boolean')fail('uv_faces.enabled must be boolean');
    if(!Array.isArray(data.uv)||data.uv.length!==4||!data.uv.every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=2048))fail('uv_faces.'+side+'.uv must contain 4 finite numbers 0..2048');
    if(data.rotation!==undefined&&! [0,90,180,270].includes(data.rotation))fail('uv_faces.rotation must be 0,90,180,270');
    faces[side]={...faces[side],uv:[...data.uv],...(data.rotation?{rotation:data.rotation}:{}),texture:data.enabled===false?null:(faces[side].texture??0)};
    if(data.enabled===false)faces[side].texture=null;
  }
  return faces;
}
function makeMesh(op) {
  text(op.name,'mesh name');
  if(!object(op.vertices)||!object(op.faces))fail('Mesh requires vertices{} and faces{}');
  const verts=Object.entries(op.vertices),faces=Object.entries(op.faces);
  if(verts.length<3||verts.length>MAX_MESH_VERTICES||faces.length<1||faces.length>MAX_MESH_FACES)fail('Mesh supports 3..256 vertices and 1..256 faces');
  for(const [k,v] of verts){if(!/^[A-Za-z0-9_-]{1,24}$/.test(k)||['__proto__','prototype','constructor'].includes(k))fail('Invalid or unsafe mesh vertex id');coords(v,'vertex');}
  for(const [k,face] of faces){
    if(!/^[A-Za-z0-9_-]{1,24}$/.test(k)||['__proto__','prototype','constructor'].includes(k)||!object(face)||Object.keys(face).some(x=>!['vertices','uv'].includes(x)))fail('Invalid mesh face; fields vertices, uv');
    if(!Array.isArray(face.vertices)||![3,4].includes(face.vertices.length)||new Set(face.vertices).size!==face.vertices.length||face.vertices.some(v=>!Object.hasOwn(op.vertices,v)))fail('Mesh faces need 3 or 4 distinct known vertex ids');
    if(!object(face.uv)||Object.keys(face.uv).length!==face.vertices.length||face.vertices.some(v=>!Array.isArray(face.uv[v])||face.uv[v].length!==2||!face.uv[v].every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=2048)))fail('Mesh face UVs require [u,v] per vertex');
    const [a,b,c]=face.vertices.slice(0,3).map(id=>op.vertices[id]);const ab=b.map((x,i)=>x-a[i]),ac=c.map((x,i)=>x-a[i]);const cross=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]];if(Math.hypot(...cross)<1e-6)fail('Degenerate mesh face: '+k);
  }
  return {name:op.name,type:'mesh',uuid:randomUUID(),origin:op.origin===undefined?[0,0,0]:coords(op.origin,'origin'),rotation:op.rotation===undefined?[0,0,0]:coords(op.rotation,'rotation',360),vertices:structuredClone(op.vertices),faces:Object.fromEntries(faces.map(([k,v])=>[k,{vertices:[...v.vertices],uv:structuredClone(v.uv),texture:null}]))};
}
function uvOffset(v) {
  if (v === undefined) return [0,0];
  if (!Array.isArray(v) || v.length !== 2 || !v.every(n => Number.isInteger(n) && n >= 0 && n <= 2048)) fail('uv_offset must be [u,v] integers 0..2048');
  return [...v];
}
function updateCube(cube, op) {
  if (op.name !== undefined) cube.name = text(op.name,'cube name');
  if (op.from !== undefined) cube.from = coords(op.from,'from');
  if (op.to !== undefined) cube.to = coords(op.to,'to');
  if (op.origin !== undefined) cube.origin = coords(op.origin,'origin');
  if (op.rotation !== undefined) cube.rotation = coords(op.rotation,'rotation',360);
  if (op.uv_offset !== undefined) {cube.uv_offset=uvOffset(op.uv_offset);cube.box_uv=true;}
  if (op.uv_faces !== undefined) {cube.faces=uvFaces(op.uv_faces,cube.faces);cube.box_uv=false;}
  if (op.inflate !== undefined) cube.inflate=number(op.inflate,'inflate',-16,16);
  if (op.mirror !== undefined) { if (typeof op.mirror !== 'boolean') fail('mirror must be boolean'); cube.mirror_uv=op.mirror; }
  if (!cube.from.every((v,i) => v < cube.to[i])) fail('Each from coordinate must be smaller than to');
  if (op.visible !== undefined) {
    if (typeof op.visible !== 'boolean') fail('visible must be boolean');
    cube.visibility = op.visible;
  }
}
export function editModel(m, ops) {
  if (!Array.isArray(ops) || ops.length < 1 || ops.length > MAX_OPS) fail(`operations must contain 1..${MAX_OPS} entries`);
  assertEditable(m);
  const output = [];
  for (const op of ops) {
    if (!object(op) || typeof op.op !== 'string') fail('Every operation requires an op');
    if(op.op==='add_mesh') {
      if(m.meta.model_format==='geckolib_model')fail('Mesh editing not available in geckolib_model: Bedrock poly_mesh is deprecated; use Generic .bbmodel');
      if(m.elements.length>=MAX_CUBES)fail('Too many elements');
      const parent=groupParent(m,op.group_uuid),mesh=makeMesh(op);
      m.elements.push(mesh);parent.push(mesh.uuid);output.push({op:op.op,uuid:mesh.uuid});
    } else if(op.op==='remove_mesh') {
      text(op.uuid,'mesh uuid');const i=m.elements.findIndex(x=>x.uuid===op.uuid&&x.type==='mesh');
      if(i<0)fail('Mesh not found');m.elements.splice(i,1);if(!removeFromTree(m.outliner,op.uuid))fail('Mesh absent from outliner');output.push({op:op.op,uuid:op.uuid});
    } else if (op.op === 'add_cube') {
      if (m.elements.length >= MAX_CUBES) fail('Too many cubes');
      if (m.meta.model_format==='geckolib_model' && !op.group_uuid) fail('GeckoLib cubes require group_uuid (a bone)');
      const parent = groupParent(m, op.group_uuid);
      const cube = newCube(op);
      if(m.textures?.[0]?.uuid)for(const f of Object.values(cube.faces))f.texture=m.textures[0].uuid;
      m.elements.push(cube); parent.push(cube.uuid);
      output.push({op:op.op, uuid:cube.uuid});
    } else if (op.op === 'update_cube') {
      text(op.uuid,'uuid');
      const cube = m.elements.find(e => e.uuid === op.uuid && (e.type === 'cube' || e.type === undefined));
      if (!cube) fail('Cube not found');
      updateCube(cube, op); output.push({op:op.op, uuid:cube.uuid});
    } else if (op.op === 'remove_cube') {
      text(op.uuid,'uuid');
      const idx = m.elements.findIndex(e => e.uuid === op.uuid && (e.type === 'cube' || e.type === undefined));
      if (idx < 0) fail('Cube not found');
      m.elements.splice(idx,1);
      if (!removeFromTree(m.outliner,op.uuid)) fail('Cube absent from outliner');
      output.push({op:op.op, uuid:op.uuid});
    } else if (op.op === 'add_group') {
      if (m.groups.length >= MAX_GROUPS) fail('Too many groups');
      text(op.name,'group name');
      if (m.meta.model_format==='geckolib_model') {
        if (!/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(op.name)) fail('GeckoLib bone name must be alphanumeric/underscore, start with a letter or underscore');
        if (m.groups.some(g => g.name===op.name)) fail('Duplicate bone name');
      }
      const parent = groupParent(m, op.parent_group_uuid);
      const uuid = randomUUID();
      m.groups.push({uuid,name:op.name,origin:op.origin === undefined ? [0,0,0] : coords(op.origin,'origin'),rotation:op.rotation === undefined ? [0,0,0] : coords(op.rotation,'rotation',360)});
      parent.push({uuid,isOpen:true,children:[]});
      output.push({op:op.op,uuid});
    } else if (op.op === 'rename_group') {
      text(op.uuid,'uuid'); text(op.name,'group name');
      const g = m.groups.find(g => g.uuid === op.uuid);
      if (!g) fail('Group not found');
      if (m.meta.model_format==='geckolib_model' && (!/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(op.name) || m.groups.some(x=>x.uuid!==g.uuid&&x.name===op.name))) fail('Invalid or duplicate GeckoLib bone name');
      g.name = op.name; output.push({op:op.op,uuid:op.uuid});
    } else if (op.op === 'set_bone_transform') {
      text(op.uuid,'uuid');
      const g=m.groups.find(x=>x.uuid===op.uuid);
      if (!g) fail('Group not found');
      if (op.origin===undefined && op.rotation===undefined) fail('set_bone_transform requires origin or rotation');
      if (op.origin!==undefined) g.origin=coords(op.origin,'origin');
      if (op.rotation!==undefined) g.rotation=coords(op.rotation,'rotation',360);
      output.push({op:op.op,uuid:op.uuid});
    } else if (op.op === 'remove_empty_group') {
      text(op.uuid,'uuid');
      const g = findGroupTree(m.outliner,op.uuid);
      if (!g || !Array.isArray(g.children) || g.children.length) fail('Group missing or nonempty');
      if ((m.animations||[]).some(a=>a.animators && Object.hasOwn(a.animators,op.uuid))) fail('Cannot remove a bone referenced by animations');
      const idx = m.groups.findIndex(x => x.uuid === op.uuid);
      if (idx < 0) fail('Group not found');
      m.groups.splice(idx,1); removeFromTree(m.outliner,op.uuid);
      output.push({op:op.op,uuid:op.uuid});
    } else fail(`Unknown operation: ${op.op}; valid operations: add_cube, update_cube, remove_cube, add_group, rename_group, set_bone_transform, remove_empty_group, add_mesh, remove_mesh`);
  }
  assertEditable(m);
  return output;
}

export function inspect(m) {
  const errors = [], warnings = [];
  const elements = new Set(), groups = new Set(), visited = new Set();
  if (m.elements.length > MAX_CUBES) errors.push('Too many elements');
  if (Array.isArray(m.groups)) {
    for (const g of m.groups) {
      if (!object(g) || typeof g.uuid !== 'string' || groups.has(g.uuid)) errors.push('Duplicate or invalid group UUID');
      else groups.add(g.uuid);
    }
  }
  for (const e of m.elements) {
    if (!object(e) || typeof e.uuid !== 'string' || elements.has(e.uuid) || groups.has(e.uuid)) errors.push('Duplicate or invalid element UUID');
    else elements.add(e.uuid);
    if (object(e) && (e.type === 'cube' || e.type === undefined)) {
      if (!Array.isArray(e.from) || !Array.isArray(e.to) || e.from.length !== 3 || e.to.length !== 3 || !e.from.every((v,i) => Number.isFinite(v) && Number.isFinite(e.to[i]) && v < e.to[i])) warnings.push(`Suspicious cube geometry: ${e.name || e.uuid}`);
    } else if(object(e)&&e.type==='mesh') {
      try {makeMesh({name:e.name,vertices:e.vertices,faces:Object.fromEntries(Object.entries(e.faces||{}).map(([k,f])=>[k,{vertices:f.vertices,uv:f.uv}]))});}
      catch(error){errors.push('INVALID_MESH: '+error.message);}
    } else errors.push('Unsupported element type: '+(e?.type??'null'));
  }
  const stack = m.outliner.map(x => ({e:x,depth:0}));
  let count=0;
  while (stack.length) {
    if (++count > MAX_NODES) { errors.push('Outliner too complex'); break; }
    const {e,depth} = stack.pop();
    if (depth > 30) { errors.push('Outliner too deeply nested'); continue; }
    if (typeof e === 'string') {
      if (!elements.has(e) || visited.has(e)) errors.push(`Missing/duplicate outliner element: ${e}`);
      visited.add(e);
    } else if (object(e) && typeof e.uuid === 'string' && Array.isArray(e.children)) {
      if (!groups.has(e.uuid) || visited.has(e.uuid)) errors.push(`Missing/duplicate outliner group: ${e.uuid}`);
      visited.add(e.uuid);
      stack.push(...e.children.map(item => ({e:item,depth:depth+1})));
    } else errors.push('Invalid outliner entry');
  }
  for (const uuid of [...elements,...groups]) if (!visited.has(uuid)) errors.push(`Unreferenced element/group: ${uuid}`);
  if (Array.isArray(m.textures) && m.textures.length > 1) {
    warnings.push('TEXTURE_PREVIEW_LIMIT: bbmodel_render supports exactly one embedded PNG texture; use textures:false for flat shading.');
  } else if (Array.isArray(m.textures) && m.textures.length === 1) {
    const source = m.textures[0]?.source;
    if (typeof source !== 'string' || !/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(source)) {
      warnings.push('TEXTURE_EXTERNAL_UNSUPPORTED: bbmodel_render reads only embedded PNG textures, not external files or URLs; embed a PNG or use textures:false.');
    }
  }
  return {valid:errors.length === 0,errors:errors.slice(0,60),warnings:warnings.slice(0,60),counts:{elements:m.elements.length,groups:groups.size,textures:Array.isArray(m.textures)?m.textures.length:0}};
}

export function overview(m, includeElements = false) {
  const result = {name:m.name ?? null,format_version:m.meta.format_version ?? null,model_format:m.meta.model_format ?? null,
    cubes:m.elements.filter(e => object(e) && (e.type === 'cube' || e.type === undefined)).length,
    elements:m.elements.length,groups:Array.isArray(m.groups)?m.groups.length:0,
    textures:Array.isArray(m.textures)?m.textures.length:0,animations:Array.isArray(m.animations)?m.animations.length:0};
  if (includeElements) {
    if (m.elements.length > 250) fail('Too many elements for scene output; use info and inspect locally');
    result.elements_detail=m.elements.map(e => ({uuid:e.uuid,name:e.name,type:e.type ?? 'cube',from:e.from,to:e.to,origin:e.origin,rotation:e.rotation}));
    result.groups_detail=Array.isArray(m.groups)?m.groups.map(g => ({uuid:g.uuid,name:g.name,origin:g.origin,rotation:g.rotation})):[];
    result.outliner=m.outliner;
  }
  return result;
}
