import { Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard.jsx';
import CustomerPortal from './pages/CustomerPortal.jsx';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/order/:customerId" element={<CustomerPortal />} />
    </Routes>
  );
}
