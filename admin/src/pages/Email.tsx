import {useEffect,useState,type FormEvent} from 'react';
import {Send} from 'lucide-react';
import {Button,ErrorBox,Field,Loading,PageHeader,ResourceError,Success,useResource} from '../shared/ui';
import {message,patch,post} from '../shared/api';

type Smtp={host:string;port:number;username:string;from_address:string;security:'starttls'|'ssl'|'none';has_password:boolean};

export default function EmailPage(){
 const r=useResource<Smtp>('/api/admin/smtp');const [saved,setSaved]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [sending,setSending]=useState(false);const [formKey,setFormKey]=useState(0);
 useEffect(()=>setFormKey(key=>key+1),[r.data]);
 if(r.error)return <ResourceError error={r.error} retry={r.reload}/>;
 if(r.loading||!r.data)return <Loading/>;
 const data=r.data;
 async function save(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError('');setSaved('');const f=new FormData(event.currentTarget);try{await patch('/api/admin/smtp',{host:f.get('host'),port:Number(f.get('port')),username:f.get('username'),password:f.get('password'),from_address:f.get('from_address'),security:f.get('security'),clear_password:f.get('clear_password')==='on'});setSaved('SMTP settings saved.');r.reload();}catch(e){setError(message(e));}finally{setBusy(false);}}
 async function test(event:FormEvent<HTMLFormElement>){event.preventDefault();setSending(true);setError('');setSaved('');try{const result=await post<{message:string}>('/api/admin/smtp/test',{to:new FormData(event.currentTarget).get('to')});setSaved(result.message);}catch(e){setError(message(e));}finally{setSending(false);}}
 return <><PageHeader title="Email (SMTP)" description="The mail server used for password recovery and other account email."/><ErrorBox error={error}/>{saved&&<Success>{saved}</Success>}
 <section className="panel"><form key={formKey} onSubmit={save}><div className="form-grid">
  <Field label="SMTP host"><input name="host" maxLength={253} defaultValue={data.host} placeholder="smtp.example.com"/></Field>
  <Field label="Port"><input name="port" type="number" min="1" max="65535" required defaultValue={data.port}/></Field>
  <Field label="Username"><input name="username" maxLength={254} autoComplete="off" defaultValue={data.username}/></Field>
  <Field label="Password" hint={data.has_password?'A password is saved. Leave blank to keep it.':'Stored encrypted and never shown again.'}><input name="password" type="password" maxLength={512} autoComplete="new-password"/></Field>
  <Field label="From address"><input name="from_address" maxLength={254} defaultValue={data.from_address} placeholder="TuraQRcode <no-reply@example.com>"/></Field>
  <Field label="Security"><select name="security" defaultValue={data.security}><option value="starttls">STARTTLS (usually port 587)</option><option value="ssl">SSL/TLS (usually port 465)</option><option value="none">None</option></select></Field>
 </div>{data.has_password&&<div className="form-actions"><label className="checkbox-label"><input name="clear_password" type="checkbox"/><span>Remove the saved password</span></label></div>}<div className="form-actions"><Button busy={busy}>Save settings</Button></div></form></section>
 <section className="panel"><h2>Send a test email</h2><form onSubmit={test}><Field label="Send to"><input name="to" type="email" required maxLength={254} placeholder="you@company.com"/></Field><Button className="secondary" busy={sending}><Send size={14}/>Send test</Button></form></section></>;
}
