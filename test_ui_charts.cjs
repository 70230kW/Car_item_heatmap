// Requires Playwright and a running app. Set BASE_URL or CHROMIUM_EXECUTABLE_PATH as needed.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({
  headless:true,
  ...(process.env.CHROMIUM_EXECUTABLE_PATH ? {
   executablePath:process.env.CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']
  }:{})
 });
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8000');
  await page.click('#try-demo');await page.waitForSelector('.js-plotly-plot');
  // Match the reported broad year range, keeping a legitimate old car in the data.
  await page.evaluate(()=>{
   stores[0].data.vehicles[0].year=1990;
   stores[0].data.vehicles[1].year=2026;
   renderAll();
  });
  async function checkTicks(){
   await page.waitForFunction(()=>[...document.querySelectorAll("#panels .chart")].every(e=>e._fullLayout && Math.abs(e._fullLayout.width-e.clientWidth)<2));
   await page.waitForFunction(()=>[...document.querySelectorAll('#panels .chart')].every(e=>e._fullLayout?.xaxis.tickvals.length<10));
   const axes=await page.locator('#panels .chart').evaluateAll(charts=>charts.map(chart=>({
    ticks:chart._fullLayout.xaxis.tickvals,
    range:chart._fullLayout.xaxis.range,
    labels:[...chart.querySelectorAll('.xtick text')].map(e=>{
     const r=e.getBoundingClientRect();return {text:e.textContent,left:r.left,right:r.right};
    })
   })));
   for(const axis of axes){
    assert(axis.range[0]<1990 && axis.range[1]>2026,'old/new vehicles cropped');
    assert(axis.labels.length>=2,'too few year labels');
    for(let i=0;i<axis.labels.length;i++){
     assert(/^\d{4}年$/.test(axis.labels[i].text));
     if(i)assert(axis.labels[i].left-axis.labels[i-1].right>=4,'year labels overlap');
    }
   }
   assert.deepEqual(axes[0].ticks,axes[1].ticks,'stores use different year ticks');
  }
  await checkTicks();
  assert.deepEqual(await page.locator('#panels .chart').first().evaluate(e=>e.data.map(t=>t.type)),['heatmap','heatmap','heatmap']);
  await page.click('label[for="style-dots"]');
  assert.deepEqual(await page.locator('#panels .chart').first().evaluate(e=>e.data.map(t=>t.type)),['scatter']);
  assert(await page.locator('#smooth-control').isHidden());
  const dotsCount=await page.locator('#panels .chart').first().evaluate(e=>e.data[0].x.length);
  assert.equal(dotsCount,48);
  assert(await page.locator('#panels .chart').first().evaluate(e=>e.data[0].marker.color.every(color=>['new','short','used'].map(categoryColor).includes(color))));
  assert.notEqual(await page.locator('#panels .chart .scatterlayer .points').first().evaluate(e=>getComputedStyle(e).filter),'none');
  assert.equal(await page.locator('#panels .chart .xaxislayer-above').first().evaluate(e=>getComputedStyle(e).filter),'none');
  await checkTicks();
  await page.click('label[for="ax-km"]');
  assert.deepEqual(await page.locator('#panels .chart').first().evaluate(e=>e.data.map(t=>t.type)),['scatter']);
  await page.click('label[for="style-blur"]');
  assert.deepEqual(await page.locator('#panels .chart').first().evaluate(e=>e.data.map(t=>t.type)),['heatmap','heatmap','heatmap']);
  assert(await page.locator('#smooth-control').isVisible());
  await page.click('label[for="md-share"]');
  await page.click('label[for="ax-year"]');
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(300);
  await checkTicks();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.setViewportSize({width:1600,height:1000});
  await page.waitForTimeout(300);
  await checkTicks();
  assert.deepEqual(errors,[]);
  console.log('PASS: 1990–2026 labels do not overlap on desktop/mobile; shared year ticks; exclusive dot/blur traces; both axes and controls work');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
