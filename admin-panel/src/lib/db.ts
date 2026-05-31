import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import path from 'path';

// Ruta al archivo SQLite
const dbPath = path.join(process.cwd(), 'database.sqlite');

let dbInstance: any = null;

export async function getDb() {
  if (!dbInstance) {
    dbInstance = await open({
      filename: dbPath,
      driver: sqlite3.Database,
    });
    await initDbTables(dbInstance);
  }
  return dbInstance;
}

async function initDbTables(db: any) {
  
  await db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL,
      startDate TEXT NOT NULL,
      endDate TEXT NOT NULL,
      role TEXT DEFAULT 'user'
    );
  `);
  
  // Create default admin user if none exists
  const admin = await db.get(`SELECT id FROM users WHERE role = 'admin'`);
  if (!admin) {
    // Admin default password is 'admin123' (we will hash this later, using bcryptjs, but for now we just import it when the server starts)
    const bcrypt = require('bcryptjs');
    const salt = await bcrypt.genSalt(10);
    const hash = await bcrypt.hash('admin123', salt);
    
    // Admin has 100 years of validity
    const startDate = new Date().toISOString();
    const endDate = new Date(Date.now() + 100 * 365 * 24 * 60 * 60 * 1000).toISOString();
    
    await db.run(
      `INSERT INTO users (name, email, password, startDate, endDate, role) VALUES (?, ?, ?, ?, ?, ?)`,
      ['Admin', 'admin@example.com', hash, startDate, endDate, 'admin']
    );
  }
  
  return db;
}
