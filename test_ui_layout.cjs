// Playwright regression tests for horizontal comparison and post-scrape auto-collapse.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.BASE_URL || 'http://127.0.0.1:8000';
const data={vehicles:[{price:150,year:2024,mileage:20,text:'テスト車両'}],pages:1,warnings:[]};
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({
  headless:true,
  ...(process.env.CHROMIUM_EXECUTABLE_PATH ? {
   executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']
  }:{})
 });
 try{
  const errors=[];
  async function setup(count){
   const page=await browser.newPage({viewport:{width:1440,height:1000}});
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base);
   await page.fill('#own-name','自社');
   await page.fill('#own-url','https://example.com/own');
   for(let i=1;i<count;i++){
    if(i>1)await page.click('#add');
    await page.locator('#rivals .url').nth(i-1).fill('https://example.com/rival/'+i);
   }
   return page;
  }
  {
   const page=await setup(5);
   await page.route('**/api/analyze?**',async route=>{
    await delay(route.request().url().includes('own')?100:500);
    await route.fulfill({json:data});
   });
   await page.click('#go');
   await page.waitForFunction(()=>stores[0].status==='done' && stores.some(s=>s.status!=='done'));
   assert(!await page.locator('#app').evaluate(e=>e.classList.contains('collapsed')),'collapsed before all requests finished');
   await page.waitForSelector('#app.collapsed');
   await page.waitForTimeout(350);
   const positions=()=>page.locator('.panel').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width};}));
   const before=await positions();
   assert.equal(before.length,5);
   assert(before[1].x>before[0].x);
   assert.equal(before[1].y,before[0].y);
   await page.locator('#panels').evaluate(e=>{e.scrollLeft=600;});
   await page.waitForTimeout(100);
   const after=await positions();
   assert(Math.abs(after[0].x-before[0].x)<1,'own store moved while scrolling');
   assert(after[1].x<before[1].x-100,'rival did not scroll');
   assert(await page.locator('#panels').evaluate(e=>e.classList.contains('scrolled')));
   const regular = await page.locator('#panels').evaluate(e=>({
    available:e.clientWidth, card:e.querySelector('.panel').getBoundingClientRect().width
   }));
   assert(Math.abs(regular.card/regular.available-.45)<.01,'regular card is not 45% of comparison area');
   await page.click('#fit-all');
   await page.waitForTimeout(350);
   const fitted = await page.locator('#panels').evaluate(e=>{
    const bounds=e.getBoundingClientRect();
    return {
     overflow:e.scrollWidth-e.clientWidth,
     cards:[...e.querySelectorAll('.panel')].map(p=>{
      const r=p.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top};
     }),left:bounds.left,right:bounds.right
    };
   });
   assert(fitted.overflow<=1,'fit mode still scrolls horizontally');
   for(const card of fitted.cards){
    assert(card.left>=fitted.left-1 && card.right<=fitted.right+1,'card outside comparison viewport');
    assert.equal(card.top,fitted.cards[0].top);
   }
   assert.equal(await page.locator('#fit-all').getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('.panel.own').evaluate(e=>getComputedStyle(e).position),'static');
   await page.click('#fit-all');
   await page.waitForTimeout(100);
   const restored=await page.locator('#panels').evaluate(e=>e.querySelector('.panel').getBoundingClientRect().width/e.clientWidth);
   assert(Math.abs(restored-.45)<.01,'cannot restore 45% cards');
   assert.equal(await page.locator('.panel.own').evaluate(e=>getComputedStyle(e).position),'sticky');
   console.log('PASS: 45% cards, fit-all button shows all five stores, toggle restores width and pinned own store');
   await page.click('#rail');
   assert(await page.locator('#setup-body').isVisible(),'cannot reopen input menu');
   await page.setViewportSize({width:390,height:844});
   await page.waitForTimeout(300);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile page overflow');
   assert(await page.locator('#panels').evaluate(e=>e.scrollWidth>e.clientWidth));
   await page.close();
   console.log('PASS: horizontal comparison, own store fixed, rivals scroll, collapse only after all complete, reopen and mobile scrolling');
  }
  for(const mixed of [false,true]){
   const page=await setup(2);
   await page.route('**/api/analyze?**',async route=>{
    if(mixed && route.request().url().includes('own'))await route.fulfill({json:data});
    else await route.fulfill({status:400,json:{detail:'URL error'}});
   });
   await page.click('#go');
   await page.waitForFunction(()=>!document.querySelector('#go').disabled);
   await page.waitForTimeout(100);
   assert.equal(await page.locator('#app').evaluate(e=>e.classList.contains('collapsed')),mixed);
   await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: failures alone keep menu open; partial success collapses; no JavaScript errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
