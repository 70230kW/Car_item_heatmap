const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const vehicle={id:'row-1',price:150,year:2024,mileage:0,text:'取込車両'};
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error' && m.text().includes('グラフ'))errors.push(m.text())});
  await page.route('**/api/google/status',route=>route.fulfill({json:{configured:true,connected:true}}));
  const headers=['会社名','車名','価格（円）','年式','走行距離（万km）'];
  await page.route('**/api/google/preview',route=>route.fulfill({json:{
   id:'a'.repeat(40),title:'在庫表',sheets:['東京','大阪'],sheet:JSON.parse(route.request().postData()).sheet || '東京',
   headers,rows:[['A社','ヤリス','1,500,000','2024',0]],truncated:false
  }}));
  let imported=0;
  await page.route('**/api/google/import',async route=>{
   const body=JSON.parse(route.request().postData());imported++;
   assert.deepEqual(body.mapping,{price:2,year:3,mileage:4,name:1,company:0});
   assert.equal(body.price_unit,'yen');assert.equal(body.mileage_unit,'man_km');
   await route.fulfill({json:{
    source:'sheet-'+imported,url:body.url,sheet:body.sheet,rows_read:2,skipped_rows:0,
    stores:body.role==='own' ? [{name:'自社データ',role:'own',data:{vehicles:[vehicle],pages:1,warnings:[]}}]
      : [{name:'A社',role:'rival',data:{vehicles:[vehicle],pages:1,warnings:[]}},{name:'B社',role:'rival',data:{vehicles:[{...vehicle,id:'row-2',price:250}],pages:1,warnings:[]}}]
   }});
  });
  await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8001');
  await page.locator('.google-sheets summary').click();
  await page.waitForFunction(()=>!document.querySelector('#sheet-read').disabled);
  await page.fill('#sheet-url','https://docs.google.com/spreadsheets/d/'+'a'.repeat(40)+'/edit');
  await page.click('#sheet-read');
  await page.waitForSelector('#sheet-mapping:visible');
  assert.equal(await page.locator('#map-price').inputValue(),'2');
  assert.equal(await page.locator('#sheet-price-unit').inputValue(),'yen');
  assert.equal(await page.locator('#sheet-mileage-unit').inputValue(),'man_km');
  await page.selectOption('#sheet-tab','大阪');
  assert(await page.locator('#sheet-mapping').isHidden());
  await page.click('#sheet-read');
  await page.waitForSelector('#sheet-mapping:visible');
  await page.click('#sheet-import');
  await page.waitForFunction(()=>stores.length===2);
  await page.selectOption('#sheet-role','own');
  await page.fill('#sheet-url','https://docs.google.com/spreadsheets/d/'+'b'.repeat(40)+'/edit');
  await page.click('#sheet-read');
  await page.waitForSelector('#sheet-mapping:visible');
  await page.click('#sheet-import');
  await page.waitForFunction(()=>stores.length===3);
  assert.equal(await page.evaluate(()=>stores[0].role),'own');
  await page.fill('#own-url','https://example.com/own');
  await page.locator('#rivals .url').first().fill('https://example.com/rival');
  let fetched=0;
  await page.route('**/api/analyze?**',route=>{fetched++;return route.fulfill({json:{vehicles:[vehicle],pages:1,warnings:[]}});});
  await page.click('#go');
  await page.waitForSelector('#app.collapsed');
  assert.equal(fetched,1,'imported own data should replace web own');
  assert.equal(await page.evaluate(()=>stores.length),4,'imported sheets disappeared during scrape');
  await page.click('#overlay-toggle');
  assert.equal(await page.locator('#company-list .company-toggle').count(),4);
  await page.click('#rail');
  await page.route('**/api/google/logout',route=>route.fulfill({json:{connected:false}}));
  await page.click('#google-logout');
  await page.waitForFunction(()=>stores.every(s=>!s.sourceGoogle));
  assert.equal(await page.evaluate(()=>stores.length),1);
  assert.deepEqual(errors,[]);
  console.log('PASS: private-sheet preview, column/units mapping, tab choice, multiple sheet sources, own replacement, web + sheet comparison, company list, disconnect clears private data');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
