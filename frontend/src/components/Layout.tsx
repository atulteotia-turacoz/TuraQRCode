import {useEffect, useState} from 'react';
import {Link, NavLink, Outlet, useLocation, useNavigate} from 'react-router-dom';
import {
  Activity, Barcode, ChevronRight, ContactRound, FolderOpen,
  LayoutDashboard, Layers, Link2, LogOut, Menu, QrCode, ScanLine, X,
} from 'lucide-react';
import {Brand, ErrorBox} from '../shared/ui';
import {useAuth} from '../shared/auth';
import {message} from '../shared/api';

const workspaceNavigation = [
  {to: '/app', label: 'Overview', icon: LayoutDashboard, end: true},
  {to: '/app/projects', label: 'Projects', icon: FolderOpen},
];

const manageNavigation = [
  {to: '/app/codes', label: 'QR codes', icon: QrCode},
  {to: '/app/links', label: 'Link shortener', icon: Link2},
  {to: '/app/barcodes', label: 'Barcodes', icon: Barcode},
  {to: '/app/business-cards', label: 'Business cards', icon: ContactRound},
  {to: '/app/bulk', label: 'Bulk & print', icon: Layers},
  {to: '/app/scanner', label: 'QR Scanner', icon: ScanLine},
];

function initials(name?: string) {
  return name?.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'TU';
}

export default function Layout() {
  const {user, logout} = useAuth();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const location = useLocation();
  const navigate = useNavigate();
  const isLinksArea = location.pathname.startsWith('/app/links');
  const isBarcodesArea = location.pathname.startsWith('/app/barcodes');
  const pageLabel = [...workspaceNavigation, ...manageNavigation, {to: '/app/analytics', label: 'Analytics'}]
    .find(item => 'end' in item && item.end ? location.pathname === item.to : location.pathname.startsWith(item.to))?.label
    || (isLinksArea ? 'Link shortener' : isBarcodesArea ? 'Barcodes' : location.pathname.startsWith('/app/create') ? 'Create a QR code' : 'Account settings');

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [open]);

  const closeNavigation = () => setOpen(false);
  const renderLink = (item: {to: string; label: string; icon: typeof QrCode; end?: boolean}) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      onClick={closeNavigation}
      className={({isActive}) => `sidebar-link${isActive ? ' active' : ''}`}
    >
      <item.icon size={18} strokeWidth={1.8} aria-hidden="true" />
      <span>{item.label}</span>
    </NavLink>
  );

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">Skip to content</a>
      {open && <button className="sidebar-scrim" onClick={closeNavigation} aria-label="Close navigation" />}

      <aside id="workspace-sidebar" className={`sidebar${open ? ' open' : ''}`} aria-label="Workspace">
        <div className="sidebar-brand">
          <Brand inverse />
          <button className="icon-button mobile-only" onClick={closeNavigation} aria-label="Close navigation">
            <X size={20} />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Workspace navigation">
          <div className="sidebar-group">
            <p className="sidebar-label">WORKSPACE</p>
            {workspaceNavigation.map(renderLink)}
          </div>

          <div className="sidebar-group">
            <p className="sidebar-label">MANAGE</p>
            {manageNavigation.map(renderLink)}
          </div>

          <div className="sidebar-group">
            <p className="sidebar-label">INSIGHTS</p>
            {renderLink({to: '/app/analytics', label: 'Analytics', icon: Activity})}
          </div>
        </nav>

        <div className="sidebar-bottom">
          <button className="sidebar-link sidebar-account-link" onClick={async () => {
            try {
              await logout();
              navigate('/login');
            } catch (exception) {
              setError(message(exception));
            }
          }}>
            <LogOut size={17} strokeWidth={1.8} aria-hidden="true" /><span>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="workspace">
        <header className="workspace-header">
          <div className="workspace-breadcrumb">
            <button
              className="icon-button mobile-only"
              onClick={() => setOpen(true)}
              aria-label="Open navigation"
              aria-expanded={open}
              aria-controls="workspace-sidebar"
            >
              <Menu size={21} />
            </button>
            <Link to="/app">Workspace</Link>
            <ChevronRight size={14} aria-hidden="true" />
            <span>{pageLabel}</span>
          </div>
          <div className="header-user">
            <span className="header-live"><i aria-hidden="true" />Your workspace is ready</span>
            <Link className="avatar" to="/app/settings" aria-label="Account settings">{initials(user?.name)}</Link>
            <span className="header-name">{user?.name}</span>
          </div>
        </header>

        <main className="workspace-main" id="main-content">
          <ErrorBox error={error} />
          <Outlet />
        </main>

        <footer className="workspace-footer">
          <span>© {new Date().getFullYear()} Turacoz</span>
          <span><Link to="/terms">Terms</Link><Link to="/privacy">Privacy</Link></span>
        </footer>
      </div>
    </div>
  );
}
