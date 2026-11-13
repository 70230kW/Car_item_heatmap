// Run against the app: BASE_URL=http://127.0.0.1:8000 node test_ui_queue.cjs
// Requires Playwright and its Chromium browser (or CHROMIUM_EXECUTABLE_PATH).
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.BASE_URL || 'http://127.0.0.1:8000';
const data = {vehicles:[{price:150,year:2024,mileage:20,text:'テスト車両'}],pages:1,warnings:[]};
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));

(async()=>{
  const browser = await chromium.launch({
    headless:true,
    ...(process.env.CHROMIUM_EXECUTABLE_PATH ? {
      executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,
      args:['--no-sandbox','--disable-dev-shm-usage']
    } : {})
  });
  try {
    async function setup(count) {
      const page = await browser.newPage();
      const errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base);
      await page.fill('#own-name','自社テスト');
      await page.fill('#own-url','https://example.com/stock/0');
      for(let i=1;i<count;i++){
        if(i>1) await page.click('#add');
        await page.locator('#rivals .store .name').nth(i-1).fill('他社テスト'+i);
        await page.locator('#rivals .store .url').nth(i-1).fill('https://example.com/stock/'+i);
      }
      return {page,errors};
    }

    // Four stores must never exceed the server's two concurrent scrape slots.
    {
      const {page,errors}=await setup(4);
      let active=0, peak=0, calls=0;
      await page.route('**/api/analyze?**',async route=>{
        calls++; active++; peak=Math.max(peak,active);
        await sleep(250);
        active--;
        await route.fulfill({json:data});
      });
      await page.click('#go');
      await page.waitForFunction(()=>document.querySelector('#panels').textContent.includes('順番待ち'));
      await page.waitForFunction(()=>!document.querySelector('#go').disabled);
      assert.equal(calls,4); assert.equal(peak,2);
      assert.equal(await page.locator('.panel .failed').count(),0);
      assert.equal(await page.locator('.panel .stats dd').count(),12);
      assert.deepEqual(errors,[]);
      await page.close();
      console.log('PASS: four stores queued, peak concurrency two, all succeed');
    }

    // Both 503 and 429 should be retried, respecting Retry-After.
    for (const status of [503,429]) {
      const {page,errors}=await setup(1);
      let calls=0, first;
      await page.route('**/api/analyze?**',async route=>{
        calls++;
        if(calls===1) {
          first=Date.now();
          await route.fulfill({status,headers:{'Retry-After':'1'},json:{detail:'混雑中'}});
        } else {
          assert(Date.now()-first>=900,'Retry-After ignored');
          await route.fulfill({json:data});
        }
      });
      await page.click('#go');
      await page.waitForFunction(()=>document.querySelector('#panels').textContent.includes('自動再試行'));
      await page.waitForFunction(()=>!document.querySelector('#go').disabled);
      assert.equal(calls,2);
      assert.equal(await page.locator('.failed').count(),0);
      assert.deepEqual(errors,[]);
      await page.close();
      console.log('PASS: '+status+' automatically recovers');
    }

    // Permanent errors must not be retried.
    {
      const {page,errors}=await setup(1);
      let calls=0;
      await page.route('**/api/analyze?**',async route=>{
        calls++;
        await route.fulfill({status:400,json:{detail:'URLを確認してください'}});
      });
      await page.click('#go');
      await page.waitForSelector('.failed');
      assert.equal(calls,1);
      assert((await page.locator('.failed').innerText()).includes('URLを確認してください'));
      assert.deepEqual(errors,[]);
      await page.close();
      console.log('PASS: permanent errors are not retried');
    }

    // Changing to the sample cancels pending retries and queued stores.
    {
      const {page,errors}=await setup(4);
      let calls=0;
      await page.route('**/api/analyze?**',async route=>{
        calls++;
        await route.fulfill({status:503,headers:{'Retry-After':'1'},json:{detail:'混雑中'}});
      });
      await page.click('#go');
      await page.waitForFunction(()=>document.querySelector('#panels').textContent.includes('自動再試行'));
      await page.evaluate(()=>startDemo());
      const count=calls;
      await sleep(1300);
      assert.equal(calls,count);
      assert.equal(await page.locator('.panel').count(),3);
      assert((await page.locator('#workspace-status').innerText()).includes('サンプル'));
      assert.deepEqual(errors,[]);
      await page.close();
      console.log('PASS: sample selection cancels retries and queue');
    }

    // Exercise all 500 page requests without waiting 499 seconds in this mock test.
    {
      const {page,errors}=await setup(1);
      await page.click('details.opts summary');
      await page.selectOption('#pages','500');
      await page.evaluate(()=>{ waitForRetry = async (_ms, signal) => { if(signal.aborted) throw new DOMException('Aborted','AbortError'); }; });
      let calls=0;
      await page.route('**/api/analyze-page?**', async route=>{
        calls++;
        await route.fulfill({json:{
          vehicles:[{...data.vehicles[0],id:'AU'+calls}],
          pages:1,warnings:[],
          next_url:calls<500 ? 'https://example.com/stock/?PN='+(calls+1) : null
        }});
      });
      await page.click('#go');
      await page.waitForFunction(()=>!document.querySelector('#go').disabled,{},{timeout:120000});
      assert.equal(calls,500);
      assert.equal(await page.evaluate(()=>stores[0].data.pages),500);
      assert.equal(await page.evaluate(()=>stores[0].data.vehicles.length),500);
      assert.equal(await page.locator('.failed').count(),0);
      assert.deepEqual(errors,[]);
      await page.close();
      console.log('PASS: 500 incremental pages, 500 distinct IDs retained');
    }

    // A failed later page must leave the successful pages visible.
    {
      const {page,errors}=await setup(1);
      await page.click('details.opts summary');
      await page.selectOption('#pages','500');
      await page.evaluate(()=>{ waitForRetry = async ()=>{}; });
      let calls=0;
      await page.route('**/api/analyze-page?**',async route=>{
        calls++;
        if(calls===3) await route.fulfill({status:502,json:{detail:'upstream unavailable'}});
        else await route.fulfill({json:{
          vehicles:[{...data.vehicles[0],id:'AU'+calls}],pages:1,warnings:[],
          next_url:'https://example.com/stock/?PN='+(calls+1)
        }});
      });
      await page.click('#go');
      await page.waitForFunction(()=>!document.querySelector('#go').disabled);
      assert.equal(calls,3);
      assert.equal(await page.evaluate(()=>stores[0].data.pages),2);
      assert.equal(await page.evaluate(()=>stores[0].data.vehicles.length),2);
      assert((await page.locator('#panels .notes').innerText()).includes('2ページ分の結果を保持'));
      assert.equal(await page.locator('.failed').count(),0);
      assert.deepEqual(errors,[]);
      await page.close();
      console.log('PASS: failure on page three retains first two pages');
    }
  } finally {
    await browser.close();
  }
})().catch(e=>{console.error(e);process.exit(1)});
