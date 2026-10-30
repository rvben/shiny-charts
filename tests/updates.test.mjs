import test from 'node:test';
import assert from 'node:assert/strict';
import { applyUpdate } from '../frontend/updates.js';
const spec = {kind:'scatter', columns:['x','y','id'], rows:[[1,2,'a'],[2,null,'b']], encoding:{x:'x',y:'y',key:'id'}, view:{revision:'same'}};
const stream={token:'first',sequence:0};
const message={token:'first',base:0,sequence:1,operation:'append',max_rows:2,data:{columns:spec.columns,rows:[[3,4,'c']]}};
test('append rolls off rows, preserves metadata and does not mutate prior snapshots',()=>{
  const next=applyUpdate(spec,stream,message);
  assert.deepEqual(next.spec.rows,[[2,null,'b'],[3,4,'c']]);
  assert.deepEqual(spec.rows,[[1,2,'a'],[2,null,'b']]);
  assert.deepEqual(next.spec.view,spec.view);
  assert.equal(next.stream.sequence,1);
});
test('replacement decodes its own dictionaries and allows empty recovery',()=>{
  const next=applyUpdate(spec,stream,{...message,operation:'replace',data:{columns:spec.columns,rows:[[4,5,0]],dictionaries:{id:['d']}}});
  assert.deepEqual(next.spec.rows,[[4,5,'d']]);
  assert.deepEqual(applyUpdate(next.spec,next.stream,{...message,base:1,sequence:2,operation:'replace',data:{columns:spec.columns,rows:[]}}).spec.rows,[]);
});
test('stale, duplicate, out-of-order and malformed messages fail atomically',()=>{
  for(const change of [{token:'old'},{base:1},{sequence:2},{operation:'unknown'},{max_rows:0},{data:{columns:['bad'],rows:[]}},{data:{columns:spec.columns,rows:[[3,4,'a']]}},{data:{columns:spec.columns,rows:[[3,4]]}},{data:{columns:spec.columns,rows:[[3,Infinity,'c']]}}]) assert.throws(()=>applyUpdate(spec,stream,{...message,...change}));
  assert.equal(spec.rows.length,2);assert.equal(stream.sequence,0);
});
test('bands append/replace with exact row alignment and reject malformed bounds',()=>{
  const banded={...spec,kind:'line',band:{label:'Interval',bounds:[[-1,3],[null,null]]}};
  const next=applyUpdate(banded,stream,{...message,data:{...message.data,bounds:[[2,6]]}});
  assert.deepEqual(next.spec.band.bounds,[[null,null],[2,6]]);
  for(const bounds of [[],[[8,2]],[[2,Infinity]]]) assert.throws(()=>applyUpdate(banded,stream,{...message,data:{...message.data,bounds}}));
});


test('pie and formatted hover updates reject invalid data atomically',()=>{
 const pie={...spec,kind:'pie',hover:{formats:{id:'number:0'}}};
 assert.throws(()=>applyUpdate(pie,stream,{...message,data:{columns:spec.columns,rows:[[3,-1,4]]}}),/negative/);
 assert.throws(()=>applyUpdate(pie,stream,message),/format/);
 assert.equal(stream.sequence,0);assert.equal(spec.rows.length,2);
});

test('bar proxies preserve the overlay and reject a new colliding group atomically', () => {
 const bars={...spec,kind:'bar',labels:{y:'Y'},encoding:{...spec.encoding,color:'id'},line:{label:'Forecast',rows:[['x',9]]}};
 const next=applyUpdate(bars,stream,message);
 assert.equal(next.spec.line,bars.line);
 assert.throws(()=>applyUpdate(bars,stream,{...message,data:{columns:spec.columns,rows:[[3,4,'Forecast']]}}),/line label/);
 assert.equal(stream.sequence,0);
});
