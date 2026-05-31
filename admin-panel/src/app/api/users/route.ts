import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { requireAdmin } from '@/lib/auth';
import bcrypt from 'bcryptjs';

export const dynamic = 'force-dynamic';

export async function GET() {
  const authError = await requireAdmin();
  if (authError) return authError;

  try {
    const db = await getDb();
    const users = await db.all('SELECT id, name, email, startDate, endDate, role FROM users ORDER BY id DESC');
    return NextResponse.json(users);
  } catch (error) {
    return NextResponse.json({ error: 'Error al obtener usuarios' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const authError = await requireAdmin();
  if (authError) return authError;

  try {
    const data = await request.json();
    const { name, email, password, startDate, endDate } = data;

    if (!name || !email || !password || !startDate || !endDate) {
      return NextResponse.json({ error: 'Todos los campos son obligatorios' }, { status: 400 });
    }

    const db = await getDb();

    // Check if email already exists
    const existing = await db.get('SELECT id FROM users WHERE email = ?', [email]);
    if (existing) {
      return NextResponse.json({ error: 'El email ya está registrado' }, { status: 400 });
    }

    const salt = await bcrypt.genSalt(10);
    const hash = await bcrypt.hash(password, salt);

    const result = await db.run(
      'INSERT INTO users (name, email, password, startDate, endDate, role) VALUES (?, ?, ?, ?, ?, ?)',
      [name, email, hash, startDate, endDate, 'user']
    );

    return NextResponse.json({ message: 'Usuario creado exitosamente', id: result.lastID });
  } catch (error) {
    console.error(error);
    return NextResponse.json({ error: 'Error al crear usuario' }, { status: 500 });
  }
}
