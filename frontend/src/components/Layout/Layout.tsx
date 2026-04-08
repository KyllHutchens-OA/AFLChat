import { ReactNode } from 'react';
import NavBar from './NavBar';

interface LayoutProps {
  children: ReactNode;
}

const Layout = ({ children }: LayoutProps) => {
  return (
    <div className="h-dvh flex flex-col overflow-hidden">
      <NavBar />
      <div className="flex-1 overflow-auto">{children}</div>
    </div>
  );
};

export default Layout;
