import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { requireAdmin } from '@/lib/auth';
import bcrypt from 'bcryptjs';

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const authError = await requireAdmin();
  if (authError) return authError;

  try {
    const data = await request.json();
    const { name, email, password, startDate, endDate } = data;

    if (!name || !email || !startDate || !endDate) {
      return NextResponse.json({ error: 'Faltan campos obligatorios' }, { status: 400 });
    }

    const db = await getDb();
    
    // Check if another user has this email
    const existing = await db.get('SELECT id FROM users WHERE email = ? AND id != ?', [email, id]);
    if (existing) {
      return NextResponse.json({ error: 'El email ya está en uso por otro usuario' }, { status: 400 });
    }

    let query = 'UPDATE users SET name = ?, email = ?, startDate = ?, endDate = ?';
    let queryParams = [name, email, startDate, endDate];

    if (password) {
      const salt = await bcrypt.genSalt(10);
      const hash = await bcrypt.hash(password, salt);
      query += ', password = ?';
      queryParams.push(hash);
    }

    query += ' WHERE id = ?';
    queryParams.push(id);

    await db.run(query, queryParams);

    return NextResponse.json({ message: 'Usuario actualizado exitosamente' });
  } catch (error) {
    console.error(error);
    return NextResponse.json({ error: 'Error al actualizar usuario' }, { status: 500 });
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const authError = await requireAdmin();
  if (authError) return authError;

  try {
    const db = await getDb();
    
    // Prevent deleting admin or self (assuming id 1 is admin for now or check role)
    const targetUser = await db.get('SELECT role FROM users WHERE id = ?', [id]);
    if (targetUser && targetUser.role === 'admin') {
      return NextResponse.json({ error: 'No se puede eliminar a un administrador' }, { status: 403 });
    }

    await db.run('DELETE FROM users WHERE id = ?', [id]);

    return NextResponse.json({ message: 'Usuario eliminado' });
  } catch (error) {
    console.error(error);
    return NextResponse.json({ error: 'Error al eliminar usuario' }, { status: 500 });
  }
}
