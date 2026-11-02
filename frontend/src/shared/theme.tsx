import {useState} from 'react';
import {Moon,Sun} from 'lucide-react';

const KEY='tura.theme';
type Theme='light'|'dark';
function stored():Theme{try{return localStorage.getItem(KEY)==='dark'?'dark':'light';}catch{return 'light';}}
export function applyStoredTheme(){document.documentElement.dataset.theme=stored();}
export function ThemeToggle(){
 const [theme,setTheme]=useState<Theme>(stored);const next=theme==='dark'?'light':'dark';const label='Switch to '+next+' mode';
 function toggle(){document.documentElement.dataset.theme=next;try{localStorage.setItem(KEY,next);}catch{/* Remembering the choice is optional. */}setTheme(next);}
 return <button type="button" className="theme-toggle" aria-label={label} title={label} onClick={toggle}>{theme==='dark'?<Moon size={15}/>:<Sun size={15}/>}</button>;
}
