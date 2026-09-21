const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '..');
const dom = new JSDOM(fs.readFileSync(path.join(root, 'site/index.html'), 'utf8'), {
  url: 'https://buffedlizard55-lab.github.io/VacationSchedule/', runScripts: 'outside-only'
});
const w = dom.window;
w.fetch = () => Promise.reject(new Error('offline test'));
w.eval(fs.readFileSync(path.join(root,'site/data/schedule-data.js'),'utf8'));
w.eval(fs.readFileSync(path.join(root,'site/app.js'),'utf8'));
w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
const e = w.FreeTimeEngine;
const $ = id => w.document.getElementById(id);
const go = date => { $('dateInput').value = date; $('dateInput').dispatchEvent(new w.Event('change')); };
let checks = 0;
function check(value, message) { assert.ok(value, message); checks++; }
function payload(date, raw, ids=[133,147], status={}) {
  return {dates:[{date, games:[{gamePk:1,gameDate:raw,teams:{away:{team:{id:ids[0],name:'Athletics'}},home:{team:{id:ids[1],name:'Yankees'}}},status}]}]};
}
(async () => {
  await new Promise(resolve => setTimeout(resolve, 0));
  check(w.document.querySelectorAll('#mlbClubs .club-item').length===30,'30 clubs shown');
  check(w.document.querySelectorAll('#mlbClubs .pill.high').length===2,'Giants and Athletics flagged');
  check(!w.document.body.textContent.includes('fully verified'),'No blanket verification claim');
  check(!Array.from(w.document.querySelectorAll('a[href]')).some(a => a.getAttribute('href').includes('NOT RELEASED')),'Estimation prose is never a broken source link');
  go('2028-02-29');
  check(w.document.querySelectorAll('.calendar-day').length===29,'Leap day calendar');
  $('nextDay').click();
  check($('dateInput').value==='2028-03-01','Leap date navigation');
  go('2026-01-01');
  check($('prevDay').disabled && $('prevMonth').disabled,'Lower bound navigation');
  go('2029-12-31');
  check($('nextDay').disabled && $('nextMonth').disabled,'Upper bound navigation');
  go('2026-09-29');
  check(!w.document.querySelector('#scoreboard .onair').textContent.includes('on air'),'TBD never falsely live');
  check($('freeList').textContent.includes('No free window'),'Full day reserved for TBD');
  check($('decisionBody').textContent.includes('Past window'),'Past vacations clearly labelled');
  const game = e.normalizeMlb(payload('2026-09-20','2026-09-21T02:00:00Z'),'https://statsapi.mlb.com/')[0];
  check(game.date_local==='2026-09-20','UTC game mapped to PT date');
  check(game.network.includes('KNEW') && !game.network.includes('KNBR'),'Athletics uses KNEW, not Giants station');
  const tbd = e.normalizeMlb(payload('2026-11-01',null),'https://statsapi.mlb.com/')[0];
  const iv = e.gameToInterval(tbd);
  check((iv.end-iv.start)/60000===1500,'Null timestamp reserves full DST day');
  check(e.gameToInterval({...game,cancelled:true})===null,'Cancelled original fixture no longer blocks');
  const replacement = {...game,date_local:'2026-09-29'};
  check(e.combinedGames([replacement]).filter(g=>g.league==='MLB' && g.date_local==='2026-09-29').length===1,'Live fixtures replace aggregate placeholders');
  // Race: old request resolves after navigation; it must not replace the newer date.
  const pending = [];
  w.fetch = url => new Promise(resolve => pending.push({url,resolve}));
  go('2026-09-20');
  go('2026-09-21');
  pending[1].resolve({ok:true,json:()=>Promise.resolve(payload('2026-09-21','2026-09-22T02:00:00Z'))});
  await new Promise(resolve => setTimeout(resolve, 0));
  pending[0].resolve({ok:true,json:()=>Promise.resolve(payload('2026-09-20','2026-09-21T02:00:00Z'))});
  await new Promise(resolve => setTimeout(resolve, 0));
  check($('dateInput').value==='2026-09-21','Old response cannot navigate backwards');
  check($('mlbNote').textContent.includes('2026-09-21'),'Old response cannot replace current feed status');
  check(w.document.querySelectorAll('#scoreboard .game').length>0,'Latest response remains on board');
  console.log(`${checks} publication/regression browser checks passed`);
  dom.window.close();
})().catch(error=>{console.error(error); dom.window.close();process.exitCode=1;});
