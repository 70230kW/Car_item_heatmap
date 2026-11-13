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
   stores[0].data.vehicles=[5,500,20000,null].map((mileage,i)=>({price:100+i*20,year:2024,mileage,text:'色テスト'+i}));
   renderAll();
  });
  await page.waitForFunction(()=>document.querySelector('#panels .chart').data?.length===4);
  assert(await page.locator('#panels .chart').first().evaluate(chart=>{
   const types=chart.data.every(t=>t.type==='heatmap');
   const matched=chart.data.every(t=>t.colorscale.at(-1)[1]===categoryColor(t.meta.category));
   const keys=chart.data.map(t=>t.meta.category);
   return types && matched && ['new','short','used','unknown'].every(k=>keys.includes(k));
  }));
  assert(await page.evaluate(()=>{
   const sh=shared(),p=sh.per.get(stores[0].key);
   return p.z.every((row,j)=>row.every((value,i)=>{
    const sum=Object.values(p.categoryZ).reduce((total,matrix)=>total+matrix[j][i],0);
    return Math.abs(sum-value)<1e-9;
   }));
  }),'category densities do not sum to total density');
  await page.click('label[for="style-dots"]');
  await page.waitForFunction(()=>document.querySelector('#panels .chart').data?.[0]?.type==='scatter');
  const expected=await page.evaluate(()=>['new','short','used','unknown'].map(categoryColor));
  assert.deepEqual(await page.locator('#panels .chart').first().evaluate(e=>e.data[0].marker.color),expected);
  const barColors=await page.evaluate(()=>{
   return ['new','short','used','unknown'].map(key=>{
    const marker=document.createElement('i');marker.style.color=categoryColor(key);document.body.append(marker);
    const color=getComputedStyle(marker).color;marker.remove();
    return color===getComputedStyle(document.querySelector('#panels .c-'+key)).backgroundColor;
   });
  });
  assert(barColors.every(Boolean),'dot/category colors do not match the inventory bar');
  await page.click('#overlay-toggle');
  await page.waitForFunction(()=>document.querySelector('#overlay-panel .chart')?.data?.length===3);
  const own=await page.locator('#overlay-panel .chart').evaluate(e=>e.data.find(t=>t.name.startsWith('自社')));
  assert.deepEqual(own.marker.color,expected);
  assert.equal(own.marker.symbol,'circle');
  assert.equal(new Set(await page.locator('#overlay-panel .chart').evaluate(e=>e.data.map(t=>t.marker.symbol))).size,3);
  await page.click('label[for="ax-km"]');
  await page.waitForFunction(()=>document.querySelector('#overlay-panel .chart').data.find(t=>t.name.startsWith('自社')).x.length===3);
  assert.deepEqual(await page.locator('#overlay-panel .chart').evaluate(e=>e.data.find(t=>t.name.startsWith('自社')).marker.color),expected.slice(0,3));
  assert.deepEqual(errors,[]);
  console.log('PASS: category-matched dots/blur/bar, unknown-mileage gray, category density conservation, company shapes and both axes');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
