import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './components/Login';
import UserManagement from './components/UserManagement';
import './App.css';

function App() {
  const isAuthenticated = () => {
    return !!localStorage.getItem('admin_token');
  };

  return (
    <Router>
      <Routes>
        <Route
          path="/login"
          element={
            isAuthenticated() ? <Navigate to="/users" replace /> : <Login />
          }
        />
        <Route
          path="/users"
          element={
            isAuthenticated() ? (
              <UserManagement />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
        <Route path="/" element={<Navigate to="/users" replace />} />
      </Routes>
    </Router>
  );
}

export default App;

