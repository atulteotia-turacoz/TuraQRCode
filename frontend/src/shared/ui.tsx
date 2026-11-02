import {useCallback,useEffect,useRef,useState,useId,isValidElement,cloneElement,Children,type Dispatch,type SetStateAction,type ReactNode,type FormEvent,type ReactElement} from 'react';
import {Link,Navigate,useNavigate,useSearchParams} from 'react-router-dom';
import {ArrowRight,ArrowUpRight,Check,AlertCircle,LoaderCircle,X,LockKeyhole,ShieldCheck,Eye,EyeOff} from 'lucide-react';
import {api,message,post} from './api';
import {useAuth} from './auth';
import {ThemeToggle} from './theme';
import {money,useSite} from './site';
import {clearResource,readResource,requestResource,writeResource} from './resourceCache';
import type {User} from './types';

export function Brand({inverse=false}:{inverse?:boolean}){const brand=useSite().site?.landing.brand;return <Link to="/" className={'brand '+(inverse?'inverse':'')} aria-label="TuraQRcode home"><span>{brand?.primary??'Tura'}<span className="brand-accent">{brand?.accent??'QRcode'}</span></span></Link>;}
export function Button({children,busy=false,...props}:React.ButtonHTMLAttributes<HTMLButtonElement>&{busy?:boolean}){return <button {...props} disabled={busy||props.disabled} className={'button '+(props.className||'')}>{busy?<LoaderCircle size={17} className="spin"/>:null}{children}</button>;}
export function ErrorBox({error}:{error?:string|null}){return error?<div className="notice error" role="alert"><AlertCircle size={18}/><span>{error}</span></div>:null;}
export function Success({children}:{children:ReactNode}){return <div className="notice success" role="status"><Check size={18}/><span>{children}</span></div>;}
export function Field({label,children,hint}:{label:string;children:ReactNode;hint?:string}){
 const id=useId();
 function attach(nodes:ReactNode):ReactNode{return Children.map(nodes,node=>{
  if(!isValidElement(node))return node;
  const element=node as ReactElement<Record<string,unknown>>;
  if(typeof element.type!=='string'||['input','textarea','select'].includes(element.type))return cloneElement(element,{id,'aria-describedby':hint?id+'-hint':undefined});
  return cloneElement(element,{},attach(element.props.children as ReactNode));
 });}
 return <div className="field"><label htmlFor={id}>{label}</label>{attach(children)}{hint&&<small id={id+'-hint'}>{hint}</small>}</div>;
}
export function PasswordInput({id,placeholder='Enter your password',...props}:React.InputHTMLAttributes<HTMLInputElement>){const [visible,setVisible]=useState(false);return <span className="password-input"><input {...props} id={id} type={visible?'text':'password'} placeholder={placeholder}/><button type="button" aria-label={visible?'Hide password':'Show password'} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></span>;}
export function Empty({icon,heading,children,action}:{icon:ReactNode;heading:string;children:ReactNode;action?:ReactNode}){return <div className="empty"><span className="empty-icon">{icon}</span><h3>{heading}</h3><p>{children}</p>{action}</div>;}
export function Loading(){return <div className="loading" role="status"><LoaderCircle className="spin" size={22}/>Loading…</div>;}
export function useResource<T>(path:string,revalidateOnEntry=false){
 const initial=readResource<T>(path);const [data,setDataState]=useState<T|null>(initial?.value??null);const [error,setError]=useState('');const [loading,setLoading]=useState(!initial);const [refreshVersion,setRefreshVersion]=useState(0);const handledRefresh=useRef(0);
 const setData=useCallback<Dispatch<SetStateAction<T|null>>>(value=>setDataState(previous=>{const next=typeof value==='function'?(value as (previous:T|null)=>T|null)(previous):value;if(next===null)clearResource(path);else writeResource(path,next);return next;}),[path]);
 const reload=useCallback(()=>setRefreshVersion(version=>version+1),[]);
 useEffect(()=>{let active=true;const cached=readResource<T>(path);const force=handledRefresh.current!==refreshVersion;handledRefresh.current=refreshVersion;
  if(cached){setDataState(cached.value);setLoading(false);}else{setDataState(null);setLoading(true);}
  setError('');if(cached?.fresh&&!force&&!revalidateOnEntry)return;
  if(!cached)setLoading(true);
  requestResource<T>(path,()=>api<T>(path)).then(value=>{if(active)setDataState(value);}).catch(e=>{if(active&&!cached)setError(message(e));}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;};
 },[path,refreshVersion,revalidateOnEntry]);
 return {data,error,loading,reload,setData};
}
export function ResourceError({error,retry}:{error:string;retry:()=>void}){return <div className="resource-error"><ErrorBox error={error}/><Button className="secondary" onClick={retry}>Try again</Button></div>;}
export function Modal({title,children,onClose}:{title:string;children:ReactNode;onClose:()=>void}){
  const ref=useRef<HTMLDialogElement>(null);useEffect(()=>{const old=document.activeElement as HTMLElement;ref.current?.showModal();return()=>old?.focus();},[]);
  return <dialog ref={ref} className="modal" onCancel={onClose} onClick={e=>{if(e.target===e.currentTarget)onClose();}}><div className="modal-head"><h2>{title}</h2><button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={20}/></button></div>{children}</dialog>;
}
export function Confirm({title,children,onConfirm,onClose}:{title:string;children:ReactNode;onConfirm:()=>Promise<void>;onClose:()=>void}){const [busy,setBusy]=useState(false);const [error,setError]=useState('');return <Modal title={title} onClose={onClose}><p className="muted">{children}</p><ErrorBox error={error}/><div className="modal-actions"><Button className="secondary" onClick={onClose}>Cancel</Button><Button className="danger" busy={busy} onClick={async()=>{setBusy(true);try{await onConfirm();onClose();}catch(e){setError(message(e));}finally{setBusy(false);}}}>Confirm</Button></div></Modal>;}
export function PageHeader({eyebrow,title,description,action}:{eyebrow?:string;title:string;description?:string;action?:ReactNode}){return <div className="page-heading"><div>{eyebrow&&<p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description&&<p>{description}</p>}</div>{action}</div>;}
export function AuthPage({mode,admin=false}:{mode:'login'|'register'|'forgot'|'reset';admin?:boolean}){
  const {user,setUser}=useAuth();const navigate=useNavigate();const [error,setError]=useState('');const [success,setSuccess]=useState('');const [busy,setBusy]=useState(false);
  const register=mode==='register',forgot=mode==='forgot',reset=mode==='reset';
  const {site}=useSite();const auth=site?.landing.auth;const plans=site?.plans||[];const [params]=useSearchParams();const next=useRef('/app');
  const [planId,setPlanId]=useState('');const selectedPlan=plans.find(plan=>plan.id===planId)||plans.find(plan=>plan.id===params.get('plan'))||plans.find(plan=>plan.price_monthly===0)||plans[0];
  useEffect(()=>{setError('');setSuccess('');},[mode]);
  const token=new URLSearchParams(window.location.search).get('token');
  useEffect(()=>{if(user&&(mode==='login'||register)&&(!admin||user.is_admin))navigate(user.must_change_password?'/change-password':admin?'/':next.current,{replace:true});},[user,mode,register,admin,navigate]);
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setError('');setSuccess('');setBusy(true);const f=new FormData(e.currentTarget);try{
    if(register){const u=await post<User>('/api/auth/register',{name:f.get('name'),email:f.get('email'),password:f.get('password'),accept_terms:f.get('terms')==='on',accept_privacy:f.get('terms')==='on',plan_id:selectedPlan?.id});if(selectedPlan&&selectedPlan.price_monthly>0)next.current='/app/billing?plan='+selectedPlan.id;setUser(u);}
    else if(forgot){const r=await post<{message:string}>('/api/auth/forgot-password',{email:f.get('email')});setSuccess(r.message);}
    else if(reset){if(f.get('password')!==f.get('confirm'))throw new Error('The passwords do not match.');await post('/api/auth/reset-password',{token,new_password:f.get('password')});setUser(null);setSuccess('Your password has been updated. You can now sign in.');}
    else{const u=await post<User>('/api/auth/login',{email:f.get('email'),password:f.get('password'),admin});setUser(u);}
  }catch(e){setError(message(e));}finally{setBusy(false);}}
  if(register&&site&&!site.saas_enabled)return <Navigate to="/login" replace/>;
  return <div className="auth-page"><aside className="auth-story"><Brand/><div className="auth-story-copy"><p>{auth?.heading}</p><p>{auth?.body}</p></div><small>{auth?.note}</small></aside><main className="auth-main"><Link className="back-link" to={admin?'/login':'/'}>← {admin?'Administration':'Back to home'}</Link><div className="auth-form"><div className="auth-title"><h1>{register?'Create your account':forgot?'Forgot your password?':reset?'Choose a new password':admin?'Administrator sign in':'Sign in'}</h1><ThemeToggle/></div><p className="muted">{register?'Create, share, and manage your QR codes in one place.':forgot?'We’ll help you get back to your account.':reset?'Choose a strong password to protect your account.':admin?'Sign in to manage TuraQRcode.':'Sign in to continue to your workspace.'}</p><ErrorBox error={error}/>{success?<><Success>{success}</Success>{reset&&<Link className="button full" to="/login">Continue to sign in<ArrowRight size={18}/></Link>}</>:<form onSubmit={submit}>
    {register&&plans.length>0&&<fieldset className="plan-picker"><legend className="sr-only">Plan</legend>{plans.map(plan=><label key={plan.id}><span><input type="radio" name="plan" checked={selectedPlan?.id===plan.id} onChange={()=>setPlanId(plan.id)}/>{plan.name}</span><small>{plan.price_monthly?money(plan.price_monthly,plan.currency)+' / month':'Free'}</small></label>)}</fieldset>}
    {register&&<Field label="Full name"><input name="name" autoComplete="name" required minLength={2} maxLength={100} placeholder="Your full name"/></Field>}
    {!reset&&<Field label="Email address"><input name="email" type="email" autoComplete="email" required maxLength={254} placeholder="you@company.com"/></Field>}
    {!forgot&&<Field label={reset?'New password':'Password'} hint={register||reset?'Use at least 12 characters, including a letter and a number.':undefined}><PasswordInput name="password" autoComplete={register||reset?'new-password':'current-password'} required minLength={register||reset?12:1} maxLength={128}/></Field>}
    {reset&&<Field label="Confirm new password"><PasswordInput name="confirm" autoComplete="new-password" required minLength={12} maxLength={128}/></Field>}
    {register&&<label className="checkbox-label"><input name="terms" type="checkbox" required/><span>I agree to the <Link to="/terms" target="_blank">Terms & Conditions</Link> and <Link to="/privacy" target="_blank">Privacy Policy</Link>.</span></label>}
    {!register&&!forgot&&!reset&&!admin&&<div className="form-link"><Link to="/forgot-password">Forgot password?</Link></div>}
    <Button className="full" busy={busy} disabled={reset&&!token}>{register?'Create account':forgot?'Send recovery instructions':reset?'Update password':'Sign in'}<ArrowRight size={18}/></Button>
    {reset&&!token&&<ErrorBox error="This recovery link is incomplete. Please request a new one."/>}
  </form>}
  {!admin&&<p className="auth-switch">{register?<>Already have an account? <Link to="/login">Sign in</Link></>:forgot||reset?<Link to="/login">Back to sign in</Link>:site?.saas_enabled?<>New here? <Link to="/register">Create an account</Link></>:null}</p>}<div className="auth-trust"><ShieldCheck size={16}/> Your account, securely protected</div></div></main></div>;
}
export function ChangePassword({admin=false}:{admin?:boolean}){
  const {user,setUser}=useAuth();const [error,setError]=useState('');const [busy,setBusy]=useState(false);const navigate=useNavigate();
  useEffect(()=>{if(user&&!user.must_change_password)navigate(admin?'/':'/app',{replace:true});},[user?.must_change_password,admin,navigate]);
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');const f=new FormData(e.currentTarget);try{if(f.get('password')!==f.get('confirm'))throw new Error('The passwords do not match.');const u=await post<User>('/api/auth/password',{current_password:f.get('current'),new_password:f.get('password')});setUser(u);}catch(e){setError(message(e));}finally{setBusy(false);}}
  return <div className="security-page"><Brand/><section className="panel"><ShieldCheck size={36} className="teal"/><h1>Secure your account</h1><p className="muted">{user?.must_change_password?'Before continuing, replace your temporary password with a password only you know.':'Choose a new password for your account.'}</p><ErrorBox error={error}/><form onSubmit={submit}><Field label="Current password"><PasswordInput name="current" required autoComplete="current-password"/></Field><Field label="New password" hint="Use at least 12 characters, including a letter and a number."><PasswordInput name="password" required minLength={12} maxLength={128} autoComplete="new-password"/></Field><Field label="Confirm new password"><PasswordInput name="confirm" required autoComplete="new-password"/></Field><Button className="full" busy={busy}>Update password & continue<ArrowRight size={18}/></Button></form></section></div>;
}
export function CopyButton({value,label='Copy link'}:{value:string;label?:string}){const [copied,setCopied]=useState(false);const [error,setError]=useState('');return <><button type="button" className="button secondary" onClick={async()=>{try{await navigator.clipboard.writeText(value);setCopied(true);setTimeout(()=>setCopied(false),2000);}catch{setError('Copy is unavailable in this browser. Select and copy the address shown.');}}}>{copied?<Check size={16}/>:<ArrowUpRight size={16}/>} {copied?'Copied':label}</button><ErrorBox error={error}/></>;}
