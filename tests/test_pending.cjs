const { JSDOM } = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const F = require('../dist/feed.js');
const root = path.resolve(__dirname, '../dist');
const now = new Date().toISOString();
const base = {status:'candidate',source_type:'community',source_name:'測試來源',first_seen_at:now,checked_at:now,body_read:true,category:'其他',tags:['其他'],reasons:['領取／購買方式未確認'],hurdles:[],score:50,discount:{kind:'bogo',percent:50,strong:true},discount_label:'買一送一',steps:'方式待確認'};
const pending = [
 {...base,id:'food',title:'全聯餅乾買一送一',url:'https://example.org/food'},
 {...base,id:'game',title:'貼圖13折',url:'https://example.org/game'},
 {...base,id:'tech',title:'耳機特價情報',body_read:false,discount:null,url:'https://example.org/tech'},
 {...base,id:'stale',title:'耳機降價舊情報',retained:true,url:'https://example.org/stale'},
 {...base,id:'daily',title:'牙膏特價',discount:null,url:'https://example.org/daily'},
 {...base,id:'other',title:'未知商品XYZ',discount:null,url:'https://example.org/other'}
];
const fixture = {schema_version:6,is_demo:false,run_status:'ok',sources:[],deals:[],conditional:[],pending};
let checks=0;const check=(v,e)=>{assert.deepEqual(v,e);checks++;};
(async()=>{
 check(F.topics(pending[0]),['餐飲食品']);
 check(F.primary({...pending[0],tags:F.topics(pending[0])}),'餐飲食品');
 check(F.primary({...base,tags:['任務']}),'任務');
 check(F.primary({...base,tags:F.topics({...base,title:'Steam免費遊戲',tags:['3C','遊戲娛樂']})}),'遊戲娛樂');
 check(pending.map(F.pendingStage),['clear','clear','summary','stale','discount','discount']);
 check(F.pendingStage({...base,discount:{strong:true,range_claim:true}}),'discount');
 const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'https://local.example/',runScripts:'outside-only'});
 dom.window.fetch=async()=>({ok:true,json:async()=>fixture});
 for(const file of ['feed.js','app.js'])dom.window.eval(fs.readFileSync(path.join(root,file),'utf8'));
 await new Promise(r=>setImmediate(r));
 const d=dom.window.document,$=s=>d.querySelector(s),click=s=>$(s).click(),count=()=>d.querySelectorAll('.deal-card').length;
 check($('#catalogNotice').hidden,false);check($('#catalogCopy').textContent.includes('6 則'),true);
 check($('#filters').closest('details'),null);
 click('#browsePending');
 check(count(),6);check(d.querySelectorAll('.pending-topic').length,5);
 check($('#pendingControls').hidden,false);
 check($('#pendingStages [data-stage="clear"]').textContent,'有明確折扣 2');
 check($('.missing-summary').hidden,false);
 check($('#filters [data-category="其他"]').textContent,'其他／未辨識 1');
 click('[data-category="餐飲食品"]');check(count(),1);check($('.topic-heading').textContent,'餐飲食品 · 1 則');
 click('[data-stage="summary"]');check(count(),0);check($('#emptyState').hidden,false);
 click('#clearFilters');check(count(),6);check($('#pendingStages .active').dataset.stage,'all');
 click('[data-stage="clear"]');check(count(),2);
 click('[data-stage="summary"]');check(count(),1);check($('article h3').textContent,'耳機特價情報');
 click('[data-stage="stale"]');check(count(),1);check($('article h3').textContent,'耳機降價舊情報');
 click('[data-stage="all"]');
 $('.save-deal').click();click('#savedButton');check(count(),1);check($('#pendingControls').hidden,true);check(d.querySelectorAll('.pending-topic').length,0);
 dom.window.close();console.log(`PASS: ${checks} pending grouping/filter assertions`);
})().catch(e=>{console.error(e);process.exitCode=1;});
