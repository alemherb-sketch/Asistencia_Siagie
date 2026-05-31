import { NextResponse } from 'next/server';

export async function POST() {
  const response = NextResponse.json({ message: 'Cierre de sesión exitoso' });
  response.cookies.delete('auth_token');
  return response;
}
