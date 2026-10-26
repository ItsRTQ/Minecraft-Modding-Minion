import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {parseModel,inspect} from '../src/model.mjs';

test('Packaged demo .bbmodel parses with Blockbench 5-like structure and validates',async()=>{
  const raw=await fs.readFile(new URL('../examples/demo.bbmodel',import.meta.url),'utf8');
  const model=parseModel(raw);
  assert.equal(model.meta.format_version,'5.0');
  assert.equal(model.meta.model_format,'free');
  assert.equal(model.elements.length,2);
  assert.equal(inspect(model).valid,true);
});
