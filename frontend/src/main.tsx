import {StrictMode,Component,lazy,Suspense,type ErrorInfo,type ReactNode} from 'react';
import {createRoot} from 'react-dom/client';
import {applyStoredTheme} from './shared/theme';
import {BrowserRouter,Routes,Route,Link,Navigate,useLocation} from 'react-router-dom';
import {useEffect} from 'react';
import {AuthProvider,RequireAuth} from './shared/auth';
import {SiteProvider} from './shared/site';
import {AuthPage,ChangePassword,Brand,Loading} from './shared/ui';
import Layout from './components/Layout';
import {Home,Legal} from './pages/Public';
import {OverviewPage,CodesPage,CreatePage,DetailPage,AnalyticsPage,CreateLinkPage,CreateBarcodePage} from './pages/Codes';
const CardsPage=lazy(()=>import('./pages/Organization').then(module=>({default:module.CardsPage})));
const ProjectsPage=lazy(()=>import('./pages/Organization').then(module=>({default:module.ProjectsPage})));
const ScannerPage=lazy(()=>import('./pages/Scanner'));
const BillingPage=lazy(()=>import('./pages/Billing'));
import BulkPage from './pages/Bulk';
import SettingsPage from './pages/Settings';
import './shared/styles.css';
import './styles.css';
import './accessibility.css';
import './blue-theme.css';
import './workspace.css';
import './card-editor.css';
import './tura-theme.css';
class Boundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}componentDidCatch(_error:Error,_info:ErrorInfo){}render(){return this.state.failed?<main className="error-boundary"><Brand/><h1>Let’s get you back on track.</h1><p>This page couldn’t be displayed. Please refresh and try again.</p><button className="button" onClick={()=>window.location.reload()}>Refresh page</button></main>:this.props.children;}}
function ScrollTop(){const {pathname}=useLocation();useEffect(()=>{window.scrollTo(0,0);},[pathname]);return null;}
function App(){return <BrowserRouter><ScrollTop/><AuthProvider><SiteProvider><Suspense fallback={<Loading/>}><Routes><Route path="/" element={<Home/>}/><Route path="/barcode-generator" element={<Navigate to="/app/barcodes/new" replace/>}/><Route path="/login" element={<AuthPage mode="login"/>}/><Route path="/register" element={<AuthPage mode="register"/>}/><Route path="/forgot-password" element={<AuthPage mode="forgot"/>}/><Route path="/reset-password" element={<AuthPage mode="reset"/>}/><Route path="/terms" element={<Legal/>}/><Route path="/privacy" element={<Legal privacy/>}/><Route path="/change-password" element={<RequireAuth><ChangePassword/></RequireAuth>}/><Route path="/app" element={<RequireAuth><Layout/></RequireAuth>}><Route index element={<OverviewPage/>}/><Route path="codes" element={<CodesPage key="all"/>}/><Route path="create" element={<CreatePage/>}/><Route path="links" element={<CodesPage key="links" category="short"/>}/><Route path="links/new" element={<CreateLinkPage/>}/><Route path="links/:id" element={<DetailPage/>}/><Route path="barcodes" element={<CodesPage key="barcodes" category="barcode"/>}/><Route path="barcodes/new" element={<CreateBarcodePage/>}/><Route path="barcodes/:id" element={<DetailPage/>}/><Route path="codes/:id" element={<DetailPage/>}/><Route path="analytics" element={<AnalyticsPage/>}/><Route path="projects" element={<ProjectsPage/>}/><Route path="business-cards" element={<CardsPage/>}/><Route path="bulk" element={<BulkPage/>}/><Route path="scanner" element={<ScannerPage/>}/><Route path="billing" element={<BillingPage/>}/><Route path="settings" element={<SettingsPage/>}/></Route><Route path="*" element={<main className="security-page"><Brand/><div className="empty"><h1>This page took a different turn.</h1><p>Let’s get you back to a familiar place.</p><Link to="/" className="button">Back to home</Link></div></main>}/></Routes></Suspense></SiteProvider></AuthProvider></BrowserRouter>;}
applyStoredTheme();
createRoot(document.getElementById('root')!).render(<StrictMode><Boundary><App/></Boundary></StrictMode>);
