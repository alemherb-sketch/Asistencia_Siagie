'use client';

import { useState, useEffect } from 'react';

export default function AdminDashboard() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formData, setFormData] = useState({ name: '', email: '', password: '', startDate: '', endDate: '' });
  const [error, setError] = useState('');
  
  // Para hoy
  const today = new Date().toISOString().split('T')[0];

  const fetchUsers = async () => {
    try {
      const res = await fetch('/api/users');
      const data = await res.json();
      setUsers(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    try {
      const url = editingId ? `/api/users/${editingId}` : '/api/users';
      const method = editingId ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      const data = await res.json();
      
      if (!res.ok) throw new Error(data.error || 'Error al guardar usuario');
      
      setShowModal(false);
      setEditingId(null);
      setFormData({ name: '', email: '', password: '', startDate: '', endDate: '' });
      fetchUsers();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleEdit = (user: any) => {
    setEditingId(user.id);
    setFormData({
      name: user.name,
      email: user.email,
      password: '',
      startDate: user.startDate ? new Date(user.startDate).toISOString().split('T')[0] : '',
      endDate: user.endDate ? new Date(user.endDate).toISOString().split('T')[0] : ''
    });
    setShowModal(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm('¿Estás seguro de eliminar este usuario?')) return;
    try {
      await fetch(`/api/users/${id}`, { method: 'DELETE' });
      fetchUsers();
    } catch (err) {
      console.error(err);
    }
  };

  const getStatus = (start: string, end: string) => {
    const now = new Date();
    const startDate = new Date(start);
    const endDate = new Date(end);

    if (now < startDate) return <span className="badge" style={{ background: 'rgba(234, 179, 8, 0.1)', color: '#eab308', border: '1px solid rgba(234, 179, 8, 0.2)' }}>Programado</span>;
    if (now > endDate) return <span className="badge badge-danger">Expirado</span>;
    return <span className="badge badge-success">Activo</span>;
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>Gestión de Usuarios</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Administra el acceso y tiempo de uso</p>
        </div>
        <button onClick={() => {
          setEditingId(null);
          setFormData({ name: '', email: '', password: '', startDate: '', endDate: '' });
          setShowModal(true);
        }} className="btn btn-primary">
          + Crear Usuario
        </button>
      </div>

      <div className="glass-panel table-container">
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>Cargando usuarios...</div>
        ) : (
          <table style={{ width: '100%' }}>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Email</th>
                <th>Rol</th>
                <th>Inicio</th>
                <th>Fin (Expiración)</th>
                <th>Estado</th>
                <th style={{ textAlign: 'right' }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td style={{ fontWeight: 500 }}>{user.name}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{user.email}</td>
                  <td>
                    <span className="badge" style={{ background: user.role === 'admin' ? 'rgba(99, 102, 241, 0.1)' : 'rgba(255, 255, 255, 0.05)', color: user.role === 'admin' ? 'var(--primary-color)' : 'var(--text-muted)' }}>
                      {user.role}
                    </span>
                  </td>
                  <td>{user.startDate ? new Date(user.startDate).toLocaleDateString() : '-'}</td>
                  <td>{user.endDate ? new Date(user.endDate).toLocaleDateString() : '-'}</td>
                  <td>{user.role === 'admin' ? <span className="badge badge-success">Activo</span> : getStatus(user.startDate, user.endDate)}</td>
                  <td style={{ textAlign: 'right' }}>
                    {user.role !== 'admin' && (
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button onClick={() => handleEdit(user)} className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', background: 'rgba(255,255,255,0.1)', color: 'white' }}>
                          Editar
                        </button>
                        <button onClick={() => handleDelete(user.id)} className="btn btn-danger" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                          Eliminar
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>No hay usuarios registrados</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, backdropFilter: 'blur(4px)' }}>
          <div className="glass-panel animate-fade-in" style={{ width: '100%', maxWidth: '500px', padding: '2rem', background: '#191c29' }}>
            <h2 style={{ fontSize: '1.25rem', marginBottom: '1.5rem', fontWeight: 600 }}>
              {editingId ? 'Editar Usuario' : 'Nuevo Usuario'}
            </h2>
            
            {error && (
              <div style={{ background: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger-color)', padding: '0.75rem', borderRadius: '8px', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">Nombre Completo</label>
                <input required className="form-input" type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} />
              </div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input required className="form-input" type="email" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} />
              </div>
              <div className="form-group">
                <label className="form-label">
                  Contraseña de Acceso {editingId && <span style={{fontSize: '0.75rem', color: 'var(--text-muted)'}}>(Opcional)</span>}
                </label>
                <input required={!editingId} className="form-input" type="password" value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} />
              </div>
              
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Fecha de Inicio</label>
                  <input required className="form-input" type="date" min={today} value={formData.startDate} onChange={e => setFormData({...formData, startDate: e.target.value})} />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Fecha de Fin (Expiración)</label>
                  <input required className="form-input" type="date" min={formData.startDate || today} value={formData.endDate} onChange={e => setFormData({...formData, endDate: e.target.value})} />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '2rem' }}>
                <button type="button" onClick={() => setShowModal(false)} className="btn" style={{ background: 'transparent', color: 'var(--text-muted)' }}>
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary">
                  {editingId ? 'Guardar Cambios' : 'Crear Cuenta'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
