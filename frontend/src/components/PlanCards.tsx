import {Check} from 'lucide-react';
import type {ReactNode} from 'react';
import {limitLabel,money,type Plan} from '../shared/site';

export type Cycle='monthly'|'yearly';
export function CycleToggle({cycle,onChange}:{cycle:Cycle;onChange:(value:Cycle)=>void}){return <div className="cycle" role="group" aria-label="Billing period">{(['monthly','yearly'] as const).map(value=><button key={value} type="button" aria-pressed={cycle===value} onClick={()=>onChange(value)}>{value==='monthly'?'Monthly':'Yearly'}</button>)}</div>;}
export function PlanGrid({plans,cycle,action}:{plans:Plan[];cycle:Cycle;action:(plan:Plan)=>ReactNode}){return <div className="plan-grid">{plans.map(plan=>{const price=cycle==='yearly'?plan.price_yearly:plan.price_monthly;return <article key={plan.id} className={'plan-card'+(plan.is_featured?' featured':'')}><h3>{plan.name}{plan.is_featured&&<span className="badge accent">Popular</span>}</h3>{plan.description&&<p>{plan.description}</p>}<div className="plan-price">{price?money(price,plan.currency):'Free'}{price>0&&<small> / {cycle==='yearly'?'year':'month'}</small>}</div><ul>{[limitLabel(plan.max_codes,'codes and links'),limitLabel(plan.max_cards,'business cards'),limitLabel(plan.max_projects,'projects'),...plan.features].map(item=><li key={item}><Check size={14} aria-hidden="true"/>{item}</li>)}</ul>{action(plan)}</article>;})}</div>;}
