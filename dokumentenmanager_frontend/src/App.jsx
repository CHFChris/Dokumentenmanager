import React from 'react'
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import ProtectedRoute from './components/ProtectedRoute'

export default function App() {
  return (
    <div style={{fontFamily:'system-ui, sans-serif', maxWidth: 900, margin: '0 auto', padding: 24}}>
      <header style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: 24}}>
        <h1 style={{margin:0}}>Dokumentenmanager</h1>
        <nav style={{display:'flex', gap:12}}>
          <Link to="/login">Login</Link>
          <Link to="/register">Registrieren</Link>
          <Link to="/app">App</Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login/>} />
        <Route path="/register" element={<Register/>} />
        <Route element={<ProtectedRoute/>}>
          <Route path="/app" element={<Dashboard/>} />
        </Route>
        <Route path="*" element={<div>404</div>} />
      </Routes>
    </div>
  )
}
