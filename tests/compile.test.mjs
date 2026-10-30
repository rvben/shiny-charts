import test from 'node:test';
import assert from 'node:assert/strict';
import { compile, colorFor, displayValue, pointEvent, unpack, palette, formatter, groupsOf, displayedRecords } from '../frontend/compile.js';

const theme = { font: 'Manrope', fg: '#243044', muted: '#596779', grid: '#dce4ed', border: '#dce4ed', surface: '#fff' };
const spec = {
  kind: 'line', columns: ['x', 'y', 'group', 'key'], rows: [[2, 3, 'A', 'a'], [1, null, 'A', 'b'], [1, 4, 'B', 'c']],
  encoding: { x: 'x', y: 'y', color: 'group', key: 'key' },
  labels: { x: 'Time', y: 'Cost' }, formats: { x: 'number', y: 'currency:USD:3' },
  x_type: 'value', rules: [{ y: 4, label: 'Budget' }], view: { zoom: true }, selection: {}, tooltip: [],
};
test('stable colors across reordered/filtered series', () => {
  const first = compile(spec, theme, 700);
  const filtered = compile({ ...spec, rows: [spec.rows[2]] }, theme, 300);
  assert.equal(first.series[1].itemStyle.color, filtered.series[0].itemStyle.color);
  assert.equal(first.series[1].itemStyle.color, colorFor('B'));
});
test('sort lines by numeric x and preserve original row identity and gaps', () => {
  const series = compile(spec, theme, 700).series[0];
  assert.deepEqual(series.data.map(p => p.row), [1, 0]);
  assert.equal(series.data[0].value[1], null);
  assert.equal(series.connectNulls, false);
  assert.deepEqual(pointEvent(spec, 0, 0).keys, ['a']);
});
test('one budget rule, zero baseline for bars, responsive ticks', () => {
  const result = compile(spec, theme, 320);
  assert.equal(result.series.filter(s => s.markLine).length, 1);
  assert.equal(result.xAxis.splitNumber, 3);
  const bar = compile({ ...spec, kind: 'bar', x_type: 'category', stacked: true }, theme, 700);
  assert.equal(bar.yAxis.scale, false);
  assert.equal(bar.series[0].stack, 'total');
});
test('confidence band crosses zero and does not bridge missing data', () => {
  const data = { ...spec, rows: [[1, 0, 'A', 'a'], [2, 0.5, 'A', 'b'], [3, null, 'A', 'c'], [4, 1, 'A', 'd']], band: { bounds: [[-1, 1], [-0.5, 1.5], [null, null], [0, 2]] } };
  const band = compile(data, theme, 700).series[0];
  assert.equal(band.type, 'custom');
  assert.equal(band.data.length, 1);
  assert.deepEqual(band.data[0], [1, -1, 1, 2, -0.5, 1.5]);
});
test('histogram event is a bin range rather than a fabricated row identifier', () => {
  const data = { ...spec, kind: 'histogram', rows: [[0.5, 8]], columns: ['x', 'y'], encoding: { x: 'x', y: 'y' }, intervals: [[0, 1]] };
  assert.deepEqual(pointEvent(data, 0, 0), { kind: 'bin', range: { min: 0, max: 1, upper_inclusive: true }, count: 8 });
});
test('tooltip escapes untrusted labels and data', () => {
  const data = { ...spec, rows: [[1, 2, '<img src=x onerror=alert(1)>', 'a']] };
  const result = compile(data, theme, 700);
  const text = result.tooltip.formatter({ data: { row: 0 }, seriesName: '<img>' });
  assert.ok(text.includes('&lt;img&gt;'));
  assert.ok(!text.includes('<img'));
});
test('decode categorical dictionaries before producing events and legends', () => {
  const packed = { ...spec, rows: [[1, 2, 0, 'a']], dictionaries: { group: ['Workload'] } };
  const decoded = unpack(packed);
  assert.equal(pointEvent(decoded, 0, 0).group, 'Workload');
  assert.equal(compile(decoded, theme, 700).series[0].name, 'Workload');
  assert.equal(packed.rows[0][2], 0);
});
test('horizontal bars retain semantic events, full tooltip names, and value-axis rules',()=>{
  const bar={...spec,kind:'bar',orientation:'horizontal',x_type:'category',rows:[['Enterprise onboarding and access provisioning',1200,'A','a']],rules:[{y:1000,label:'Target'}]};
  const result=compile(bar,theme,320);
  assert.equal(result.xAxis.type,'value');assert.equal(result.yAxis.type,'category');
  assert.deepEqual(result.series[0].data[0].value,[1200,0]);
  assert.equal(result.series[0].markLine.data[0].xAxis,1000);
  assert.equal(pointEvent(bar,0,0).x,bar.rows[0][0]);
  assert.ok(result.tooltip.formatter({data:{row:0},seriesName:'A'}).includes(bar.rows[0][0]));
  assert.equal(result.yAxis.axisLabel.overflow,'truncate');
});
test('numeric axis gutter accommodates large formatted values and tooltip missing fields',()=>{
  const data={...spec,rows:[[1,100000000,'A','a']],tooltip:['missing'],columns:[...spec.columns,'missing']};
  const result=compile(data,theme,700);
  assert.ok(result.grid.left>64);
  assert.ok(result.tooltip.formatter({data:{row:0},seriesName:'A'}).includes('Missing'));
});
test('named palette slots resolve collisions and remain stable under filtering and themes',()=>{
  const data={...spec,palette:{Email:1,Chat:2},rows:[[1,2,'Email','a'],[1,3,'Chat','b']]};
  const first=compile(data,theme,700);
  assert.notEqual(first.series[0].itemStyle.color,first.series[1].itemStyle.color);
  const custom=['#111111','#222222','#333333','#444444','#555555','#666666'];
  assert.equal(compile({...data,rows:[data.rows[1]]},{...theme,palette:custom},320).series[0].itemStyle.color,'#222222');
  assert.ok(custom.includes(colorFor('constructor',custom,{})));
});

test('display preserves encoded units, UTC timestamp precision, and literal extras',()=>{
  const data={...spec,formats:{x:'number:1',y:'percent:0'}};
  assert.equal(displayValue(data,'y',.42),'42%');
  assert.equal(displayValue(spec,'y',12.5),'$12.500');
  assert.equal(displayValue(data,'x',1234.56),'1,234.6');
  assert.equal(displayValue(data,'key','<img>'),'<img>');
  assert.equal(displayValue(data,'y',null),'Missing');
  const time={...data,x_type:'time'};
  assert.equal(displayValue(time,'x','2026-10-03T01:02:03Z'),'Oct 3, 2026, 01:02:03 UTC');
  assert.ok(compile(time,theme,700).tooltip.formatter({data:{row:0},seriesName:'A'}));
});

test('compact vertical category ticks can skip labels while retaining all records',()=>{
 const bar={...spec,kind:'bar',x_type:'category',rows:Array.from({length:8},(_,i)=>[String(2019+i),.4,'A',String(i)])};
 const compact=compile(bar,theme,296);
 assert.equal(compact.xAxis.axisLabel.interval,'auto');
 assert.equal(compact.xAxis.axisLabel.hideOverlap,true);
 assert.equal(compact.series[0].data.length,8);
 assert.equal(compile(bar,theme,700).xAxis.axisLabel.interval,0);
});


test('normalized share stacks never round past 100 percent and respect explicit domains',()=>{
 const shares={...spec,kind:'bar',stacked:true,x_type:'category',rules:[],formats:{x:'number',y:'percent:0'},rows:[['a',.4,'A','a'],['a',.6,'B','b']]};
 for(const width of [390,440,480,700]){
  const result=compile(shares,theme,width);
  assert.equal(result.yAxis.max,1);assert.equal(result.yAxis.min,0);
 }
 assert.equal(compile({...shares,domain:{y:[0,2]}},theme,440).yAxis.max,2);
 assert.equal(compile({...shares,rows:[['a',.8,'A','a'],['a',.6,'B','b']]},theme,440).yAxis.max,undefined);
 assert.equal(compile({...shares,rules:[{y:1.2,label:'Limit'}]},theme,440).yAxis.max,undefined);
 assert.equal(compile({...shares,orientation:'horizontal'},theme,440).xAxis.max,1);
});

test('bar totals use visible groups with separate positive and negative stacks',()=>{
 const bar={...spec,kind:'bar',stacked:true,x_type:'category',rules:[],rows:[['a',2,'A','a'],['a',3,'B','b'],['a',-1,'C','c']],value_labels:{show:true,totals:true},legend:{order:['C','B','A']}};
 const option=compile(bar,theme,700);
 assert.deepEqual(option.series.filter(s=>s.id.startsWith('series:')).map(s=>s.name),['C','B','A']);
 assert.deepEqual(option.series.filter(s=>s.id.startsWith('total:')).flatMap(s=>s.data).map(p=>p.total),[5,-1]);
 const filtered=compile(bar,theme,700,new Set(['B']));
 assert.deepEqual(filtered.series.filter(s=>s.id.startsWith('total:')).flatMap(s=>s.data).map(p=>p.total),[2,-1]);
 assert.equal(option.series[0].label.formatter({data:{row:2}}),'-$1.000');
 assert.equal(option.series.at(-1).silent,true);
});

test('titles, atomic dense date labels, numeric precision and physical horizontal domains',()=>{
 const bar={...spec,kind:'bar',x_type:'category',rules:[],labels:{...spec.labels,title:'Title'},formats:{x:'number',y:'number:0'},rows:Array.from({length:30},(_,i)=>[`2026-01-${String(i+1).padStart(2,'0')}`,0,'A',String(i)])};
 const result=compile(bar,theme,900);
 assert.equal(result.title.text,'Title');assert.ok(result.grid.top>22);
 assert.equal(result.xAxis.axisLabel.overflow,'truncate');assert.equal(result.xAxis.axisLabel.interval,'auto');
 assert.equal(result.yAxis.minInterval,1);
 const horizontal=compile({...bar,orientation:'horizontal',domain:{y:[-2,10]},ticks:{x_rotation:30}},theme,440);
 assert.equal(horizontal.xAxis.min,-2);assert.equal(horizontal.xAxis.max,10);assert.equal(horizontal.yAxis.axisLabel.rotate,30);
 assert.equal(colorFor('A'),colorFor('A',palette));
 assert.equal(colorFor('Extra',palette,{Extra:12}),palette[11]);
});


test('value labels contrast with named, HSL, and hex host colours',()=>{
 const bar={...spec,kind:'bar',stacked:true,x_type:'category',rules:[],value_labels:{show:true},palette:{A:1},rows:[['a',1,'A','a']]};
 for(const [color,expected] of [['white','#000000'],['hsl(0, 0%, 100%)','#000000'],['#000','#ffffff']]) {
  assert.equal(compile(bar,{...theme,palette:[color]},700).series[0].label.color,expected);
 }
});


test('fixed percent domains use intervals that include both endpoints', () => {
 const shares={...spec,kind:'bar',stacked:true,x_type:'category',rules:[],formats:{x:'number',y:'percent:0'},domain:{y:[0,1]}};
 for(const width of [260,440,480,900]){
  const result=compile(shares,theme,width);
  assert.equal(result.yAxis.interval,width<480?.25:.2);
  assert.equal(result.yAxis.axisLabel.showMaxLabel,true);
 }
 assert.equal(compile({...shares,domain:{y:[.1,.9]}},theme,440).yAxis.interval,.2);
 assert.equal(compile({...shares,orientation:'horizontal'},theme,440).xAxis.interval,.25);
});

test('stack labels hide zero and segments too small for the formatted text', () => {
 const bar={...spec,kind:'bar',stacked:true,x_type:'category',value_labels:{show:true,totals:true},rows:[['a',0,'A','a']]};
 const series=compile(bar,theme,260).series[0];
 assert.equal(series.label.formatter({data:{row:0}}),'');
 const params={labelRect:{width:40,height:11},rect:{width:32,height:100}};
 assert.equal(series.labelLayout(params).width,0);
 assert.equal(series.labelLayout({...params,rect:{width:100,height:-15}}).width,0);
 assert.equal(series.labelLayout({...params,rect:{width:100,height:-30}}).width,undefined);
});

test('few long category names wrap whole words, and explicit rotation retains all categories', () => {
 const bar={...spec,kind:'bar',x_type:'category',rules:[],rows:['Made prediction','Declined prediction','Timed out','Failed'].map((x,i)=>[x,i+1,'A',String(i)])};
 const option=compile(bar,theme,460);
 assert.equal(option.xAxis.axisLabel.interval,0);
 assert.equal(option.xAxis.axisLabel.formatter('Made prediction'),'Made\nprediction');
 assert.equal(option.xAxis.axisLabel.hideOverlap,false);
 assert.equal(compile({...bar,ticks:{x_rotation:45}},theme,460).xAxis.axisLabel.interval,0);
 assert.equal(compile({...bar,ticks:{x_labels:'all'}},theme,260).xAxis.axisLabel.interval,0);
 assert.ok(Number.isFinite(compile({...bar,rows:[],ticks:{x_labels:'wrap'}},theme,260).grid.bottom));
});


test('rotated labels respect actual height and reserve a minimum plot',()=>{
 const bar={...spec,kind:'bar',x_type:'category',rules:[],ticks:{x_rotation:45},rows:[['Made prediction',300000,'A','a'],['Declined prediction',12000,'A','b']]};
 const result=compile(bar,theme,460,new Set(),180);
 assert.ok(180-result.grid.top-result.grid.bottom>=89);
 assert.ok(result.xAxis.axisLabel.width<100);
 assert.ok(result.xAxis.nameGap<70);
 assert.equal(result.xAxis.axisLabel.interval,0);
});

test('pie slices preserve palette, original row selection and hidden groups',()=>{
 const pie={...spec,kind:'pie',x_type:'category',rules:[],rows:[['A',3,'A','a'],['B',7,'B','b']],legend:{order:['B','A']}};
 const result=compile(pie,theme,300);
 assert.equal(result.series[0].type,'pie');
 assert.deepEqual(result.series[0].data.map(p=>p.row),[1,0]);
 assert.equal(pointEvent(pie,0,result.series[0].data[0].row).keys[0],'b');
 assert.deepEqual(compile(pie,theme,300,new Set(['B'])).series[0].data.map(p=>p.name),['A']);
 assert.equal(result.xAxis,undefined);
});

test('hover templates combine formatted columns and escape literals and data',()=>{
 const data={...spec,rows:[[1,.42,'<img>','a']],formats:{x:'number',y:'percent:0'},hover:{tokens:[{text:'<b>'},{field:'group'},{text:' '},{field:'y',format:'percent:1'},{text:'\n&'}]}};
 const html=compile(data,theme,460).tooltip.formatter({data:{row:0},seriesName:'A'});
 assert.equal(html,'&lt;b&gt;&lt;img&gt; 42.0%<br>&amp;');
 assert.ok(compile({...data,hover:{formats:{y:'number:2'}}},theme,460).tooltip.formatter({data:{row:0},seriesName:'A'}).includes('0.42'));
});

test('x rules map semantic axes and plot annotations remain silent',()=>{
 const bar={...spec,kind:'bar',x_type:'category',rules:[{x:'a',label:'Cutoff'},{y:3,label:'Target'}],rows:[['a',2,'A','a']],annotations:[{x:'a',y:2,text:'Peak',position:'top'}]};
 const normal=compile(bar,theme,460);
 assert.equal(normal.useUTC,true);
 assert.deepEqual(normal.series[0].markLine.data,[{xAxis:0,name:'Cutoff'},{yAxis:3,name:'Target'}]);
 const horizontal=compile({...bar,orientation:'horizontal'},theme,460);
 assert.deepEqual(horizontal.series[0].markLine.data,[{yAxis:0,name:'Cutoff'},{xAxis:3,name:'Target'}]);
 assert.equal(normal.series.at(-1).id,'annotations');
 assert.equal(normal.series.at(-1).silent,true);
});


test('hover fields named like object properties retain literal column values',()=>{
 const data={...spec,columns:['x','y','constructor'],rows:[[1,2,'literal']],tooltip:['constructor'],hover:{tokens:[{field:'constructor'}]}};
 assert.equal(compile(data,theme,300).tooltip.formatter({data:{row:0}}),'literal');
});


test('explicit digits keep trailing zeros; defaults retain compact numbers', () => {
 assert.equal(formatter('percent:1')(.84), '84.0%');
 assert.equal(formatter('percent:1')(.034), '3.4%');
 assert.equal(formatter('number:2')(12), '12.00');
 assert.equal(displayValue({...spec, formats:{x:'number',y:'percent:1'}}, 'y', .84),'84.0%');
 assert.equal(formatter('number')(12), '12');
 assert.equal(formatter('percent')(.84), '84%');
});

test('stack gutters include formatted totals and percent endpoints at every width', () => {
 const bars={...spec,kind:'bar',x_type:'category',stacked:true,rules:[],
   rows:[['a',.58,'A','a'],['a',.42,'B','b']],formats:{x:'number',y:'percent:0'}};
 for (const width of [300,440,900]) {
   const option=compile(bars,theme,width);
   assert.ok(option.yAxis.axisLabel.width >= 28);
   assert.equal(option.yAxis.axisLabel.formatter(1),'100%');
 }
 const big=compile({...bars,rows:[['a',1600000,'A','a'],['a',1600000,'B','b']],formats:{x:'number',y:'number:0'}},theme,300);
 assert.ok(big.yAxis.axisLabel.width >= '3,200,000'.length*7);
});

test('temporal bar categories show short dates without changing identity', () => {
 const bars={...spec,kind:'bar',x_type:'category',x_temporal:true,rules:[],rows:[['2026-01-01T00:00:00+00:00',2,'A','a']]};
 const option=compile(bars,theme,300);
 assert.equal(option.xAxis.axisLabel.formatter(bars.rows[0][0]),'Jan 1');
 assert.equal(pointEvent(bars,0,0).x,bars.rows[0][0]);
});

test('missing pie values do not create legend entries; valid zero slices stay', () => {
 const pie={...spec,kind:'pie',rows:[['a',null,'A','a'],['b',2,'B','b'],['c',0,'C','c']]};
 assert.deepEqual(groupsOf(pie),['B','C']);
});

test('between-category rules and plot edge annotations do not extend the value domain', () => {
 const bars={...spec,kind:'bar',x_type:'category',rows:[['Mar',2,'A','a'],['Apr',3,'A','b']],
   rules:[{x_between:['Mar','Apr'],label:'Divider'}],annotations:[{x:'Mar',y:'top',text:'Actuals',position:'top'}]};
 const option=compile(bars,theme,440);
 assert.equal(option.series.find(s=>s.id==='between-rules').encode.y,-1);
 assert.equal(option.series.find(s=>s.id==='plot-annotations').encode.y,-1);
 assert.equal(option.series.find(s=>s.id==='plot-annotations').clip,false);
 assert.ok(option.grid.top>=36);
 assert.equal(compile({...bars,rows:[bars.rows[0]]},theme,440).series.some(s=>s.id==='between-rules'),false);
});

test('bar overlay follows category order with gaps, shared units and independent legend', () => {
 const bars={...spec,kind:'bar',x_type:'category',stacked:true,rules:[{y:7,label:'Target'}],
   rows:[['Jan',2,'A','a'],['Feb',3,'A','b'],['Mar',4,'B','c']],
   formats:{x:'number',y:'number:2'},legend:{order:['Forecast','A','B']},
   line:{label:'Forecast',columns:['m','total'],encoding:{x:'m',y:'total'},tooltip:[],rows:[['Mar',12],['Jan',8],['Apr',99]]}};
 const option=compile(bars,theme,300);
 const line=option.series.find(s=>s.id==='line-overlay');
 assert.equal(line.silent,true);
 assert.deepEqual(line.data.map(d=>d.value),[[0,8],[1,null],[2,12]]);
 assert.equal(line.connectNulls,false);
 assert.equal(option.series[0].markLine.data[0].yAxis,7);
 assert.equal(option.tooltip.formatter({seriesName:'Forecast',data:line.data[2]}),'Mar<br><strong>Forecast</strong>: 12.00');
 assert.deepEqual(groupsOf(bars),['Forecast','A','B']);
 assert.equal(compile(bars,theme,300,new Set(['Forecast'])).series.find(s=>s.id==='line-overlay').data.length,0);
 const percent={...bars,formats:{x:'number',y:'percent:0'},rows:[['Jan',.5,'A','a'],['Jan',.5,'B','b']],line:{...bars.line,rows:[['Jan',2]]}};
 assert.equal(compile(percent,theme,300).yAxis.max,undefined);
});

test('pie summary counts visible nonzero slices and skips missing and hidden names', () => {
 const pie={...spec,kind:'pie',rows:[['a',2,'A','a'],['b',null,'B','b'],['c',0,'C','c'],['d',1,'D','d']]};
 assert.equal(displayedRecords(pie),2);
 assert.equal(displayedRecords(pie,new Set(['D'])),1);
});
