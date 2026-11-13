const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
 try{
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.BASE_URL || 'http://127.0.0.1:8000';
  await page.goto(base);
  assert.equal(await page.locator('#saved-count').innerText(),'0');
  const name='自社 <img src=x onerror=alert(1)>';
  const url='https://example.com/stock?sort=price&page=1';
  await page.fill('#own-name',name);
  await page.fill('#own-url',url);
  await page.locator('.store.own .save-store').click();
  assert.equal(await page.locator('#saved-count').innerText(),'1');
  await page.locator('.store.own .save-store').click();
  assert.equal(await page.locator('#saved-count').innerText(),'1','duplicate was saved');
  await page.locator('#rivals .name').first().fill('他社B');
  await page.locator('#rivals .url').first().fill('https://example.net/stock');
  await page.locator('#rivals .save-store').first().click();
  assert.equal(await page.locator('#saved-count').innerText(),'2');
  await page.reload();
  assert.equal(await page.locator('#saved-count').innerText(),'2');
  await page.fill('#own-name','');
  await page.fill('#own-url','');
  await page.locator('.store.own .saved-picker').selectOption('0');
  assert.equal(await page.inputValue('#own-name'),name);
  assert.equal(await page.inputValue('#own-url'),url);
  await page.click('#add');
  await page.locator('#rivals .saved-picker').last().selectOption('1');
  assert.equal(await page.locator('#rivals .name').last().inputValue(),'他社B');
  await page.locator('#rivals .url').last().fill('javascript:alert(1)');
  await page.locator('#rivals .save-store').last().click();
  assert.equal(await page.locator('#saved-count').innerText(),'2');
  assert(await page.locator('#saved-message').evaluate(e=>e.classList.contains('error')));
  await page.locator('#saved-stores summary').click();
  assert.equal(await page.locator('#saved-list strong').first().textContent(),name);
  assert.equal(await page.locator('#saved-list img').count(),0,'saved name treated as HTML');
  await page.locator('#saved-list .delete-saved').first().click();
  assert.equal(await page.locator('#saved-count').innerText(),'1');
  assert.equal(await page.inputValue('#own-name'),name,'deleting registration cleared inputs');
  await page.reload();
  assert.equal(await page.locator('#saved-count').innerText(),'1');
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  await page.close();

  const blocked=await browser.newPage();
  await blocked.addInitScript(()=>{
   const original=Storage.prototype.setItem;
   Storage.prototype.setItem=function(key,value){
    if(key==='inventory-heatmap:registered-stores:v1')throw new DOMException('Full','QuotaExceededError');
    return original.call(this,key,value);
   };
  });
  await blocked.goto(base);
  await blocked.fill('#own-name','保存できない店舗');
  await blocked.fill('#own-url','https://example.com/');
  await blocked.locator('.store.own .save-store').click();
  assert.equal(await blocked.locator('#saved-count').innerText(),'0');
  assert((await blocked.locator('#saved-message').innerText()).includes('保存できませんでした'));
  await blocked.close();
  console.log('PASS: register, deduplicate, reload, recall own/rivals, dynamic rows, delete without clearing inputs, URL validation, safe text, mobile, storage failure');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
