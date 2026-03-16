import { Routes, Route, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard.jsx';
import CustomerPortal from './pages/CustomerPortal.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';

function CustomerPortalWithKey() {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary>
      <CustomerPortal key={pathname} />
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/order" element={<CustomerPortalWithKey />} />
      <Route path="/order/:customerId" element={<CustomerPortalWithKey />} />
    </Routes>
  );
}
