import { Component } from 'react';
import { Link } from 'react-router-dom';

/** Catches render errors and shows a fallback so the app never goes blank. */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('CustomerPortal error:', error, info?.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-white flex items-center justify-center max-w-lg mx-auto p-4">
          <div className="text-center">
            <p className="text-gray-700 font-medium mb-2">Something went wrong loading this page.</p>
            <p className="text-sm text-gray-500 mb-4">{String(this.state.error?.message || this.state.error)}</p>
            <Link to="/order" className="text-blue-600 hover:underline">Back to customer list</Link>
            <span className="mx-2 text-gray-400">·</span>
            <Link to="/" className="text-blue-600 hover:underline">Dashboard</Link>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
