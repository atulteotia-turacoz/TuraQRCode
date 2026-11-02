import {test,expect,type Page} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {readFile} from 'node:fs/promises';

async function register(page:Page){
 await page.goto('/register');await page.getByLabel('Full name').fill('Taylor Morgan');await page.getByLabel('Email address').fill(`card-tools-${Date.now()}@example.com`);await page.getByLabel('Password',{exact:true}).fill('ReviewPassword123!');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Create account',exact:true}).click();await expect(page).toHaveURL(/\/app$/);
}

test('inline formatting tools, photo crops and rich published profile work without a popup',async({page})=>{
 test.setTimeout(90000);
 await register(page);await page.goto('/app/business-cards');await page.getByRole('button',{name:'Create business card',exact:true}).click();await page.getByLabel('Full name').fill('Taylor Morgan');await page.getByLabel('Job title').fill('Research Director');await page.getByLabel('Company',{exact:true}).fill('Turacoz');await page.getByLabel('Email address').fill('taylor@example.com');
 const bio=page.getByRole('textbox',{name:'About you',exact:true});await bio.fill('Research with purpose');await bio.press('ControlOrMeta+a');
 const tools=page.getByRole('group',{name:'About you formatting',exact:true});
 for(const name of ['Bold','Italic','Underline','Strikethrough'])await tools.getByRole('button',{name,exact:true}).click();
 for(const tag of ['strong','em','u','s'])await expect(bio.locator(tag)).toHaveText('Research with purpose');
 await tools.getByRole('button',{name:'Clear formatting',exact:true}).click();await expect(bio.locator('strong')).toHaveCount(0);
 await tools.getByRole('button',{name:'Undo',exact:true}).click();await expect(bio.locator('strong')).toHaveCount(1);await tools.getByRole('button',{name:'Redo',exact:true}).click();await expect(bio.locator('strong')).toHaveCount(0);
 for(const name of ['Superscript','Subscript','Inline code']){await tools.getByRole('button',{name,exact:true}).click();await expect(tools.getByRole('button',{name,exact:true})).toHaveAttribute('aria-pressed','true');await tools.getByRole('button',{name,exact:true}).click();}
 await tools.getByRole('button',{name:'Bold',exact:true}).click();await tools.getByRole('button',{name:'Bullet list',exact:true}).click();await expect(bio.locator('ul li')).toHaveCount(1);await tools.getByRole('button',{name:'Numbered list',exact:true}).click();await expect(bio.locator('ol li')).toHaveCount(1);await bio.press('End');await bio.press('Enter');await bio.pressSequentially('Second item');await tools.getByRole('button',{name:'Indent list',exact:true}).click();await expect(bio.locator('ol ol')).toHaveCount(1);await tools.getByRole('button',{name:'Outdent list',exact:true}).click();await expect(bio.locator('ol ol')).toHaveCount(0);
 await tools.getByRole('button',{name:'Numbered list',exact:true}).click();await tools.getByRole('button',{name:'Quote',exact:true}).click();await expect(bio.locator('blockquote')).toHaveCount(1);await tools.getByRole('button',{name:'Quote',exact:true}).click();
 await bio.fill('Research with purpose');await bio.press('ControlOrMeta+a');await tools.getByRole('button',{name:'Clear formatting',exact:true}).click();await tools.getByRole('button',{name:'Bold',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
 for(const label of ['Upload profile photo','Upload cover image','Upload company logo'])await page.getByLabel(label,{exact:true}).setInputFiles('tests/fixtures/card-photo.png');
 const logo=page.locator('.card-media-thumbnail.company_logo img');const fitted=await logo.getAttribute('src');await page.getByLabel('Company logo layout',{exact:true}).selectOption('crop');await expect(logo).not.toHaveAttribute('src',fitted!);await page.getByRole('slider',{name:'Company logo zoom',exact:true}).press('End');await page.getByRole('slider',{name:'Company logo horizontal position',exact:true}).press('Home');await page.getByRole('button',{name:'Reset company logo crop',exact:true}).click();await expect(page.getByLabel('Company logo layout',{exact:true})).toHaveValue('fit');
 for(const [slot,width,height] of [['profile_image',512,512],['cover_image',1280,720],['company_logo',512,512]] as const){const image=page.locator('.card-media-thumbnail.'+slot+' img');await image.evaluate(element=>(element as HTMLImageElement).decode());expect(await image.evaluate(element=>[(element as HTMLImageElement).naturalWidth,(element as HTMLImageElement).naturalHeight])).toEqual([width,height]);}
 const portrait=page.locator('.card-media-thumbnail.profile_image img');const before=await portrait.getAttribute('src');await page.getByRole('slider',{name:'Profile photo zoom',exact:true}).press('End');await expect(portrait).not.toHaveAttribute('src',before!);
 await page.getByRole('slider',{name:'Cover image zoom',exact:true}).press('End');await page.getByRole('slider',{name:'Cover image horizontal position',exact:true}).press('End');
 await page.getByRole('button',{name:'Add experience',exact:true}).click();await page.getByLabel('Role',{exact:true}).fill('Director');await page.getByRole('textbox',{name:'Experience highlights',exact:true}).fill('Leading thoughtful research.');
 await page.getByRole('button',{name:'Add a section',exact:true}).click();await page.getByLabel('Section title').fill('Specialties');await page.getByRole('textbox',{name:'Details',exact:true}).fill('Medical communication and strategy.');
 await page.getByRole('button',{name:'Add social profile',exact:true}).click();await page.getByLabel('Social profile URL').fill('taylor-morgan');
 await page.getByRole('button',{name:'Create business card',exact:true}).click();await expect(page.getByRole('heading',{name:'Digital business cards',exact:true})).toBeVisible();
 const card=(await(await page.request.get('/api/cards')).json())[0];expect(card.bio_html).toContain('<strong>');expect(card.social_links[0].url).toBe('https://www.linkedin.com/in/taylor-morgan');
 await page.getByRole('button',{name:'Edit Taylor Morgan',exact:true}).click();await expect(page.getByRole('textbox',{name:'About you'}).locator('strong')).toHaveText('Research with purpose');await page.getByRole('button',{name:'Adjust company logo crop',exact:true}).click();await expect(page.getByRole('slider',{name:'Company logo zoom',exact:true})).toBeVisible();await page.screenshot({path:'tests/screenshots/card-inline-editor.png',fullPage:true});
 const profile=await page.context().newPage();await profile.goto(card.public_url);await expect(profile.getByRole('heading',{name:'Taylor Morgan',exact:true})).toBeVisible();await expect(profile.locator('.profile-rich strong')).toHaveText('Research with purpose');await expect(profile.locator('.profile-panel')).toHaveCount(0);await expect(profile.getByRole('link',{name:'LinkedIn',exact:true})).toHaveAttribute('href','https://www.linkedin.com/in/taylor-morgan');
 const contact=profile.waitForEvent('download');await profile.getByRole('link',{name:'Save contact',exact:true}).click();expect((await readFile((await(await contact).path())!)).toString()).toContain('FN:Taylor Morgan');
 await profile.screenshot({path:'tests/screenshots/card-profile-desktop.png',fullPage:true});
 for(const width of [390,768,1280]){await profile.setViewportSize({width,height:844});expect(await profile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(await profile.locator('.profile-banner').evaluate(element=>Math.abs(element.getBoundingClientRect().width-element.parentElement!.getBoundingClientRect().width)<1)).toBeTruthy();const audit=await new AxeBuilder({page:profile}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();expect(audit.violations.map(item=>item.id)).toEqual([]);}
 await profile.close();
});

test('five-row CSV downloads, creates short links and reports invalid rows',async({page})=>{
 await register(page);await page.goto('/app/bulk');const pending=page.waitForEvent('download');await page.getByRole('link',{name:'Download 5-row CSV example'}).click();const csv=(await readFile((await(await pending).path())!)).toString();expect(csv.trim().split('\n')).toHaveLength(6);
 await page.getByLabel('Upload CSV file').setInputFiles({name:'bulk-5.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});await page.getByLabel('Code type',{exact:true}).selectOption('short');await page.getByRole('button',{name:'Create 5 short links',exact:true}).click();await expect(page.getByText('5 created · 0 need attention',{exact:true})).toBeVisible();
 await page.goto('/app/links');await expect(page.locator('a.name-cell').filter({hasText:'Turacoz website'})).toBeVisible();await page.goto('/app/codes');await expect(page.locator('a.name-cell').filter({hasText:'Turacoz website'})).toHaveCount(0);
 await page.goto('/app/bulk');await page.getByLabel('Or paste CSV content').fill('name,url,alias\nWrong,not-a-url,\nValid,https://example.com,');await page.getByRole('button',{name:'Create 2 QR codes',exact:true}).click();await expect(page.getByText('1 created · 1 need attention',{exact:true})).toBeVisible();
});

test('social QR generator accepts a handle and offers exports for each platform',async({page})=>{
 await register(page);
 for(const [platform,label] of [['YouTube','YouTube URL or handle'],['Instagram','Instagram URL or handle'],['Facebook','Facebook URL or username'],['LinkedIn','LinkedIn URL or username']]){
  await page.goto('/app/create');await page.getByLabel('Code name').fill(platform);await page.getByRole('button',{name:platform,exact:true}).click();await page.getByLabel(label,{exact:true}).fill('@turacoz');await expect(page.getByAltText('Your QR code preview')).toBeVisible();await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByRole('button',{name:'Create QR code',exact:true}).click();await expect(page).toHaveURL(/\/app\/codes\//);await page.getByRole('button',{name:'Download QR code',exact:true}).click();const dialog=page.getByRole('dialog');await dialog.getByLabel('File format').selectOption('svg');const pending=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download SVG',exact:true}).click();const bytes=await readFile((await(await pending).path())!);expect(bytes.toString()).toContain('<svg');
 }
});

test('card image size limits give clear feedback and preserve an existing valid image',async({page})=>{
 await register(page);await page.goto('/app/business-cards');await page.getByRole('button',{name:'Create business card',exact:true}).click();
 for(const [label,minimum] of [['Upload profile photo','128 px wide × 128 px high'],['Upload cover image','320 px wide × 180 px high'],['Upload company logo','64 px wide × 64 px high']]){
  const slot=page.locator('.card-media-slot').filter({has:page.getByLabel(label,{exact:true})});await expect(slot.getByText('Minimum upload: '+minimum,{exact:true})).toBeVisible();await page.getByLabel(label,{exact:true}).setInputFiles('tests/fixtures/card-too-small.png');await expect(page.getByRole('alert')).toContainText('use an image at least');
 }
 const upload=page.getByLabel('Upload profile photo',{exact:true});await upload.setInputFiles('tests/fixtures/card-photo.png');await expect(page.getByRole('alert')).toHaveCount(0);const image=page.locator('.card-media-thumbnail.profile_image img');const valid=await image.getAttribute('src');
 await upload.setInputFiles('tests/fixtures/card-too-small.png');await expect(page.getByRole('alert')).toContainText('128');await expect(image).toHaveAttribute('src',valid!);
 await upload.setInputFiles('tests/fixtures/card-too-wide.png');await expect(page.getByRole('alert')).toContainText('8,000 px per side');await expect(image).toHaveAttribute('src',valid!);
 await upload.setInputFiles({name:'oversized.png',mimeType:'image/png',buffer:Buffer.alloc(8_000_001)});await expect(page.getByRole('alert')).toContainText('smaller than 8 MB');await expect(image).toHaveAttribute('src',valid!);
 await upload.setInputFiles('tests/fixtures/card-photo.png');await expect(page.getByRole('alert')).toHaveCount(0);await page.getByRole('button',{name:'Reset profile photo crop',exact:true}).click();await expect(page.getByRole('slider',{name:'Profile photo zoom',exact:true})).toHaveValue('1');
});
