import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { api, post } from './api';
import type {User} from './types';

type Auth={user:User|null;loading:boolean;setUser:(user:User|null)=>void;logout:()=>Promise<void>};
const Context=createContext<Auth>(null!);
export function AuthProvider({children}:{children:ReactNode}){
  const [user,setUser]=useState<User|null>(null);const [loading,setLoading]=useState(true);
  // Administrators work in the administration app. Local apps share a cookie across ports.
  useEffect(()=>{api<User>('/api/auth/me').then(value=>setUser(value.is_admin?null:value)).catch(()=>setUser(null)).finally(()=>setLoading(false));},[]);
  async function logout(){await post('/api/auth/logout',{});setUser(null);}
  return <Context.Provider value={{user,loading,setUser,logout}}>{children}</Context.Provider>;
}
export const useAuth=()=>useContext(Context);
export function RequireAuth({children,admin=false}:{children:ReactNode;admin?:boolean}){
  const {user,loading}=useAuth();const location=useLocation();
  if(loading)return <div className="page-loading" role="status">Opening your workspace…</div>;
  if(!user||(admin&&!user.is_admin))return <Navigate to="/login" state={{from:location.pathname}} replace/>;
  if(user.must_change_password&&location.pathname!='/change-password')return <Navigate to="/change-password" replace/>;
  return <>{children}</>;
}
