import {contrast,readableInk} from '../components/DesignColors';
import {useState,type CSSProperties,type FormEvent} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {Plus,FolderOpen,ArrowUpRight,ContactRound,Download,ExternalLink,Trash2,Pencil,Link2,MapPin,Phone,QrCode,Palette} from 'lucide-react';
import {api,post,patch,message,download} from '../shared/api';
import {Button,PageHeader,useResource,Loading,ResourceError,Empty,ErrorBox,Modal,Field,Confirm,CopyButton} from '../shared/ui';
import ExportDialog from '../components/ExportDialog';
import CardMediaFields from '../components/CardMedia';
import RichTextEditor,{RichText} from '../components/RichTextEditor';
import type {CardMedia} from '../components/CardMedia';
import type {Project,Card,CardLink,CardSection,CardExperience,CardSocial} from '../shared/types';

type CardTheme={name:string;color:string;background_end:string|null;text_color:string;accent_color:string;background_angle:number};
const cardThemes:CardTheme[]=[
 {name:'Signature blue',color:'#102a56',background_end:'#2563eb',text_color:'#ffffff',accent_color:'#bfdbfe',background_angle:135},
 {name:'Ocean glass',color:'#082f49',background_end:'#0e7490',text_color:'#ffffff',accent_color:'#a5f3fc',background_angle:135},
 {name:'Cobalt',color:'#172554',background_end:'#1d4ed8',text_color:'#ffffff',accent_color:'#bfdbfe',background_angle:135},
 {name:'Indigo dusk',color:'#312e81',background_end:'#6d28d9',text_color:'#ffffff',accent_color:'#ddd6fe',background_angle:135},
 {name:'Emerald',color:'#052e16',background_end:'#15803d',text_color:'#ffffff',accent_color:'#bbf7d0',background_angle:135},
 {name:'Teal current',color:'#042f2e',background_end:'#0f766e',text_color:'#ffffff',accent_color:'#99f6e4',background_angle:135},
 {name:'Plum',color:'#3b0764',background_end:'#86198f',text_color:'#ffffff',accent_color:'#f5d0fe',background_angle:135},
 {name:'Rosewood',color:'#4c0519',background_end:'#be123c',text_color:'#ffffff',accent_color:'#fecdd3',background_angle:135},
 {name:'Charcoal',color:'#111827',background_end:'#334155',text_color:'#ffffff',accent_color:'#cbd5e1',background_angle:135},
 {name:'Midnight',color:'#020617',background_end:'#1e293b',text_color:'#ffffff',accent_color:'#93c5fd',background_angle:135},
 {name:'Sunset',color:'#7c2d12',background_end:'#c2410c',text_color:'#ffffff',accent_color:'#fed7aa',background_angle:135},
 {name:'Copper',color:'#431407',background_end:'#9a3412',text_color:'#ffffff',accent_color:'#fdba74',background_angle:135},
 {name:'Sky',color:'#eff6ff',background_end:'#dbeafe',text_color:'#0f172a',accent_color:'#1d4ed8',background_angle:135},
 {name:'Cloud',color:'#f8fafc',background_end:'#e2e8f0',text_color:'#0f172a',accent_color:'#334155',background_angle:135},
 {name:'Lavender',color:'#faf5ff',background_end:'#ede9fe',text_color:'#312e81',accent_color:'#6d28d9',background_angle:135},
 {name:'Mint',color:'#ecfdf5',background_end:'#d1fae5',text_color:'#064e3b',accent_color:'#047857',background_angle:135},
 {name:'Warm sand',color:'#fffbeb',background_end:'#fef3c7',text_color:'#451a03',accent_color:'#92400e',background_angle:135},
 {name:'Rose quartz',color:'#fff1f2',background_end:'#fce7f3',text_color:'#881337',accent_color:'#be123c',background_angle:135},
 {name:'Cool horizon',color:'#f0f9ff',background_end:'#e0f2fe',text_color:'#0c4a6e',accent_color:'#0369a1',background_angle:45},
 {name:'Olive leaf',color:'#365314',background_end:'#4d7c0f',text_color:'#ffffff',accent_color:'#d9f99d',background_angle:135},
];
const cardBackground=(card:Pick<Card,'color'|'background_end'|'background_angle'>)=>card.background_end?`linear-gradient(${card.background_angle||135}deg, ${card.color}, ${card.background_end})`:card.color;
const cardInk=(card:Pick<Card,'color'|'text_color'>)=>card.text_color||readableInk(card.color);

export function ProjectsPage(){const r=useResource<Project[]>('/api/projects');const [editing,setEditing]=useState<Project|'new'|null>(null);const [deleting,setDeleting]=useState<Project|null>(null);return <><PageHeader title="Projects" description="Give every campaign a place to belong." action={<Button onClick={()=>setEditing('new')}><Plus size={17}/>New project</Button>}/>{r.error?<ResourceError error={r.error} retry={r.reload}/>:r.loading?<Loading/>:r.data?.length?<div className="projects-grid">{r.data.map(p=><article className="panel project-card" key={p.id}><div className="project-card-top"><span className="folder-icon" style={{color:p.color,background:p.color+'12'}}><FolderOpen size={25}/></span><div><button className="icon-button" aria-label={'Rename '+p.name} onClick={()=>setEditing(p)}><Pencil size={15}/></button>{!p.is_default&&<button className="icon-button" aria-label={'Delete '+p.name} onClick={()=>setDeleting(p)}><Trash2 size={15}/></button>}</div></div><h2>{p.name}</h2>{p.is_default&&<span className="badge">Default project</span>}<p>{p.total_codes} {p.total_codes===1?'connection':'connections'}</p><div className="inline-actions project-category-links"><Link to={'/app/codes?project='+p.id} className="text-link">QR codes<ArrowUpRight size={16}/></Link><Link to={'/app/links?project='+p.id} className="text-link">Link shortener<ArrowUpRight size={16}/></Link><Link to={'/app/barcodes?project='+p.id} className="text-link">Barcodes<ArrowUpRight size={16}/></Link></div></article>)}</div>:<section className="panel"><Empty icon={<FolderOpen size={26}/>} heading="A home for your next campaign" action={<Button onClick={()=>setEditing('new')}><Plus size={16}/>Create a project</Button>}>Group related codes and short links so your work stays beautifully organized.</Empty></section>}{editing&&<ProjectEditor project={editing==='new'?undefined:editing} onClose={()=>setEditing(null)} onDone={()=>{setEditing(null);r.reload();}}/>}{deleting&&<Confirm title="Delete this project?" onClose={()=>setDeleting(null)} onConfirm={async()=>{await api('/api/projects/'+deleting.id,{method:'DELETE'});r.reload();}}>“{deleting.name}” will be removed. Its codes and links will move to your default project.</Confirm>}</>;}
function ProjectEditor({project,onClose,onDone}:{project?:Project;onClose:()=>void;onDone:()=>void}){const [error,setError]=useState('');const [busy,setBusy]=useState(false);async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);const f=new FormData(e.currentTarget);try{const data={name:f.get('name'),color:f.get('color')};if(project)await patch('/api/projects/'+project.id,data);else await post('/api/projects',data);onDone();}catch(e){setError(message(e));}finally{setBusy(false);}}return <Modal title={project?'Edit project':'Create a project'} onClose={onClose}><form onSubmit={submit}><ErrorBox error={error}/><Field label="Project name"><input name="name" defaultValue={project?.name} required maxLength={100} autoFocus placeholder="e.g. Autumn campaign"/></Field><Field label="Project color"><input name="color" type="color" defaultValue={project?.color||'#2563eb'}/></Field><div className="modal-actions"><Button type="button" className="secondary" onClick={onClose}>Cancel</Button><Button busy={busy}>{project?'Save changes':'Create project'}</Button></div></form></Modal>;}

export function CardsPage(){
 const r=useResource<Card[]>('/api/cards',true);
 const [editing,setEditing]=useState<Card|'new'|null>(null);
 const [deleting,setDeleting]=useState<Card|null>(null);
 const [error,setError]=useState('');
 const [creatingQr,setCreatingQr]=useState<string|null>(null);
 const [exportCard,setExportCard]=useState<Card|null>(null);
 const navigate=useNavigate();
 async function createQr(card:Card){
  setCreatingQr(card.id);setError('');
  try{const result=await post<{qr_code_url:string}>('/api/cards/'+card.id+'/qr-code',{});navigate(result.qr_code_url);}
  catch(exception){setError(message(exception));}
  finally{setCreatingQr(null);}
 }
 if(editing)return <CardEditor card={editing==='new'?undefined:editing} onClose={()=>setEditing(null)} onDone={()=>{setEditing(null);r.reload();}}/>;
 return <>
  <PageHeader title="Digital business cards" description="Share your contact details, work, and professional profile with one scan." action={<Button onClick={()=>setEditing('new')}><Plus size={17}/>Create business card</Button>}/>
  <ErrorBox error={error}/>
  {r.error?<ResourceError error={r.error} retry={r.reload}/>:r.loading?<Loading/>:r.data?.length?
   <div className="cards-grid">{r.data.map(card=><article key={card.id} className="business-card-panel">
    <div className="business-card-preview" style={{background:cardBackground(card),color:cardInk(card),'--card-accent':card.accent_color||'#bfdbfe'} as CSSProperties}>
     <div className="card-preview-top"><span className="card-wordmark">{'TURAQRCODE \u00b7 DIGITAL CARD'}</span><span className="card-link-count"><Link2 size={13}/>{card.links?.length||0} links</span></div>
     <span className="card-monogram">{card.profile_image?<img src={card.profile_image} alt="Profile photo"/>:card.name.split(' ').filter(Boolean).slice(0,2).map(part=>part[0]).join('').toUpperCase()}</span>
     <h2>{card.name}</h2><p>{[card.title,card.company].filter(Boolean).join(' \u00b7 ')||'Your professional profile'}</p>
    </div>
    <div className="business-card-content">
     <div className="business-card-contact"><span>{card.email||card.phone||card.website||'Add contact details to your profile'}</span>{card.address&&<small><MapPin size={13}/>{card.address}</small>}</div>
     <div className="business-card-actions">
      <a className="button secondary small" href={card.public_url} target="_blank" rel="noreferrer"><ExternalLink size={14}/>View card</a>
      {card.qr_code_id?<Link className="button small" to={'/app/codes/'+card.qr_code_id}><QrCode size={14}/>Customize QR code</Link>:<Button className="small" busy={creatingQr===card.id} onClick={()=>createQr(card)}><QrCode size={14}/>Create QR code</Button>}
      <Button className="secondary small" onClick={()=>setExportCard(card)}><Download size={14}/>Download QR</Button>
     </div>
     <div className="business-card-footer"><CopyButton value={card.public_url} label="Copy profile link"/><div><button className="icon-button" aria-label={'Edit '+card.name} onClick={()=>setEditing(card)}><Pencil size={15}/></button><button className="icon-button" aria-label={'Delete '+card.name} onClick={()=>setDeleting(card)}><Trash2 size={15}/></button></div></div>
    </div>
   </article>)}</div>
   :<section className="panel"><Empty icon={<ContactRound size={27}/>} heading="Your next introduction, reimagined" action={<Button onClick={()=>setEditing('new')}><Plus size={16}/>Create your business card</Button>}>Add your contact details, a short introduction, and links to your work. We will prepare a matching QR code in your default project.</Empty></section>}
  {exportCard&&<ExportDialog title={`Download ${exportCard.name}'s QR code`} onClose={()=>setExportCard(null)} onExport={async options=>{const query=new URLSearchParams({format:options.format,size:String(options.widthPx),print_preset:options.size});await download('/api/cards/'+exportCard.id+'/qr?'+query,'digital-business-card-qr.'+options.format);}}/>}
  {deleting&&<Confirm title="Delete this business card?" onClose={()=>setDeleting(null)} onConfirm={async()=>{await api('/api/cards/'+deleting.id,{method:'DELETE'});r.reload();}}>{`\u201c${deleting.name}\u201d and its public profile and linked QR code will be removed.`}</Confirm>}
 </>;
}

function CardEditor({card,onClose,onDone}:{card?:Card;onClose:()=>void;onDone:()=>void}){
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const [uploading,setUploading]=useState(false);
 const [bioHTML,setBioHTML]=useState(card?.bio_html||'');
 const [media,setMedia]=useState<CardMedia>({profile_image:card?.profile_image||null,cover_image:card?.cover_image||null,company_logo:card?.company_logo||null});
 const [experience,setExperience]=useState<CardExperience[]>(card?.experience||[]);
 const [socials,setSocials]=useState<CardSocial[]>(card?.social_links||[]);
 const [links,setLinks]=useState<CardLink[]>(card?.links||[]);const [sections,setSections]=useState<CardSection[]>(card?.sections||[]);
 const [draft,setDraft]=useState<Record<string,string>>(()=>Object.fromEntries(['name','title','company','email','phone','website','bio','address'].map(key=>[key,String(card?.[key as keyof Card]||'')])));
 const [theme,setTheme]=useState<CardTheme>(()=>card?{name:'Custom',color:card.color,background_end:card.background_end,text_color:card.text_color||readableInk(card.color),accent_color:card.accent_color||'#bfdbfe',background_angle:card.background_angle||135}:cardThemes[0]);
 const backgrounds=[theme.color,...(theme.background_end?[theme.background_end]:[])];
 const textReadable=backgrounds.every(background=>contrast(theme.text_color,background)>=4.5);
 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setError('');if(sections.some(section=>!section.body.trim())){setError('Add details to each profile section, or remove the empty section.');return;}if(!textReadable){setError('Choose a text color with strong contrast across the full background.');return;}setBusy(true);
  const values:Record<string,unknown>=Object.fromEntries(new FormData(event.currentTarget).entries());
  Object.assign(values,media,{bio:draft.bio,bio_html:bioHTML,experience,social_links:socials});
  values.links=links.filter(link=>link.label.trim()&&link.url.trim()).map(link=>({label:link.label.trim(),url:link.url.trim()}));
  values.sections=sections.filter(section=>section.title.trim()&&section.body.trim()).map(section=>({title:section.title.trim(),body:section.body.trim(),body_html:section.body_html||''}));
  values.color=theme.color;values.background_end=theme.background_end;values.background_angle=theme.background_angle;values.text_color=theme.text_color;values.accent_color=theme.accent_color;
  try{if(card)await patch('/api/cards/'+card.id,values);else await post('/api/cards',values);onDone();}catch(exception){setError(message(exception));}finally{setBusy(false);}
 }
 function editLink(index:number,key:keyof CardLink,value:string){setLinks(current=>current.map((link,i)=>i===index?{...link,[key]:value}:link));}
 function editSection(index:number,key:keyof CardSection,value:string){setSections(current=>current.map((section,i)=>i===index?{...section,[key]:value}:section));}
 const initials=draft.name.trim().split(/\s+/).filter(Boolean).slice(0,2).map(word=>word[0]).join('').toUpperCase()||'YN';
 const role=[draft.title,draft.company].filter(Boolean).join(' · ');
 const themeStyle={background:theme.background_end?`linear-gradient(${theme.background_angle}deg, ${theme.color}, ${theme.background_end})`:theme.color,color:theme.text_color,'--card-accent':theme.accent_color} as CSSProperties;
 return <div className="card-studio-page">
  <div className="card-studio-header"><div><button className="text-link" type="button" onClick={onClose}>← Back to business cards</button><h1>{card?'Edit your digital card':'Create a digital business card'}</h1><p>Build a professional profile with a QR code and a shareable address.</p></div><span className="badge">Live preview</span></div>
  <div className="card-studio-layout">
   <aside className="card-studio-preview"><div className="card-studio-preview-head"><span>PUBLIC CARD PREVIEW</span><span>Updates as you edit</span></div><div className="card-live-card">
    <header className="card-live-hero"><div className="card-live-banner" style={themeStyle}>{media.cover_image&&<img className="card-live-cover" src={media.cover_image} alt="Profile cover"/>}<span className="card-live-brand">TURAQRCODE · DIGITAL CARD</span>{media.company_logo&&<img className="card-live-company-logo" src={media.company_logo} alt="Company logo"/>}</div><div className="card-live-identity"><span className="card-live-avatar" style={themeStyle}>{media.profile_image?<img src={media.profile_image} alt="Profile photo"/>:initials}</span><h2>{draft.name||'Your name'}</h2><p>{role||'Job title ? Company'}</p></div></header>
    <div className="card-live-content"><RichText text={draft.bio||'Add a short introduction about your work, focus, or experience.'} html={bioHTML}/>
     {(draft.email||draft.phone||draft.website||draft.address)&&<div className="card-live-contact">{draft.email&&<span>✉ {draft.email}</span>}{draft.phone&&<span>☎ {draft.phone}</span>}{draft.website&&<span>↗ {draft.website}</span>}{draft.address&&<span>⌖ {draft.address}</span>}</div>}
     {sections.filter(section=>section.title||section.body).map((section,index)=><section className="card-live-section" key={index}><strong>{section.title||'Profile section'}</strong><RichText text={section.body} html={section.body_html}/></section>)}
     {experience.length>0&&<section className="card-live-section"><strong>Professional experience</strong>{experience.map((item,index)=><article className="card-live-experience" key={index}><b>{item.role||'Role'}</b><small>{[item.organization,item.period].filter(Boolean).join(' · ')}</small><RichText text={item.description} html={item.description_html}/></article>)}</section>}
     {socials.length>0&&<div className="card-live-links">{socials.map((social,index)=><span key={index}>{social.platform} ↗</span>)}</div>}
     {links.filter(link=>link.label||link.url).length>0&&<div className="card-live-links">{links.filter(link=>link.label||link.url).map((link,index)=><span key={index}>{link.label||'Profile link'} ↗</span>)}</div>}
    </div></div><p className="card-studio-preview-note">Your profile address is public. Include only details you want to share.</p></aside>
   <form id="card-studio-form" className="card-studio-form" onSubmit={submit}>
    <ErrorBox error={error}/>
    <section className="card-form-section"><div className="card-form-heading"><span><ContactRound size={17}/></span><div><h2>Card details</h2><p>Name and public address for your digital card.</p></div></div>
     <Field label="Full name"><input name="name" value={draft.name} onChange={event=>setDraft({...draft,name:event.target.value})} required minLength={2} maxLength={100} autoFocus placeholder="e.g. Alex Rivera"/></Field>
     <Field label="Public address" hint="This address stays with your card and QR code."><input value={card?.public_url||'Created when you save this card'} readOnly aria-label="Public card address"/></Field>
    </section>
    <section className="card-form-section"><div className="card-form-heading"><span><ContactRound size={17}/></span><div><h2>Professional profile</h2><p>Add your role, organization, and a concise introduction.</p></div></div>
     <div className="field-grid"><Field label="Job title"><input name="title" value={draft.title} onChange={event=>setDraft({...draft,title:event.target.value})} maxLength={120} placeholder="e.g. Product designer"/></Field><Field label="Company"><input name="company" value={draft.company} onChange={event=>setDraft({...draft,company:event.target.value})} maxLength={120} placeholder="Organization or practice"/></Field></div>
     <RichTextEditor label="About you" text={draft.bio} html={bioHTML} limit={2000} placeholder="Describe your work, experience, or focus." onChange={(text,html)=>{setDraft(current=>({...current,bio:text}));setBioHTML(html);}}/>
    </section>
    <section className="card-form-section"><div className="card-form-heading"><span><ContactRound size={17}/></span><div><h2>Photos & branding</h2><p>Add a profile photo, a landscape cover, and your logo. PNG, JPG, or WebP, up to 8 MB each. Use the inline controls to adjust the crop.</p></div></div><CardMediaFields value={media} onChange={setMedia} onBusy={setUploading} onError={setError}/></section>
    <section className="card-form-section"><div className="card-form-heading"><span><ContactRound size={17}/></span><div><h2>Professional experience</h2><p>Share relevant roles, organizations, dates, and highlights.</p></div></div>
     {experience.map((item,index)=><fieldset className="card-profile-section-editor" key={index}><legend>Experience {index+1}</legend><Field label="Role"><input value={item.role} required minLength={2} maxLength={120} onChange={event=>setExperience(current=>current.map((entry,i)=>i===index?{...entry,role:event.target.value}:entry))}/></Field><div className="field-grid"><Field label="Organization"><input value={item.organization} maxLength={120} onChange={event=>setExperience(current=>current.map((entry,i)=>i===index?{...entry,organization:event.target.value}:entry))}/></Field><Field label="Period"><input value={item.period} maxLength={80} placeholder="e.g. 2022 – Present" onChange={event=>setExperience(current=>current.map((entry,i)=>i===index?{...entry,period:event.target.value}:entry))}/></Field></div><RichTextEditor label="Experience highlights" text={item.description} html={item.description_html} limit={1000} onChange={(text,html)=>setExperience(current=>current.map((entry,i)=>i===index?{...entry,description:text,description_html:html}:entry))}/><button type="button" className="text-link" onClick={()=>setExperience(current=>current.filter((_,i)=>i!==index))}>Remove experience</button></fieldset>)}
     {experience.length<12&&<button type="button" className="button secondary small" onClick={()=>setExperience(current=>[...current,{role:'',organization:'',period:'',description:''}])}><Plus size={14}/>Add experience</button>}
    </section>
    <section className="card-form-section"><div className="card-form-heading"><span><Link2 size={17}/></span><div><h2>Social profiles</h2><p>Give visitors a direct link to your professional and social accounts.</p></div></div>
     {socials.map((item,index)=><div className="card-link-editor-row" key={index}><Field label="Platform"><select value={item.platform} onChange={event=>setSocials(current=>current.map((entry,i)=>i===index?{...entry,platform:event.target.value}:entry))}>{['linkedin','instagram','facebook','x','youtube','tiktok','github','pinterest','whatsapp','telegram'].map(platform=><option key={platform} value={platform} disabled={socials.some((entry,i)=>i!==index&&entry.platform===platform)}>{platform==='linkedin'?'LinkedIn':platform==='youtube'?'YouTube':platform==='github'?'GitHub':platform==='x'?'X':platform[0].toUpperCase()+platform.slice(1)}</option>)}</select></Field><Field label="Social profile URL" hint="Enter a profile URL or account handle. For WhatsApp, include the country code."><input type="text" required value={item.url} placeholder="@your-handle or https://?" maxLength={2048} onChange={event=>setSocials(current=>current.map((entry,i)=>i===index?{...entry,url:event.target.value}:entry))}/></Field><button className="icon-button" type="button" aria-label={'Remove '+item.platform+' profile'} onClick={()=>setSocials(current=>current.filter((_,i)=>i!==index))}><Trash2 size={16}/></button></div>)}
     {socials.length<10&&<button type="button" className="button secondary small" onClick={()=>{const platform=['linkedin','instagram','facebook','x','youtube','tiktok','github','pinterest','whatsapp','telegram'].find(platform=>!socials.some(item=>item.platform===platform));if(platform)setSocials(current=>[...current,{platform,url:''}]);}}><Plus size={14}/>Add social profile</button>}
    </section>
    <section className="card-form-section"><div className="card-form-heading"><span><Phone size={17}/></span><div><h2>Contact & location</h2><p>Share the contact information people should use.</p></div></div>
     <div className="field-grid"><Field label="Email address"><input name="email" type="email" value={draft.email} onChange={event=>setDraft({...draft,email:event.target.value})} maxLength={254} placeholder="alex@company.com"/></Field><Field label="Phone number"><input name="phone" type="tel" value={draft.phone} onChange={event=>setDraft({...draft,phone:event.target.value})} maxLength={30} placeholder="+1 555 010 2030"/></Field></div>
     <Field label="Website"><input name="website" type="url" value={draft.website} onChange={event=>setDraft({...draft,website:event.target.value})} placeholder="https://company.com" maxLength={2048}/></Field>
     <Field label="Location"><input name="address" value={draft.address} onChange={event=>setDraft({...draft,address:event.target.value})} maxLength={300} placeholder="City, region, country"/></Field>
    </section>
    <section className="card-form-section"><div className="card-form-heading"><span><Link2 size={17}/></span><div><h2>Links to your work</h2><p>Add a portfolio, social profile, booking page, or other resource.</p></div></div>
     {links.map((link,index)=><div className="card-link-editor-row" key={index}><Field label="Link name"><input required minLength={2} value={link.label} onChange={event=>editLink(index,'label',event.target.value)} maxLength={40} placeholder="e.g. LinkedIn"/></Field><Field label="Link address"><input required value={link.url} type="url" onChange={event=>editLink(index,'url',event.target.value)} maxLength={2048} placeholder="https://linkedin.com/in/your-name"/></Field><button className="icon-button" type="button" aria-label={'Remove profile link '+(link.label||index+1)} onClick={()=>setLinks(current=>current.filter((_,i)=>i!==index))}><Trash2 size={16}/></button></div>)}
     {links.length<8&&<button className="button secondary small card-add-link" type="button" onClick={()=>setLinks(current=>[...current,{label:'',url:''}])}><Plus size={14}/>Add a link</button>}
    </section>
    <section className="card-form-section"><div className="card-form-heading"><span><ContactRound size={17}/></span><div><h2>Profile sections</h2><p>Include credentials, services, specialties, achievements, or selected work.</p></div></div>
     {sections.map((section,index)=><div className="card-profile-section-editor" key={index}><Field label="Section title"><input required minLength={2} value={section.title} onChange={event=>editSection(index,'title',event.target.value)} maxLength={60} placeholder="e.g. Areas of expertise"/></Field><RichTextEditor label="Details" required text={section.body} html={section.body_html} limit={1500} placeholder="Add credentials, specialties, services, or highlights." onChange={(text,html)=>setSections(current=>current.map((entry,i)=>i===index?{...entry,body:text,body_html:html}:entry))}/><button className="text-link" type="button" onClick={()=>setSections(current=>current.filter((_,i)=>i!==index))}>Remove section</button></div>)}
     {sections.length<10&&<button className="button secondary small card-add-link" type="button" onClick={()=>setSections(current=>[...current,{title:'',body:''}])}><Plus size={14}/>Add a section</button>}
    </section>
    <section className="card-form-section"><div className="card-form-heading"><span><Palette size={17}/></span><div><h2>Card appearance</h2><p>Select a palette, then adjust the colors to match your brand.</p></div></div>
     <div className="card-theme-grid" role="group" aria-label="Business card color palettes">{cardThemes.map(preset=><button type="button" key={preset.name} aria-pressed={theme.name===preset.name} aria-label={'Apply '+preset.name+' palette'} onClick={()=>setTheme(preset)} style={{background:preset.background_end?`linear-gradient(${preset.background_angle}deg, ${preset.color}, ${preset.background_end})`:preset.color,color:preset.text_color}}><span>{preset.name}</span><i style={{background:preset.accent_color}}/></button>)}</div>
     <div className="field-grid"><Field label="Background color"><div className="color-field"><input type="color" value={theme.color} onChange={event=>setTheme({...theme,name:'Custom',color:event.target.value})}/><span>{theme.color.toUpperCase()}</span></div></Field><Field label="Background style"><select value={theme.background_end?'gradient':'solid'} onChange={event=>setTheme({...theme,name:'Custom',background_end:event.target.value==='gradient'?(theme.background_end||theme.color):null})}><option value="solid">Solid color</option><option value="gradient">Two-color gradient</option></select></Field></div>
     {theme.background_end&&<div className="field-grid"><Field label="Second background color"><div className="color-field"><input type="color" value={theme.background_end} onChange={event=>setTheme({...theme,name:'Custom',background_end:event.target.value})}/><span>{theme.background_end.toUpperCase()}</span></div></Field><Field label="Gradient direction"><select value={theme.background_angle} onChange={event=>setTheme({...theme,name:'Custom',background_angle:Number(event.target.value)})}><option value="0">Horizontal</option><option value="45">Diagonal</option><option value="90">Vertical</option><option value="135">Diagonal · reverse</option><option value="180">Horizontal · reverse</option></select></Field></div>}
     <div className="field-grid"><Field label="Text color"><div className="color-field"><input type="color" value={theme.text_color} onChange={event=>setTheme({...theme,name:'Custom',text_color:event.target.value})}/><span>{theme.text_color.toUpperCase()}</span></div></Field><Field label="Accent color"><div className="color-field"><input type="color" value={theme.accent_color} onChange={event=>setTheme({...theme,name:'Custom',accent_color:event.target.value})}/><span>{theme.accent_color.toUpperCase()}</span></div></Field></div>
     {!textReadable&&<p className="notice warning">This text color is hard to read on the selected background. Choose a darker or lighter text color before saving.</p>}
    </section>
    <div className="card-studio-actions"><Button type="button" className="secondary" onClick={onClose}>Cancel</Button><Button busy={busy} disabled={uploading}>{card?'Save changes':'Create business card'}</Button></div>
   </form>
  </div>
 </div>;
}
