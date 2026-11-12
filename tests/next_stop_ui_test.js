// Optional Node-only DOM mock: execute the actual inline UI, no browser or network.
const vm = require('node:vm');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('src/location_lab/next_stop_web.py', 'utf8').split('<script>')[1].split('</script>')[0];
const elements = Object.fromEntries(['next','clear','connect_mock','disconnect_mock','progress','current','upcoming','address','state','notice'].map(id=>[id,{id,disabled:false,textContent:''}]));
const buttons = ['next','clear','connect_mock','disconnect_mock'].map(id=>elements[id]);
let count=0, version=0, pending=null, failure=false, storageFault=false;
const context = vm.createContext({
 document:{querySelectorAll:()=>buttons,getElementById:id=>elements[id]},
 crypto:{randomUUID:()=>require('node:crypto').randomUUID()},
 fetch: async (url, options)=>{
  if(failure)throw Error('offline');
  if(url==='/api/command'){
   const command=JSON.parse(options.body);
   assert.equal(command.action,'next');
   assert.equal(command.version,version);
   if(pending)await pending;
   count++;version++;
   return {ok:true,json:async()=>({code:'ok'})};
  }
  return {ok:true,json:async()=>({storage_fault:storageFault,completed:count,total:10,mock_connected:true,state:'active',can_next:true,epoch:'test',version,current:{name:'Mock'},next:{name:'Next',address:'Synthetic'}})};
 }
});
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 vm.runInContext(source,context);await settle();
 let release;pending=new Promise(resolve=>release=resolve);
 elements.next.onclick({detail:1});elements.next.onclick({detail:1});
 assert.equal(elements.next.disabled,true);
 release();await settle();pending=null;
 assert.equal(count,1);
 // Second dblclick event after the first request has already completed.
 elements.next.onclick({detail:2});await settle();assert.equal(count,1);
 let prevented=0;
 for(const key of ['Enter',' '])elements.next.onkeydown({repeat:true,key,preventDefault:()=>prevented++});
 assert.equal(prevented,2);
 elements.next.onclick({detail:1});await settle();assert.equal(count,2);
 failure=true;elements.next.onclick({detail:1});await settle();
 assert.equal(count,2);assert.equal(elements.next.disabled,true);
 assert.match(elements.notice.textContent,/未知/);
 failure=false;storageFault=true;await vm.runInContext('refresh().then(controls)',context);
 assert.ok(buttons.every(b=>b.disabled));
 console.log('PASS: in-flight clicks, completed-response dblclick, key-repeat, explicit next, interrupted request');
})().catch(error=>{console.error(error);process.exitCode=1;});
