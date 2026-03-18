import { ReactNode } from 'react';
import NavBar from './NavBar';

interface LayoutProps {
  children: ReactNode;
}

const Layout = ({ children }: LayoutProps) => {
  return (
    <div className="min-h-screen bg-apple-gray-50">
      <NavBar />
      <main>{children}</main>
    </div>
  );
};

export default Layout;
