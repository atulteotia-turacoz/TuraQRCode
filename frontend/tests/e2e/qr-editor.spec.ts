import {test,expect,type Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';
async function register(page:import('@playwright/test').Page){await page.goto('/register');await page.getByLabel('Full name').fill('Frame Review');await page.getByLabel('Email address').fill(`frame-logo-${Date.now()}@example.com`);await page.getByLabel('Password',{exact:true}).fill('FrameReview123!');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Create account',exact:true}).click();await expect(page).toHaveURL(/\/app$/);}

function nextPreview(page:Page,matches:(design:Record<string,unknown>)=>boolean){
 return page.waitForResponse(response=>response.url().includes('/api/qr/preview?')&&response.request().method()==='POST'&&matches(response.request().postDataJSON().design));
}

for(const mode of ['dynamic','static'] as const){
test(`clearing labels and frame text supports all frames, logos, and ${mode} QR creation`,async({page})=>{
  const failures:number[]=[];
  page.on('response',response=>{if(response.url().includes('/api/qr/preview?')&&response.status()>=400)failures.push(response.status());});
  await page.goto('/register');await page.getByLabel('Full name').fill('Frame Review');await page.getByLabel('Email address').fill(`frame-${mode}-${Date.now()}@example.com`);await page.getByLabel('Password',{exact:true}).fill('FrameReview123!');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Create account',exact:true}).click();await expect(page).toHaveURL(/\/app$/);
  await page.goto('/app/create');await page.getByLabel('Code name').fill('Optional text '+mode);await page.getByLabel('Website address').fill('https://example.com/optional-text');
  if(mode==='static')await page.getByRole('radio',{name:/Static QR code/}).check();
  await page.getByRole('tab',{name:/Design/}).click();
  await page.getByLabel('Text above the code',{exact:true}).fill('Welcome');await page.getByLabel('Text above the code',{exact:true}).fill('');
  await page.getByRole('group',{name:'Choose a text label'}).getByRole('button',{name:/Text below the code/}).click();await page.getByLabel('Text below the code',{exact:true}).fill('Visit us');await page.getByLabel('Text below the code',{exact:true}).fill('');
  await page.getByRole('button',{name:'Filled callout',exact:true}).click();await page.getByLabel('Frame callout',{exact:true}).fill('');await expect(page.getByLabel('Frame callout',{exact:true})).toHaveValue('');
  for(const [frame,label] of [['none','No frame'],['banner','Outline callout'],['border','Rounded border'],['scan','Filled callout']]){
   const pending=nextPreview(page,design=>design.frame===frame&&design.frame_label==='');await page.getByRole('button',{name:label,exact:true}).click();expect((await pending).status()).toBe(200);await expect(page.getByRole('alert')).toHaveCount(0);
  }
  const pending=nextPreview(page,design=>Boolean(design.logo)&&design.frame_label==='');await page.getByLabel('Upload logo',{exact:true}).setInputFiles('tests/fixtures/card-photo.png');expect((await pending).status()).toBe(200);await expect(page.getByAltText('Your logo',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Create QR code',exact:true}).click();await expect(page).toHaveURL(/\/app\/codes\/[a-f0-9-]+$/);
  const code=await(await page.request.get('/api/codes/'+page.url().split('/').pop())).json();expect(code.mode).toBe(mode);expect(code.design.frame_label).toBe('');expect(code.design.top_text).toBe('');expect(code.design.bottom_text).toBe('');expect(code.design.logo).toContain('data:image/png;base64,');
  await page.reload();await page.getByRole('tab',{name:/Design/}).click();await expect(page.getByLabel('Frame callout',{exact:true})).toHaveValue('');await expect(page.getByAltText('Your logo',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Save changes',exact:true}).click();await expect(page.getByText('Your changes have been saved.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Download QR code',exact:true}).click();const dialog=page.getByRole('dialog');const download=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download PNG',exact:true}).click();const bytes=await readFile((await(await download).path())!);expect(bytes.readUInt32BE(16)).toBe(1024);expect(bytes.readUInt32BE(20)).toBe(1024);expect(failures).toEqual([]);
 });
}

test('invalid logos keep the previous design usable and the same image can be uploaded again',async({page})=>{
 await register(page);await page.goto('/app/create');await page.getByLabel('Website address').fill('https://example.com/logo-validation');await page.getByRole('tab',{name:/Design/}).click();
 const upload=page.getByLabel('Upload logo',{exact:true});let pending=nextPreview(page,design=>Boolean(design.logo));await upload.setInputFiles('tests/fixtures/card-photo.png');expect((await pending).status()).toBe(200);const original=await page.getByAltText('Your logo',{exact:true}).getAttribute('src');
 for(const [file,text] of [
  [{name:'logo.svg',mimeType:'image/svg+xml',buffer:Buffer.from('<svg/>')},'Choose a PNG, JPG, or WebP logo.'],
  [{name:'broken.png',mimeType:'image/png',buffer:Buffer.from('broken image')},'This image could not be opened.'],
  [{name:'large.png',mimeType:'image/png',buffer:Buffer.alloc(500001)},'Choose a logo smaller than 500 KB.'],
 ] as const){await upload.setInputFiles(file);await expect(page.getByRole('alert')).toContainText(text);await expect(page.getByAltText('Your logo',{exact:true})).toHaveAttribute('src',original!);}
 for(const [width,height] of [[4,4],[2500,2000]]){
  const data=await page.evaluate(({width,height})=>{const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const context=canvas.getContext('2d')!;context.fillStyle='#2563eb';context.fillRect(0,0,width,height);return canvas.toDataURL('image/png').split(',')[1];},{width,height});
  await upload.setInputFiles({name:'dimensions.png',mimeType:'image/png',buffer:Buffer.from(data,'base64')});await expect(page.getByRole('alert')).toContainText('at least 8 px wide and high, with no more than 4 megapixels');await expect(page.getByAltText('Your logo',{exact:true})).toHaveAttribute('src',original!);
 }
 pending=nextPreview(page,design=>design.logo===null);await page.getByRole('button',{name:'Remove logo',exact:true}).click();expect((await pending).status()).toBe(200);await expect(page.getByRole('alert')).toHaveCount(0);
 pending=nextPreview(page,design=>Boolean(design.logo));await upload.setInputFiles('tests/fixtures/card-photo.png');expect((await pending).status()).toBe(200);await expect(page.getByAltText('Your logo',{exact:true})).toBeVisible();await expect(page.getByRole('alert')).toHaveCount(0);
});
