import path from 'path';

let dbInstance: any = null;
let pgPool: any = null;
const usePg = !!process.env.DATABASE_URL;

class DbWrapper {
  constructor(private sqliteDb: any, private pgDb: any) {}

  private replacePlaceholders(query: string) {
    if (!this.pgDb) return query;
    let i = 1;
    return query.replace(/\?/g, () => `$${i++}`);
  }

  async get(query: string, params: any[] = []) {
    if (this.pgDb) {
      const res = await this.pgDb.query(this.replacePlaceholders(query), params);
      return res.rows[0] || null;
    } else {
      return this.sqliteDb.get(query, params);
    }
  }

  async all(query: string, params: any[] = []) {
    if (this.pgDb) {
      const res = await this.pgDb.query(this.replacePlaceholders(query), params);
      return res.rows;
    } else {
      return this.sqliteDb.all(query, params);
    }
  }

  async run(query: string, params: any[] = []) {
    if (this.pgDb) {
      await this.pgDb.query(this.replacePlaceholders(query), params);
      return { lastID: null, changes: null };
    } else {
      return this.sqliteDb.run(query, params);
    }
  }
}

export async function getDb() {
  if (!dbInstance) {
    if (usePg) {
      const { Pool } = require('pg');
      pgPool = new Pool({
        connectionString: process.env.DATABASE_URL,
        ssl: { rejectUnauthorized: false }
      });
      dbInstance = new DbWrapper(null, pgPool);
      await initDbTables(dbInstance, true);
    } else {
      const sqlite3 = require('sqlite3');
      const { open } = require('sqlite');
      const dbPath = path.join(process.cwd(), 'database.sqlite');
      const sqliteDb = await open({
        filename: dbPath,
        driver: sqlite3.Database,
      });
      dbInstance = new DbWrapper(sqliteDb, null);
      await initDbTables(dbInstance, false);
    }
  }
  return dbInstance;
}

async function initDbTables(db: DbWrapper, isPg: boolean) {
  const idType = isPg ? 'SERIAL PRIMARY KEY' : 'INTEGER PRIMARY KEY AUTOINCREMENT';
  
  await db.run(`
    CREATE TABLE IF NOT EXISTS users (
      id ${idType},
      name VARCHAR(255) NOT NULL,
      email VARCHAR(255) UNIQUE NOT NULL,
      password TEXT NOT NULL,
      startDate VARCHAR(255) NOT NULL,
      endDate VARCHAR(255) NOT NULL,
      role VARCHAR(50) DEFAULT 'user'
    );
  `);
  
  const admin = await db.get(`SELECT id FROM users WHERE role = 'admin'`);
  if (!admin) {
    const bcrypt = require('bcryptjs');
    const salt = await bcrypt.genSalt(10);
    const hash = await bcrypt.hash('admin123', salt);
    
    const startDate = new Date().toISOString();
    const endDate = new Date(Date.now() + 100 * 365 * 24 * 60 * 60 * 1000).toISOString();
    
    await db.run(
      `INSERT INTO users (name, email, password, startDate, endDate, role) VALUES (?, ?, ?, ?, ?, ?)`,
      ['Admin', 'admin@example.com', hash, startDate, endDate, 'admin']
    );
  }
  
  return db;
}
