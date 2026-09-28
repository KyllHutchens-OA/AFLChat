import { ReactNode } from 'react';
import NavBar from './NavBar';
import MobileTabBar from './MobileTabBar';

interface LayoutProps {
  children: ReactNode;
}

const Layout = ({ children }: LayoutProps) => {
  return (
    <div className="h-dvh flex flex-col overflow-hidden">
      <NavBar />
      {/* pb-14 keeps content clear of the fixed mobile tab bar */}
      <div className="flex-1 overflow-auto pb-14 sm:pb-0">{children}</div>
      <MobileTabBar />
    </div>
  );
};

export default Layout;
