import "express";

import type { Database } from "../configs/database.config.ts";

declare global {
  namespace Express {
    interface Request {
      db: Database;
      meta: Record<string, any>;
    }
  }
}
