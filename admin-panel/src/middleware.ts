import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  // Excluir las rutas de API de asistencia (proxied a FastAPI) del chequeo de auth
  const path = request.nextUrl.pathname
  if (path.startsWith('/asistencia/api/') || path.startsWith('/asistencia/static/')) {
    return NextResponse.next()
  }

  const token = request.cookies.get('auth_token')?.value
  
  // Si no hay token y trata de entrar a admin o asistencia, redirigir al login
  if (!token) {
    return NextResponse.redirect(new URL('/', request.url))
  }
  
  return NextResponse.next()
}

export const config = {
  matcher: ['/dashboard/:path*', '/admin/:path*', '/asistencia/:path*'],
}
