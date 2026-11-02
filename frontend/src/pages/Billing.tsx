import {useState} from 'react';
import {Navigate,useSearchParams} from 'react-router-dom';
import {CreditCard} from 'lucide-react';
import {Button,Empty,ErrorBox,Loading,Modal,PageHeader,ResourceError,Success,useResource} from '../shared/ui';
import {dateLabel,message,post} from '../shared/api';
import {money,useSite,type Plan} from '../shared/site';
import {CycleToggle,PlanGrid,type Cycle} from '../components/PlanCards';

type Gateway={id:string;label:string};
type Payment={id:string;plan_name:string;gateway:string;cycle:string;amount:number;currency:string;status:string;created_at:string};
type Billing={subscription:{plan:Plan;cycle:string;current_period_end:string|null;active:boolean}|null;usage:{codes:number;cards:number;projects:number};plans:Plan[];gateways:Gateway[];payments:Payment[]};
type Started={status:'active'}|{status:'redirect';redirect_url?:string;form?:{action:string;fields:Record<string,string>}};

function postForm(form:{action:string;fields:Record<string,string>}){const element=document.createElement('form');element.method='POST';element.action=form.action;for(const [name,value] of Object.entries(form.fields)){const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;element.append(input);}document.body.append(element);element.submit();}
const notices:Record<string,string>={success:'Payment received. Your plan is active.',failed:'The payment was not completed. You have not been charged for this attempt.',cancelled:'Checkout was cancelled.'};
const statusClass:Record<string,string>={paid:'success',pending:'neutral',failed:'paused'};

export default function BillingPage(){
 const {site}=useSite();const [params,setParams]=useSearchParams();const r=useResource<Billing>('/api/billing',true);
 const [cycle,setCycle]=useState<Cycle>('monthly');const [chosen,setChosen]=useState<Plan|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const preselected=params.get('plan');const outcome=params.get('payment');
 if(site&&!site.saas_enabled)return <Navigate to="/app" replace/>;
 if(r.error)return <ResourceError error={r.error} retry={r.reload}/>;
 if(r.loading||!r.data)return <Loading/>;
 const data=r.data;const current=data.subscription;
 async function start(plan:Plan,gateway?:string){setBusy(true);setError('');try{const result=await post<Started>('/api/billing/checkout',{plan_id:plan.id,cycle,gateway});if(result.status==='active'){setChosen(null);setParams({},{replace:true});r.reload();}else if(result.redirect_url)window.location.assign(result.redirect_url);else if(result.form)postForm(result.form);}catch(e){setError(message(e));}finally{setBusy(false);}}
 function choose(plan:Plan){setError('');const price=cycle==='yearly'?plan.price_yearly:plan.price_monthly;if(price===0)void start(plan);else setChosen(plan);}
 const stats=[{label:'Current plan',value:current?current.plan.name:'None',note:current?(current.active?(current.current_period_end?'Renews manually on '+dateLabel(current.current_period_end):'No expiry'):'Expired on '+dateLabel(current.current_period_end!)):'Choose a plan to start creating'},{label:'Codes and links',value:data.usage.codes.toLocaleString(),note:current?.plan.max_codes==null?'Unlimited':'of '+current.plan.max_codes.toLocaleString()},{label:'Business cards',value:data.usage.cards.toLocaleString(),note:current?.plan.max_cards==null?'Unlimited':'of '+current.plan.max_cards.toLocaleString()}];
 return <><PageHeader title="Billing" description="Your plan, usage and payment history."/>{outcome&&notices[outcome]&&(outcome==='success'?<Success>{notices[outcome]}</Success>:<div className="notice info" role="status"><span>{notices[outcome]}</span></div>)}<ErrorBox error={chosen?'':error}/><div className="billing-grid">{stats.map(stat=><article className="stat" key={stat.label}><div className="stat-top"><span>{stat.label}</span></div><strong>{stat.value}</strong><small>{stat.note}</small></article>)}</div>
 <section className="panel"><div className="lp-pricing-head"><h2>Plans</h2><CycleToggle cycle={cycle} onChange={setCycle}/></div>{data.plans.length?<PlanGrid plans={data.plans} cycle={cycle} action={plan=><Button className={plan.id===preselected?'':'secondary'} busy={busy} onClick={()=>choose(plan)}>{current?.active&&current.plan.id===plan.id?'Extend this plan':'Choose '+plan.name}</Button>}/>:<Empty icon={<CreditCard size={25}/>} heading="No plans available">Please contact your administrator.</Empty>}</section>
 <section className="panel"><h2>Payment history</h2>{data.payments.length?<div className="table-wrap"><table><thead><tr><th>Date</th><th>Plan</th><th>Amount</th><th>Method</th><th>Status</th></tr></thead><tbody>{data.payments.map(p=><tr key={p.id}><td className="nowrap">{dateLabel(p.created_at)}</td><td>{p.plan_name} · {p.cycle}</td><td>{money(p.amount,p.currency)}</td><td className="muted">{p.gateway}</td><td><span className={'badge '+(statusClass[p.status]||'neutral')}>{p.status}</span></td></tr>)}</tbody></table></div>:<p className="muted">No payments yet.</p>}</section>
 {chosen&&<Modal title={'Pay for '+chosen.name} onClose={()=>setChosen(null)}><p className="muted">{money(cycle==='yearly'?chosen.price_yearly:chosen.price_monthly,chosen.currency)} for one {cycle==='yearly'?'year':'month'}. You will be taken to the provider’s secure payment page. Plans do not renew automatically.</p><ErrorBox error={error}/>{data.gateways.length?<div className="gateway-choice">{data.gateways.map(gateway=><Button key={gateway.id} busy={busy} onClick={()=>start(chosen,gateway.id)}>Pay with {gateway.label}</Button>)}</div>:<div className="notice info"><span>Online payment is not set up yet. Please contact your administrator.</span></div>}</Modal>}
 </>;
}
