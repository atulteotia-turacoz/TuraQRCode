import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {api} from './api';

export type Plan={id:string;name:string;description:string;price_monthly:number;price_yearly:number;currency:string;max_codes:number|null;max_cards:number|null;max_projects:number|null;features:string[];is_featured:boolean};
export type LandingItem={title:string;body:string};
export type LandingSection={id:string;type:'generator'|'cards'|'steps'|'list'|'text'|'pricing'|'faq'|'cta';nav_label:string;heading:string;intro:string;body:string;note:string;button_label:string;items:LandingItem[]};
export type Landing={brand:{primary:string;accent:string};hero:{eyebrow:string;title:string;subtitle:string;note:string;signup_note:string;panel_title:string;panel_badge:string;panel_rows:{label:string;value:string;accent:boolean}[]};auth:{heading:string;body:string;note:string};sections:LandingSection[];footer:{tagline:string}};
export type Site={saas_enabled:boolean;landing:Landing;plans:Plan[]};

const Context=createContext<{site:Site|null;failed:boolean}>({site:null,failed:false});
export function SiteProvider({children}:{children:ReactNode}){
 const [site,setSite]=useState<Site|null>(null);const [failed,setFailed]=useState(false);
 useEffect(()=>{api<Site>('/api/site').then(setSite).catch(()=>setFailed(true));},[]);
 return <Context.Provider value={{site,failed}}>{children}</Context.Provider>;
}
export const useSite=()=>useContext(Context);
export function money(amount:number,currency:string){return new Intl.NumberFormat(undefined,{style:'currency',currency,minimumFractionDigits:amount%100?2:0,maximumFractionDigits:2}).format(amount/100);}
export function limitLabel(value:number|null,name:string){return (value===null?'Unlimited':value.toLocaleString())+' '+name;}
