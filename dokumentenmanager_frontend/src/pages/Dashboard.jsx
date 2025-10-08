import React, { useEffect, useState, useRef } from 'react'
import { me, listFiles, uploadFile, deleteFile, logout } from '../services/api'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const [user, setUser] = useState(null)
  const [files, setFiles] = useState([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [error, setError] = useState(null)
  const fileRef = useRef()
  const navigate = useNavigate()

  async function load() {
    setError(null)
    try {
      const u = await me()
      setUser(u)
      const data = await listFiles(q)
      setFiles(data.items)
      setTotal(data.total)
    } catch (err) {
      setError(err?.detail?.message || 'Fehler')
    }
  }

  useEffect(()=>{ load() }, [])

  async function onUpload(e) {
    e.preventDefault()
    const f = fileRef.current.files[0]
    if (!f) return
    setError(null)
    try {
      await uploadFile(f)
      fileRef.current.value = ''
      await load()
    } catch (err) {
      setError(err?.detail?.message || 'Upload fehlgeschlagen')
    }
  }

  async function onDelete(id) {
    try {
      await deleteFile(id)
      await load()
    } catch (err) {
      setError('Löschen fehlgeschlagen')
    }
  }

  function onLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center'}}>
        <h2>Willkommen {user?.email}</h2>
        <button onClick={onLogout}>Logout</button>
      </div>

      <form onSubmit={onUpload} style={{display:'flex', gap:12, alignItems:'center', margin:'12px 0'}}>
        <input type="file" ref={fileRef} />
        <button type="submit">Hochladen</button>
      </form>

      <div style={{display:'flex', gap:8, marginBottom:12}}>
        <input placeholder="Suche..." value={q} onChange={e=>setQ(e.target.value)} />
        <button onClick={load}>Suchen</button>
      </div>

      {error && <div style={{color:'crimson', marginBottom:12}}>{error}</div>}

      <table style={{width:'100%', borderCollapse:'collapse'}}>
        <thead>
          <tr>
            <th style={{textAlign:'left', borderBottom:'1px solid #ddd'}}>Name</th>
            <th style={{textAlign:'left', borderBottom:'1px solid #ddd'}}>Größe</th>
            <th style={{textAlign:'left', borderBottom:'1px solid #ddd'}}>SHA256</th>
            <th style={{textAlign:'left', borderBottom:'1px solid #ddd'}}>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {files.map(f => (
            <tr key={f.id}>
              <td>{f.name}</td>
              <td>{f.size}</td>
              <td style={{maxWidth:260, overflow:'hidden', textOverflow:'ellipsis'}} title={f.sha256}>{f.sha256}</td>
              <td>
                <button onClick={()=>onDelete(f.id)}>Löschen</button>
              </td>
            </tr>
          ))}
          {!files.length && <tr><td colSpan="4" style={{padding:12}}>Keine Dateien</td></tr>}
        </tbody>
      </table>
      <div style={{marginTop:12}}>Gesamt: {total}</div>
    </div>
  )
}
