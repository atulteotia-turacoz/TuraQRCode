import {test,expect} from '@playwright/test';

test('protected tracked barcode preserves scan counts through retries and cross-origin desktop/mobile navigation',async({page,browser})=>{
 const origin='http://127.0.0.1:5183';
 await page.goto('/register');await page.getByLabel('Full name').fill('Redirect Review');await page.getByLabel('Email address').fill(`redirect-${Date.now()}@example.com`);await page.getByLabel('Password',{exact:true}).fill('RedirectReview123!');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Create account',exact:true}).click();await expect(page).toHaveURL(/\/app$/);
 const created=await page.request.post('/api/codes',{headers:{Origin:origin},data:{name:'Protected barcode',kind:'barcode',mode:'dynamic',content:{format:'code128',value:origin+'/terms',tracked:true},password:'ScanAccess123',mobile_url:origin+'/privacy'}});
 expect(created.status()).toBe(201);const code=await created.json();
 for(const mobile of [false,true]){
  const context=mobile?await browser.newContext({viewport:{width:390,height:844},userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile'}):null;
  const visitor=context?await context.newPage():page;
  await visitor.goto(code.qr_payload);await expect(visitor.locator('form')).toHaveAttribute('action','/r/'+code.slug+'?via=barcode');
  await visitor.getByLabel('Access password').fill('Wrong');await visitor.getByRole('button',{name:'Continue',exact:true}).click();await expect(visitor.getByRole('alert')).toContainText('incorrect');await expect(visitor.locator('form')).toHaveAttribute('action','/r/'+code.slug+'?via=barcode');
  await visitor.getByLabel('Access password').fill('ScanAccess123');await visitor.getByRole('button',{name:'Continue',exact:true}).click();await expect(visitor).toHaveURL(origin+(mobile?'/privacy':'/terms'));await expect(visitor.getByRole('heading',{name:mobile?'Privacy Policy':'Terms & Conditions',exact:true})).toBeVisible();
  if(context)await context.close();
 }
 let stats=await(await page.request.get('/api/analytics?code_id='+code.id)).json();expect(stats.scans).toBe(2);expect(stats.clicks).toBe(0);expect(stats.recent.every((event:{channel:string})=>event.channel==='barcode')).toBeTruthy();
 await page.goto(code.short_url);await page.getByLabel('Access password').fill('ScanAccess123');await page.getByRole('button',{name:'Continue',exact:true}).click();await expect(page).toHaveURL(origin+'/terms');
 stats=await(await page.request.get('/api/analytics?code_id='+code.id)).json();expect(stats.scans).toBe(2);expect(stats.clicks).toBe(1);
});
