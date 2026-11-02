import {test,expect,type Page} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import QRCode from 'qrcode';

async function enterScanner(page:Page){
 await page.goto('/register');await page.getByLabel('Full name').fill('Scanner Review');await page.getByLabel('Email address').fill(`scanner-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`);await page.getByLabel('Password',{exact:true}).fill('ScannerPassword123!');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Create account',exact:true}).click();await expect(page).toHaveURL(/\/app$/);
 await page.getByRole('navigation').getByRole('link',{name:'QR Scanner',exact:true}).click();await expect(page.getByRole('heading',{name:'QR Scanner',exact:true})).toBeVisible();
}
async function upload(page:Page,text:string,options:QRCode.QRCodeToBufferOptions={}){
 const buffer=await QRCode.toBuffer(text,{width:600,margin:4,...options});
 await page.getByLabel('Image to scan',{exact:true}).setInputFiles({name:'scan.png',mimeType:'image/png',buffer});
 await expect(page.getByLabel('Decoded content',{exact:true})).toHaveText(text);
}
async function canvasCamera(page:Page,buffer:Buffer){
 await page.evaluate(async data=>{
  const target=window as unknown as {scanStreams:MediaStream[];scanCameraCalls:number};target.scanStreams=[];target.scanCameraCalls=0;
  const image=new Image();image.src=data;await image.decode();const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;const context=canvas.getContext('2d')!;context.drawImage(image,0,0);
  setInterval(()=>context.drawImage(image,0,0),100);
  Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>{target.scanCameraCalls++;const stream=canvas.captureStream(10);target.scanStreams.push(stream);return stream;}});
  Object.defineProperty(navigator.mediaDevices,'enumerateDevices',{configurable:true,value:async()=>[{kind:'videoinput',deviceId:'rear',label:'Rear camera'},{kind:'videoinput',deviceId:'front',label:'Front camera'}]});
 },'data:image/png;base64,'+buffer.toString('base64'));
}
async function tracksStopped(page:Page){
 await expect.poll(()=>page.evaluate(()=>(window as unknown as {scanStreams:MediaStream[]}).scanStreams.every(stream=>stream.getTracks().every(track=>track.readyState==='ended')))).toBe(true);
}

test('scanner is last in Manage, reads links/text, copies safely and saves no records',async({page,context})=>{
 await page.goto('/app/scanner');await expect(page).toHaveURL(/\/login$/);await enterScanner(page);
 const navigation=page.getByRole('navigation').locator('.sidebar-group').nth(1);await expect(navigation.getByRole('link').last()).toHaveText('QR Scanner');await expect(navigation.getByRole('link').nth(4)).toHaveText('Bulk & print');
 const before=await(await page.request.get('/api/codes')).json();const writes:string[]=[];page.on('request',request=>{if(request.method()==='POST')writes.push(request.url());});
 await page.getByRole('tab',{name:'Upload image',exact:true}).click();const url='https://example.com/scanner?source=qr';await upload(page,url);await expect(page.getByRole('link',{name:'Open link',exact:true})).toHaveAttribute('href',url);await expect(page).toHaveURL(/\/app\/scanner$/);
 await context.grantPermissions(['clipboard-read','clipboard-write']);await page.getByRole('button',{name:'Copy contents',exact:true}).click();await expect(page.getByRole('button',{name:'Copied',exact:true})).toBeVisible();expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(url);
 await page.getByRole('button',{name:'Scan another',exact:true}).click();await expect(page.getByRole('heading',{name:'Your result appears here',exact:true})).toBeVisible();
 const text='Hello from Turacoz\n<img src=x onerror=alert(1)>';await upload(page,text);await expect(page.getByRole('link',{name:'Open link',exact:true})).toHaveCount(0);await expect(page.getByLabel('Scan result').locator('img')).toHaveCount(0);
 expect(writes).toEqual([]);expect((await(await page.request.get('/api/codes')).json()).total).toBe(before.total);
});

test('image scanner decodes all five generated barcode standards and inverted QR',async({page})=>{
 await enterScanner(page);await page.getByRole('tab',{name:'Upload image',exact:true}).click();
 for(const [format,value,expected] of [['code128','TURA-SCAN-001','TURA-SCAN-001'],['code39','TURA-001','TURA-001'],['ean13','590123412345','5901234123457'],['ean8','9638507','96385074'],['upca','03600029145','036000291452']]){
  const response=await page.request.post('/api/qr/preview?format=png&size=1200',{headers:{Origin:new URL(page.url()).origin},data:{kind:'barcode',content:{format,value,show_text:true}}});expect(response.status()).toBe(200);
  await page.getByLabel('Image to scan',{exact:true}).setInputFiles({name:format+'.png',mimeType:'image/png',buffer:await response.body()});
  await expect(page.getByLabel('Decoded content',{exact:true})).toHaveText(format==='upca'?new RegExp('^0?'+expected+'$'):expected);await expect(page.getByRole('link',{name:'Open link',exact:true})).toHaveCount(0);
 }
 await upload(page,'https://example.com/inverted',{color:{dark:'#ffffffff',light:'#000000ff'}});await expect(page.getByRole('link',{name:'Open link',exact:true})).toBeVisible();
});

test('automatic navigation is opt-in and only accepts HTTP or HTTPS web links',async({page})=>{
 await enterScanner(page);await page.getByRole('tab',{name:'Upload image',exact:true}).click();await page.getByRole('checkbox',{name:/Open web links automatically/}).check();
 for(const text of ['javascript:alert(1)','data:text/html,<script>alert(1)</script>','file:///etc/passwd','//example.com','https://user:password@example.com/','mailto:hello@example.com']){await upload(page,text);await expect(page).toHaveURL(/\/app\/scanner$/);await expect(page.getByRole('link',{name:'Open link',exact:true})).toHaveCount(0);}
 const url='https://example.com/scanner-destination';await page.route(url,route=>route.fulfill({contentType:'text/html',body:'<h1>Scanned destination</h1>'}));
 const buffer=await QRCode.toBuffer(url,{width:500,margin:4});await page.getByLabel('Image to scan',{exact:true}).setInputFiles({name:'destination.png',mimeType:'image/png',buffer});await expect(page).toHaveURL(url);await expect(page.getByRole('heading',{name:'Scanned destination'})).toBeVisible();
});

test('image errors recover without a stuck state and allow the same file again',async({page})=>{
 await enterScanner(page);await page.getByRole('tab',{name:'Upload image',exact:true}).click();const input=page.getByLabel('Image to scan',{exact:true});
 for(const [name,mimeType,buffer,message] of [['wrong.txt','text/plain',Buffer.from('not an image'),'Choose a PNG'],['large.png','image/png',Buffer.alloc(12*1024*1024+1),'smaller than 12 MB'],['corrupt.png','image/png',Buffer.from('invalid image'),'No readable QR code']] as const){await input.setInputFiles({name,mimeType,buffer});await expect(page.getByRole('alert')).toContainText(message);await expect(input).toBeEnabled();}
 const oversized=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=8001;canvas.height=1;return canvas.toDataURL('image/png').split(',')[1];});await input.setInputFiles({name:'wide.png',mimeType:'image/png',buffer:Buffer.from(oversized,'base64')});await expect(page.getByRole('alert')).toContainText('8,000 px');
 const blank=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=100;canvas.height=100;return canvas.toDataURL('image/png').split(',')[1];});await input.setInputFiles({name:'blank.png',mimeType:'image/png',buffer:Buffer.from(blank,'base64')});await expect(page.getByRole('alert')).toContainText('No readable QR code');
 for(let i=0;i<2;i++){await upload(page,'A valid retry');await expect(page.getByRole('alert')).toHaveCount(0);}
});

test('live camera decodes real QR and barcode video frames and releases its tracks',async({page})=>{
 await enterScanner(page);await canvasCamera(page,await QRCode.toBuffer('https://example.com/camera',{width:600,margin:4}));await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByLabel('Decoded content',{exact:true})).toHaveText('https://example.com/camera');await tracksStopped(page);
 const response=await page.request.post('/api/qr/preview?format=png&size=1200',{headers:{Origin:new URL(page.url()).origin},data:{kind:'barcode',content:{format:'code128',value:'CAMERA-001'}}});expect(response.status()).toBe(200);await canvasCamera(page,await response.body());await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByLabel('Decoded content',{exact:true})).toHaveText('CAMERA-001');await tracksStopped(page);
 await canvasCamera(page,await QRCode.toBuffer('Inverted camera QR',{width:600,margin:4,color:{dark:'#ffffffff',light:'#000000ff'}}));await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByLabel('Decoded content',{exact:true})).toHaveText('Inverted camera QR');await tracksStopped(page);
});

test('camera permission, missing-device and busy-camera errors offer image fallback',async({page})=>{
 await enterScanner(page);
 for(const [name,message] of [['NotAllowedError','Camera access was not allowed'],['NotFoundError','No camera was found'],['NotReadableError','camera is unavailable']]){
  await page.evaluate(errorName=>Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>{throw new DOMException('Camera unavailable',errorName);}}),name);
  await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByRole('alert')).toContainText(message);await expect(page.getByRole('button',{name:'Start camera',exact:true})).toBeEnabled();
 }
 await page.getByRole('tab',{name:'Upload image',exact:true}).click();await upload(page,'Camera-free scanning works');await expect(page.getByRole('alert')).toHaveCount(0);
});

test('pending permissions, camera switching, stopping and navigation do not leak streams',async({page})=>{
 await enterScanner(page);
 await page.evaluate(()=>Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:()=>new Promise(resolve=>{(window as unknown as {releaseCapture:(stream:MediaStream)=>void}).releaseCapture=resolve;})}));
 await page.getByRole('button',{name:'Start camera',exact:true}).click();await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.evaluate(()=>{const target=window as unknown as {releaseCapture:(stream:MediaStream)=>void;lateStream:MediaStream};const canvas=document.createElement('canvas');canvas.width=100;canvas.height=100;target.lateStream=canvas.captureStream(5);target.releaseCapture(target.lateStream);});await expect.poll(()=>page.evaluate(()=>(window as unknown as {lateStream:MediaStream}).lateStream.getTracks()[0].readyState)).toBe('ended');
 const blank=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=300;canvas.height=300;return canvas.toDataURL('image/png').split(',')[1];});await canvasCamera(page,Buffer.from(blank,'base64'));
 await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByText('Camera is on',{exact:true})).toBeVisible();await expect(page.getByLabel('Camera',{exact:true})).toBeVisible();await page.getByLabel('Camera',{exact:true}).selectOption('front');await expect.poll(()=>page.evaluate(()=>(window as unknown as {scanCameraCalls:number}).scanCameraCalls)).toBe(2);
 await page.getByRole('button',{name:'Stop camera',exact:true}).click();await tracksStopped(page);
 await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByText('Camera is on',{exact:true})).toBeVisible();await page.getByRole('tab',{name:'Upload image',exact:true}).click();await tracksStopped(page);
 await page.getByRole('tab',{name:'Use camera',exact:true}).click();await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByText('Camera is on',{exact:true})).toBeVisible();await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});await tracksStopped(page);await page.evaluate(()=>Object.defineProperty(document,'hidden',{configurable:true,get:()=>false}));
 await page.getByRole('button',{name:'Start camera',exact:true}).click();await expect(page.getByText('Camera is on',{exact:true})).toBeVisible();await page.getByRole('navigation').getByRole('link',{name:'Link shortener',exact:true}).click();await expect(page).toHaveURL(/\/app\/links$/);await tracksStopped(page);
});

test('scanner supports keyboard tabs, mobile layout and automated accessibility',async({page})=>{
 await enterScanner(page);const camera=page.getByRole('tab',{name:'Use camera',exact:true});await camera.focus();await camera.press('ArrowRight');await expect(page.getByRole('tab',{name:'Upload image',exact:true})).toBeFocused();await page.keyboard.press('Home');await expect(camera).toBeFocused();await page.keyboard.press('End');await expect(page.getByRole('tab',{name:'Upload image',exact:true})).toBeFocused();await upload(page,'https://example.com/accessible');
 for(const width of [1440,390]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();const report=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();expect(report.violations.map(item=>item.id)).toEqual([]);}
});
