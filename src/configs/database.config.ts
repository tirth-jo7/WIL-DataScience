import mssql, { type config as mssqlConfig } from 'mssql';
import type { DBName } from '../constants/database.constant.ts';
import { ErrorCode } from '../constants/errors.constant.ts';
import type { ProcedureInputMap } from '../types/generated/procedures-schemas.ts';
import type { TableInputMap } from '../types/generated/table-schemas.ts';
import { AppError } from '../utils/app-error.ts';
import { env } from './env.config.ts';
import logger from './logger.config.ts';

type MergeOptions = {
  mode?: 'insert' | 'update' | 'auto';
  transaction?: mssql.Transaction;
};

type MaybeOptional<T> = keyof T extends never ? true : false;

type BatchOperation = {
  procedureName: keyof ProcedureInputMap;
  data: any;
  mode: 'json' | 'script';
};

const config: mssqlConfig = {
  driver: 'msnodesqlv8',
  server: env.DB_SERVER || '',
  user: env.DB_USER || '',
  password: env.DB_PASSWORD || '',
  options: {
    trustServerCertificate: true,
    camelCaseColumns: false,
    connectTimeout: 3000,
  },
};

export class Database {
  private pool!: mssql.ConnectionPool;
  private readonly dbName: DBName;

  constructor(dbName: DBName) {
    this.dbName = dbName;
  }

  private getConfig(): mssqlConfig {
    return {
      ...config,
      database: this.dbName,
    };
  }

  public async connect(): Promise<void> {
    try {
      const pool = await new mssql.ConnectionPool(this.getConfig()).connect();
      this.pool = pool;
      // logger.info(`✅ Connected to database: ${this.dbName}`, "system");
    } catch (error) {
      logger.error(
        `❌ Connection failed for ${this.dbName}: ${error}`,
        'error',
      );
      throw AppError.database(`Failed to connect to ${this.dbName}`, {
        code: ErrorCode.DB_ERROR,
        originalError: error,
      });
    }
  }

  public async checkConnection(): Promise<boolean> {
    try {
      const result = await this.pool
        .request()
        .query('SELECT GETDATE() AS CurrentDate');
      return result.recordset.length > 0;
    } catch (error) {
      logger.error(`Database connection check failed: ${error}`, 'error');
      return false;
    }
  }

  public async reconnect(): Promise<void> {
    try {
      await this.disconnect();
    } catch (_) { }
    await this.connect();
  }

  public async disconnect(): Promise<void> {
    try {
      await this.pool.close();
      logger.info(`🔌 Disconnected from ${this.dbName}`, 'system');
    } catch (error) {
      logger.error(
        `❌ Failed to disconnect from ${this.dbName}: ${error}`,
        'error',
      );
    }
  }

  public async mergeIntoTable<T extends keyof TableInputMap>(
    table: T,
    data: TableInputMap[T][],
    keyColumns: (keyof TableInputMap[T])[],
    options: MergeOptions = {},
  ): Promise<{
    newRecords?: any[];
    updatedRecords?: any[];
    skippedRecords?: any[];
  }> {
    const { mode = 'insert', transaction } = options;

    if (!Array.isArray(data) || data.length === 0) {
      throw AppError.database('No data provided for merge operation', {
        code: ErrorCode.INVALID_INPUT,
      });
    }

    if (!Array.isArray(keyColumns) || keyColumns.length === 0) {
      throw AppError.database('No key columns provided for merge operation', {
        code: ErrorCode.INVALID_INPUT,
      });
    }

    try {
      const request = transaction
        ? new mssql.Request(transaction)
        : this.pool.request();
      request.input('TableName', table);
      request.input('Payload', JSON.stringify(data));
      request.input('KeyColumns', keyColumns.join(','));

      const proc =
        mode === 'insert'
          ? 'spu_SafeMergeTable'
          : 'spu_SafeMergeTableWithUpdate';

      logger.info(`🔄 Merging into table: ${table} | Mode: ${mode}`, 'db');
      const output = await request.execute(proc);
      console.table(output.recordsets);

      if (mode === 'update' || mode === 'auto') {
        if (!Array.isArray(output.recordsets)) {
          throw new Error('Expected output.recordsets to be an array');
        }
        const [newRecords = [], updatedRecords = [], skippedRecords = []] =
          output.recordsets ?? [];
        // orororor
        // const recordsets = output.recordsets as IRecordSet<any>[];
        // const [newRecords, updatedRecords, skippedRecords] = recordsets;

        return {
          newRecords,
          updatedRecords,
          skippedRecords,
        };
      } else {
        return {
          skippedRecords: output.recordset ?? [],
        };
      }
    } catch (err: any) {
      logger.error(
        `❌ Merge failed for ${table} | Mode: ${mode}: ${err}`,
        'error',
      );
      throw AppError.database(`Merge failed for ${table}`, {
        code: ErrorCode.DB_ERROR,
        originalError: err,
      });
    }
  }

  private createRequest(
    req: mssql.Request,
    data: { [key: string]: any },
  ): mssql.Request {
    // biome-ignore lint/suspicious/useIterableCallbackReturn: Tirth M. Jasoliya
    Object.entries(data).forEach(([key, value]) => req.input(key, value));
    return req;
  }

  /**
   * Execute a stored procedure with optional transaction support.
   */
  public async exec<T extends keyof ProcedureInputMap>(
    procedureName: T,
    ...args: MaybeOptional<ProcedureInputMap[T]> extends true
      ? [options?: { transaction?: mssql.Transaction }]
      : [
        options: {
          data: ProcedureInputMap[T];
          transaction?: mssql.Transaction;
        },
      ]
  ): Promise<any> {
    try {
      const [options] = args;
      const transaction = options?.transaction;
      const data = (options as any)?.data;
      const request = transaction
        ? new mssql.Request(transaction)
        : this.pool.request();
      this.createRequest(request, data ?? {});
      const result = await request.execute(procedureName);
      logger.info(`⭕ Executed procedure: ${procedureName}`, 'db');
      return Array.isArray(result.recordsets) && result.recordsets.length > 1
        ? result.recordsets
        : result.recordset;
    } catch (error) {
      logger.error(
        `❌ Error executing procedure "${procedureName}": ${error}`,
        'error',
      );
      throw AppError.database('Database error', {
        code: ErrorCode.DB_ERROR,
        originalError: error,
      });
    }
  }

  /**
   * Execute a raw SQL query with optional transaction support.
   */
  public async query(queryString: string): Promise<any>;
  public async query(
    queryString: string,
    transaction: mssql.Transaction,
  ): Promise<any>;
  public async query(
    queryString: string,
    params: Record<string, any>,
    transaction?: mssql.Transaction,
  ): Promise<any>;

  public async query(
    queryString: string,
    paramsOrTransaction?: Record<string, any> | mssql.Transaction,
    maybeTransaction?: mssql.Transaction,
  ): Promise<any> {
    try {
      const { params, transaction } = (() => {
        if (paramsOrTransaction instanceof mssql.Transaction) {
          return { params: undefined, transaction: paramsOrTransaction };
        }
        return { params: paramsOrTransaction, transaction: maybeTransaction };
      })();

      const request = transaction
        ? new mssql.Request(transaction)
        : this.pool.request();

      if (params) {
        for (const [key, value] of Object.entries(params)) {
          request.input(key, value);
        }
      }
      // console.log("queryString", queryString);

      const result = await request.query(queryString);
      logger.info(`⭕ Executed query: ${queryString}`, 'db');
      return result.recordsets;
    } catch (error) {
      logger.error(
        `❌ Error executing query "${queryString}": ${error}`,
        'error',
      );
      throw error;
    }
  }

  public batch(): {
    add: <T extends keyof ProcedureInputMap>(
      procedureName: T,
      data: ProcedureInputMap[T],
      mode?: 'json' | 'script',
    ) => void;
    execute: (options?: {
      transaction?: mssql.Transaction;
    }) => Promise<any[][]>;
  } {
    const operations: BatchOperation[] = [];

    const add = <T extends keyof ProcedureInputMap>(
      procedureName: T,
      data: ProcedureInputMap[T],
      mode: 'json' | 'script' = 'script',
    ) => {
      if (!data || typeof data !== 'object') {
        throw AppError.database('Invalid data for batch', {
          code: ErrorCode.INVALID_INPUT,
        });
      }
      operations.push({ procedureName, data, mode });
    };

    const execute = async (options?: { transaction?: mssql.Transaction }) => {
      if (operations.length === 0) return [];

      const transaction = options?.transaction;
      const request = transaction
        ? new mssql.Request(transaction)
        : this.pool.request();

      try {
        logger.info(
          `🚀 Executing batch of ${operations.length} operations`,
          'db',
        );

        const results: any[][] = [];

        const groupedOperations: {
          json: BatchOperation[];
          script: BatchOperation[];
        } = {
          json: operations.filter((op) => op.mode === 'json'),
          script: operations.filter((op) => op.mode === 'script'),
        };

        if (groupedOperations.json.length > 0) {
          const jsonGroups = this.groupByProcedure(groupedOperations.json);

          for (const [procName, ops] of Object.entries(jsonGroups)) {
            const payload = ops.map((op) => op.data);
            request.input('Payload', JSON.stringify(payload));
            const result = await request.execute(procName);
            results.push(
              Array.isArray(result.recordsets) && result.recordsets.length > 1
                ? result.recordsets.flat()
                : result.recordset,
            );
          }
        }

        if (groupedOperations.script.length > 0) {
          const script = groupedOperations.script
            .map(({ procedureName, data }) => {
              const args = Object.entries(data)
                .map(([k, v]) => {
                  if (typeof v === 'string')
                    return `@${k} = '${v.replace(/'/g, "''")}'`;
                  if (v === null || v === undefined) return `@${k} = NULL`;
                  return `@${k} = ${v}`;
                })
                .join(', ');
              return `EXEC ${procedureName} ${args};`;
            })
            .join('\n');

          const result = await request.query(script);
          results.push(
            Array.isArray(result.recordsets) && result.recordsets.length > 1
              ? result.recordsets.flat()
              : result.recordset,
          );
        }

        return results;
      } catch (err) {
        logger.error(`❌ Batch execution failed: ${err}`, 'error');
        throw AppError.database('Batch execution failed', {
          code: ErrorCode.DB_ERROR,
          originalError: err,
        });
      }
    };

    return { add, execute };
  }

  private groupByProcedure(
    operations: BatchOperation[],
  ): Record<string, BatchOperation[]> {
    return operations.reduce(
      (groups: Record<string, BatchOperation[]>, op: BatchOperation) => {
        if (!groups[op.procedureName]) {
          groups[op.procedureName] = [];
        }
        groups[op.procedureName]!.push(op);
        return groups;
      },
      {},
    );
  }

  /**
   * Start a new transaction.
   */
  public async beginTransaction(): Promise<mssql.Transaction> {
    try {
      const transaction = new mssql.Transaction(this.pool);
      await transaction.begin();
      logger.info('🔄 Transaction started.', 'db');
      return transaction;
    } catch (error) {
      logger.error(`❌ Failed to start transaction: ${error}`, 'error');
      throw error;
    }
  }

  /**
   * Commit an active transaction.
   */
  public async commitTransaction(
    transaction: mssql.Transaction,
  ): Promise<void> {
    try {
      await transaction.commit();
      logger.info('✅ Transaction committed.', 'db');
    } catch (error) {
      logger.error(`❌ Failed to commit transaction: ${error}`, 'error');
      throw error;
    }
  }

  /**
   * Rollback an active transaction.
   */
  public async rollbackTransaction(
    transaction: mssql.Transaction,
  ): Promise<void> {
    try {
      await transaction.rollback();
      logger.warn('⚠️ Transaction rolled back.', 'db');
    } catch (error) {
      logger.error(`❌ Failed to rollback transaction: ${error}`, 'error');
      throw error;
    }
  }
}

// // 🛑 Graceful shutdown handling
// process.on("SIGINT", async () => {
//   logger.warn("⚠️ Received SIGINT. Closing database connection...");
//   const db = await database;
//   await db.disconnect();
//   process.exit(0);
// });
// database.config.ts: Tirth Jasoliya

export class MultiDatabase {
  private dbMap = new Map<DBName, Database>();
  private validDBs = new Set<DBName>();

  registerValidDatabases(dbNames: Readonly<DBName[]>) {
    // biome-ignore lint/suspicious/useIterableCallbackReturn: Tirth M. Jasoliya
    dbNames.forEach((name) => this.validDBs.add(name));
  }

  async getSummary(): Promise<
    { name: DBName; status: 'connected' | 'disconnected' }[]
  > {
    const summaries: { name: DBName; status: 'connected' | 'disconnected' }[] =
      await Promise.all(
        [...this.validDBs].map(async (name) => {
          try {
            const db = await this.get(name);
            const isAlive = await db.checkConnection();
            return { name, status: isAlive ? 'connected' : 'disconnected' };
          } catch {
            return { name, status: 'disconnected' };
          }
        }),
      );
    return summaries;
  }

  async get(dbName: DBName): Promise<Database> {
    if (!this.validDBs.has(dbName)) {
      throw AppError.database(`Database ${dbName} is not whitelisted!`);
    }

    let db = this.dbMap.get(dbName);

    if (!db) {
      db = new Database(dbName);
      await db.connect();
      this.dbMap.set(dbName, db);
      return db;
    }

    const isConnected = await db.checkConnection();
    if (!isConnected) {
      await db.reconnect();
    }

    return db;
  }

  async disconnectAll(): Promise<void> {
    for (const [_, db] of this.dbMap.entries()) {
      await db.disconnect();
    }
    this.dbMap.clear();
  }
}

export const manager = new MultiDatabase();

const database = (async (dbName: DBName) => {
  if (!dbName) {
    logger.error('❌ database() called without DB name!');
    throw AppError.database('DB name is required for database()');
  }
  return await manager.get(dbName);
}) as typeof manager.get & {
  registerDatabases: (dbs: Readonly<DBName[]>) => void;
};

export default database;
