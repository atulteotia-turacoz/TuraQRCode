import {useState,type FormEvent} from 'react';
import {CreditCard,Pencil,Plus,Trash2} from 'lucide-react';
import {Button,Confirm,Empty,ErrorBox,Field,Loading,Modal,PageHeader,ResourceError,useResource} from '../shared/ui';
import {message,patch,post,remove} from '../shared/api';

export type AdminPlan={id:string;name:string;description:string;price_monthly:number;price_yearly:number;currency:string;max_codes:number|null;max_cards:number|null;max_projects:number|null;features:string[];is_active:boolean;is_featured:boolean;sort_order:number;subscribers:number};
const blank:Omit<AdminPlan,'id'|'subscribers'>={name:'',description:'',price_monthly:0,price_yearly:0,currency:'INR',max_codes:null,max_cards:null,max_projects:null,features:[],is_active:true,is_featured:false,sort_order:0};
const currencies=['INR','USD','EUR','GBP','AED','SGD'];
const price=(amount:number,currency:string)=>amount?new Intl.NumberFormat(undefined,{style:'currency',currency}).format(amount/100):'Free';
const toMinor=(value:FormDataEntryValue|null)=>Math.round(Number(value||0)*100);
const limit=(value:FormDataEntryValue|null)=>value===''||value===null?null:Number(value);
const payload=(plan:Pick<AdminPlan,keyof typeof blank>)=>Object.fromEntries((Object.keys(blank) as (keyof typeof blank)[]).map(key=>[key,plan[key]]));

function PlanForm({plan,onDone,onClose}:{plan:AdminPlan|null;onDone:()=>void;onClose:()=>void}){
 const value=plan||blank;const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError('');const f=new FormData(event.currentTarget);const body={name:f.get('name'),description:f.get('description'),price_monthly:toMinor(f.get('price_monthly')),price_yearly:toMinor(f.get('price_yearly')),currency:f.get('currency'),max_codes:limit(f.get('max_codes')),max_cards:limit(f.get('max_cards')),max_projects:limit(f.get('max_projects')),features:String(f.get('features')).split('\n'),is_active:f.get('is_active')==='on',is_featured:f.get('is_featured')==='on',sort_order:Number(f.get('sort_order')||0)};try{if(plan)await patch('/api/admin/plans/'+plan.id,body);else await post('/api/admin/plans',body);onDone();onClose();}catch(e){setError(message(e));}finally{setBusy(false);}}
 return <Modal title={plan?'Edit plan':'Add plan'} onClose={onClose}><form onSubmit={submit}><ErrorBox error={error}/><div className="form-grid">
  <div className="wide"><Field label="Plan name"><input name="name" required minLength={2} maxLength={80} defaultValue={value.name}/></Field></div>
  <div className="wide"><Field label="Short description"><input name="description" maxLength={240} defaultValue={value.description}/></Field></div>
  <Field label="Monthly price" hint="Use 0 for a free plan."><input name="price_monthly" type="number" min="0" step="0.01" required defaultValue={value.price_monthly/100}/></Field>
  <Field label="Yearly price"><input name="price_yearly" type="number" min="0" step="0.01" required defaultValue={value.price_yearly/100}/></Field>
  <Field label="Currency"><select name="currency" defaultValue={value.currency}>{currencies.map(c=><option key={c}>{c}</option>)}</select></Field>
  <Field label="Display order"><input name="sort_order" type="number" min="0" max="9999" defaultValue={value.sort_order}/></Field>
  <Field label="Codes and links limit" hint="Leave blank for unlimited."><input name="max_codes" type="number" min="0" defaultValue={value.max_codes??''}/></Field>
  <Field label="Business cards limit" hint="Leave blank for unlimited."><input name="max_cards" type="number" min="0" defaultValue={value.max_cards??''}/></Field>
  <Field label="Projects limit" hint="Leave blank for unlimited."><input name="max_projects" type="number" min="0" defaultValue={value.max_projects??''}/></Field>
  <div className="wide"><Field label="Features" hint="One per line. Shown on the plan card."><textarea name="features" rows={4} defaultValue={value.features.join('\n')}/></Field></div>
 </div><div className="form-actions"><label className="toggle"><input name="is_active" type="checkbox" defaultChecked={value.is_active}/><i/>Enabled</label><label className="toggle"><input name="is_featured" type="checkbox" defaultChecked={value.is_featured}/><i/>Highlight as popular</label></div><div className="form-actions"><Button busy={busy}>{plan?'Save plan':'Add plan'}</Button><Button type="button" className="secondary" onClick={onClose}>Cancel</Button></div></form></Modal>;
}

export default function PlansPage(){
 const saas=useResource<{enabled:boolean}>('/api/admin/saas');const r=useResource<{items:AdminPlan[]}>('/api/admin/plans');const [editing,setEditing]=useState<AdminPlan|null|'new'>(null);const [deleting,setDeleting]=useState<AdminPlan|null>(null);const [error,setError]=useState('');
 async function toggleSaas(enabled:boolean){setError('');try{await patch('/api/admin/saas',{enabled});saas.reload();}catch(e){setError(message(e));}}
 async function togglePlan(plan:AdminPlan){setError('');try{await patch('/api/admin/plans/'+plan.id,{...payload(plan),is_active:!plan.is_active});r.reload();}catch(e){setError(message(e));}}
 return <><PageHeader title="SaaS and plans" description="Turn the SaaS model on or off, and manage the plans customers can choose." action={<Button onClick={()=>setEditing('new')}><Plus size={16}/>Add plan</Button>}/><ErrorBox error={error}/>
 <section className="panel saas-switch"><div><h2>SaaS model</h2><p>{saas.data?.enabled?'On: the website shows plans and sign-up, and plan limits apply.':'Off: the website shows sign in only. Accounts are created by you under Accounts.'}</p></div>{saas.data&&<label className="toggle"><input type="checkbox" checked={saas.data.enabled} onChange={e=>toggleSaas(e.target.checked)}/><i/>{saas.data.enabled?'Enabled':'Disabled'}</label>}</section>
 <section className="panel">{r.error?<ResourceError error={r.error} retry={r.reload}/>:r.loading?<Loading/>:r.data?.items.length?<div className="table-wrap"><table><thead><tr><th>Plan</th><th>Monthly</th><th>Yearly</th><th>Subscribers</th><th>Status</th><th>Actions</th></tr></thead><tbody>{r.data.items.map(plan=><tr key={plan.id}><td><strong>{plan.name}</strong>{plan.is_featured&&<> <span className="badge accent">Popular</span></>}<small className="account-email">{plan.description}</small></td><td className="nowrap">{price(plan.price_monthly,plan.currency)}</td><td className="nowrap">{price(plan.price_yearly,plan.currency)}</td><td>{plan.subscribers}</td><td><span className={'badge dot '+(plan.is_active?'':'paused')}>{plan.is_active?'Enabled':'Disabled'}</span></td><td><div className="cell-actions"><Button className="secondary small" onClick={()=>setEditing(plan)}><Pencil size={13}/>Edit</Button><Button className="secondary small" onClick={()=>togglePlan(plan)}>{plan.is_active?'Disable':'Enable'}</Button><Button className="danger small" aria-label={'Delete '+plan.name} onClick={()=>setDeleting(plan)}><Trash2 size={13}/></Button></div></td></tr>)}</tbody></table></div>:<Empty icon={<CreditCard size={25}/>} heading="No plans yet">Add your first plan. Customers can only sign up once a plan is enabled.</Empty>}</section>
 {editing&&<PlanForm plan={editing==='new'?null:editing} onDone={r.reload} onClose={()=>setEditing(null)}/>}
 {deleting&&<Confirm title={'Delete '+deleting.name+'?'} onClose={()=>setDeleting(null)} onConfirm={async()=>{await remove('/api/admin/plans/'+deleting.id);r.reload();}}>This cannot be undone. A plan with subscribers or payments can only be disabled.</Confirm>}
 </>;
}
