import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Navigation items
// ---------------------------------------------------------------------------
interface NavItem {
  label: string;
  path: string;
  icon: string;  // simple emoji / unicode icon
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard',  path: '/',          icon: '\u25A0' },   // filled square
  { label: 'Signals',    path: '/signals',   icon: '\u26A1' },   // lightning
  { label: 'Models',     path: '/models',    icon: '\u2699' },   // gear
  { label: 'Training',   path: '/training',  icon: '\u23F3' },   // hourglass
  { label: 'Charts',     path: '/charts',    icon: '\u2191' },   // up arrow
  { label: 'Risk',       path: '/risk',      icon: '\u26A0' },   // warning
  { label: 'Trades',     path: '/trades',    icon: '\u21C4' },   // left-right arrows
  { label: 'Strategy',   path: '/strategy',  icon: '\u2694' },   // crossed swords
  { label: 'Sentiment',  path: '/sentiment', icon: '\u2665' },   // heart
  { label: 'Settings',   path: '/settings',  icon: '\u2630' },   // hamburger
  { label: 'Audit',      path: '/audit',     icon: '\u2611' },   // ballot box with check
  { label: 'Exchanges',  path: '/exchanges', icon: '\u2194' },   // left right arrow
  { label: 'Capital',    path: '/capital',   icon: '\u2B06' },   // upwards arrow
  { label: 'Research',   path: '/research',  icon: '\u2318' },   // place of interest
  { label: 'Pairs',      path: '/cointegration', icon: '\u2248' },  // approximately equal
];

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const SIDEBAR_WIDTH = 220;
const SIDEBAR_COLLAPSED = 56;

const sidebarBase: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  bottom: 0,
  background: '#0d1117',
  borderRight: '1px solid #21262d',
  display: 'flex',
  flexDirection: 'column',
  zIndex: 100,
  transition: 'width 0.2s ease',
  overflow: 'hidden',
};

const logoArea: React.CSSProperties = {
  padding: '16px 14px',
  borderBottom: '1px solid #21262d',
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  minHeight: 56,
};

const navItemBase: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '10px 14px',
  cursor: 'pointer',
  fontSize: 14,
  color: '#8b949e',
  borderRadius: 6,
  margin: '2px 8px',
  border: 'none',
  background: 'none',
  width: 'calc(100% - 16px)',
  textAlign: 'left',
  transition: 'background 0.15s, color 0.15s',
  whiteSpace: 'nowrap',
};

const activeStyle: React.CSSProperties = {
  background: '#161b22',
  color: '#e2e8f0',
  fontWeight: 600,
};

const toggleBtn: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#8b949e',
  cursor: 'pointer',
  padding: '12px 14px',
  fontSize: 18,
  textAlign: 'center',
  borderTop: '1px solid #21262d',
  marginTop: 'auto',
};

// ---------------------------------------------------------------------------
// Mobile detection hook
// ---------------------------------------------------------------------------
function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.innerWidth < breakpoint : false
  );

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint - 1}px)`);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    setIsMobile(mq.matches);
    return () => mq.removeEventListener('change', handler);
  }, [breakpoint]);

  return isMobile;
}

// ---------------------------------------------------------------------------
// Overlay
// ---------------------------------------------------------------------------
const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.5)',
  zIndex: 99,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
interface SidebarProps {
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ mobileOpen = false, onMobileClose }) => {
  const [collapsed, setCollapsed] = useState(false);
  const isMobile = useIsMobile();
  const location = useLocation();
  const navigate = useNavigate();

  // Close mobile drawer on navigation
  const handleNav = useCallback((path: string) => {
    navigate(path);
    if (isMobile && onMobileClose) onMobileClose();
  }, [navigate, isMobile, onMobileClose]);

  // On mobile: full width drawer, visibility controlled by mobileOpen prop
  // On desktop: normal collapsible sidebar
  const showSidebar = isMobile ? mobileOpen : true;
  const width = isMobile ? SIDEBAR_WIDTH : (collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_WIDTH);

  return (
    <>
      {/* Overlay for mobile */}
      {isMobile && mobileOpen && (
        <div style={overlayStyle} onClick={onMobileClose} />
      )}

      {/* Sidebar */}
      <nav style={{
        ...sidebarBase,
        width,
        transform: isMobile && !showSidebar ? `translateX(-${width}px)` : 'translateX(0)',
        transition: 'width 0.2s ease, transform 0.25s ease',
      }}>
        {/* Logo */}
        <div style={logoArea}>
          <span style={{ fontSize: 20, color: '#58a6ff', flexShrink: 0 }}>{'\u2726'}</span>
          {(!collapsed || isMobile) && (
            <span style={{ fontSize: 15, fontWeight: 700, color: '#e2e8f0', letterSpacing: 0.5 }}>
              SovereignForge
            </span>
          )}
        </div>

        {/* Nav items */}
        <div style={{ padding: '8px 0', flex: 1, overflowY: 'auto' }}>
          {NAV_ITEMS.map(item => {
            const isActive = location.pathname === item.path;
            return (
              <button
                key={item.path}
                onClick={() => handleNav(item.path)}
                style={{
                  ...navItemBase,
                  ...(isActive ? activeStyle : {}),
                }}
                title={collapsed && !isMobile ? item.label : undefined}
              >
                <span style={{ fontSize: 16, flexShrink: 0, width: 20, textAlign: 'center' }}>
                  {item.icon}
                </span>
                {(!collapsed || isMobile) && <span>{item.label}</span>}
              </button>
            );
          })}
        </div>

        {/* Collapse toggle (desktop only) */}
        {!isMobile && (
          <button
            style={toggleBtn}
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? '\u00BB' : '\u00AB'}
          </button>
        )}
      </nav>

      {/* Spacer so content is not hidden behind the fixed sidebar (desktop only) */}
      {!isMobile && (
        <div style={{ minWidth: width, width, transition: 'width 0.2s ease', flexShrink: 0 }} />
      )}
    </>
  );
};

export { SIDEBAR_WIDTH, SIDEBAR_COLLAPSED };
export default Sidebar;
