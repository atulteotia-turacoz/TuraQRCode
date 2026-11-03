import {invalidateResources} from './resourceCache';

// Request paths already start with /api, so an origin ending in /api would double it.
export const API = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '').replace(/\/api$/, '');
export class ApiError extends Error { constructor(message:string,public status:number){super(message);} }
export async function api<T>(path:string, options:RequestInit={}):Promise<T>{
  let response:Response;
  try { response=await fetch(API+path,{...options,credentials:'include',headers:{...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}}); }
  catch { throw new ApiError('We couldn’t reach the service. Please check your connection and try again.',0); }
  if(!response.ok){
    let message='Something went wrong. Please try again.';
    try{ const data=await response.json(); if(typeof data.detail==='string') message=data.detail; }catch{ /* generic message */ }
    throw new ApiError(message,response.status);
  }
  if(response.status===204){if((options.method||'GET').toUpperCase()!=='GET')invalidateResources();return undefined as T;}
  const result=await response.json() as T;
  if((options.method||'GET').toUpperCase()!=='GET')invalidateResources();
  return result;
}
export const post=<T>(path:string,data:unknown)=>api<T>(path,{method:'POST',body:JSON.stringify(data)});
export const patch=<T>(path:string,data:unknown)=>api<T>(path,{method:'PATCH',body:JSON.stringify(data)});
export async function download(path:string,name:string,body?:unknown){
  const response=await fetch(API+path,{credentials:'include',method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});
  if(!response.ok){ let message='The download could not be completed. Please try again.';try{const data=await response.json();if(typeof data.detail==='string')message=data.detail;}catch{}throw new Error(message); }
  saveBlob(await response.blob(),name);
}
export function saveBlob(blob:Blob,name:string){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function message(error:unknown){return error instanceof Error?error.message:'Something went wrong. Please try again.';}
export function dateLabel(value:string){return new Date(value).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'});}
export function number(value:number){return value.toLocaleString();}
