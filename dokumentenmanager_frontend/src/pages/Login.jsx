import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login } from '../services/api'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  async function onSubmit(e) {
    e.preventDefault()
    setError(null)
    try {
      await login(email, password)
      navigate('/app')
    } catch (err) {
      setError(err?.detail?.message || 'Login fehlgeschlagen')
    }
  }

  return (
    <div style={{maxWidth: 420, margin: '0 auto'}}>
      <h2>Login</h2>
      <form onSubmit={onSubmit} style={{display:'grid', gap:12}}>
        <label>Email
          <input type="email" value={email} onChange={e=>setEmail(e.target.value)} required style={{width:'100%'}} />
        </label>
        <label>Passwort
          <input type="password" value={password} onChange={e=>setPassword(e.target.value)} required style={{width:'100%'}} />
        </label>
        {error && <div style={{color:'crimson'}}>{error}</div>}
        <button type="submit">Einloggen</button>
      </form>
      <p style={{marginTop:12}}>Noch kein Konto? <Link to="/register">Registrieren</Link></p>
    </div>
  )
}
