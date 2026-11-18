const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8001');
  await page.click('#try-demo');
  await page.evaluate(()=>{
   const source=stores.slice();
   stores=Array.from({length:8},(_,i)=>({...source[i%3],key:'grid-'+i,name:(i===0?'自社':'比較店')+(i+1),role:i===0?'own':'rival',data:{...source[i%3].data,vehicles:source[i%3].data.vehicles.slice(0,12)}}));
   buildPanels();renderAll();
  });
  await page.click('#graphs-only');
  assert(await page.locator('.setup').isHidden());
  assert(await page.locator('#panels .stats').first().isHidden());
  assert(await page.locator('#cat-compare').isHidden());
  assert(await page.locator('#panels .plate-name').first().isVisible());
  await page.click('#fit-all');
  await page.waitForFunction(()=>document.querySelector('#panels').style.getPropertyValue('--graph-columns')==='2');
  await page.waitForFunction(()=>[...document.querySelectorAll('#panels .chart')].every(e=>e._fullLayout && Math.abs(e._fullLayout.width-e.clientWidth)<2 && e._fullLayout.height<250));
  const boxes=await page.locator('#panels .panel').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,bottom:r.bottom};}));
  assert.equal(new Set(boxes.map(b=>Math.round(b.x))).size,2);
  assert.equal(new Set(boxes.map(b=>Math.round(b.y))).size,4);
  assert(boxes.every(b=>b.bottom<=1000),'eight panels do not fit the desktop viewport');
  const landscape=()=>page.locator('#panels .chart').evaluateAll(es=>es.every(e=>e.clientWidth/e.clientHeight>=1.75));
  assert(await landscape());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:'/workspace/artifacts/graphs-only-eight-stores.png',fullPage:true});
  for(const height of [900,768]){
    await page.setViewportSize({width:1440,height});
    await page.waitForFunction(h=>[...document.querySelectorAll('#panels .panel')].every(e=>e.getBoundingClientRect().bottom<=h),height);
    assert(await landscape());
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.click('#graph-settings');
  assert(await page.locator('#graph-display-controls').isVisible());
  await page.click('label[for="style-dots"]');
  await page.waitForFunction(()=>[...document.querySelectorAll('#panels .chart')].every(e=>e.data?.[0]?.type==='scatter'));
  await page.click('#graph-settings');
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('#panels').style.getPropertyValue('--graph-columns')==='1');
  await page.waitForFunction(()=>[...document.querySelectorAll('#panels .chart')].every(e=>e._fullLayout && Math.abs(e._fullLayout.width-e.clientWidth)<2));
  assert(await landscape());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.click('#graphs-only');
  assert(await page.locator('.setup').isVisible());
  assert(await page.locator('#panels .stats').first().isVisible());
  assert(await page.locator('#cat-compare').isVisible());
  assert.equal(await page.locator('#graphs-only').getAttribute('aria-pressed'),'false');
  assert.equal(await page.locator('#panels .plate-name').count(),8);
  await page.click('#graphs-only');
  await page.click('#overlay-toggle');
  await page.waitForFunction(()=>document.querySelector('#overlay-panel .chart')?.data?.length===8);
  assert.equal(new Set(await page.locator('#overlay-panel .chart').evaluate(e=>e.data.map(t=>t.marker.symbol))).size,8);
  assert(await page.locator('#overlay-panel .stats').isHidden());
  assert(await page.locator('#company-list').isVisible());
  await page.click('#graphs-only');
  assert(await page.locator('#overlay-panel .stats').isVisible());
  assert.deepEqual(errors,[]);
  console.log('PASS: graphs-only hides details, eight companies fit 2×4, landscape plots, display settings, one-column mobile and full restore');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
