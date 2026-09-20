import { ErrorCode, ErrorMessages, ErrorSource } from "../constants/errors.constant.ts";

export class AppError extends Error {
  public readonly source: ErrorSource;
  public readonly code: ErrorCode;
  public readonly originalError?: any;

  constructor(
    message: string,
    source: ErrorSource, {
      code = ErrorCode.UNKNOWN,
      originalError
    }: {
      code?: ErrorCode;
      originalError?: any;
    } = {}
  ) {
    super(message);
    this.name = "AppError";
    this.source = source;
    this.code = code;
    this.originalError = originalError;
    Error.captureStackTrace(this, this.constructor);
  }

  static database(message: string, meta: Partial<{ code: ErrorCode; originalError: any }> = {}) {
    return new AppError(message, ErrorSource.DATABASE, {
      code: meta.code ?? ErrorCode.DB_ERROR,
      originalError: meta.originalError,
    });
  }

  static service(message: string, meta: Partial<{ code: ErrorCode; originalError: any }> = {}) {
    return new AppError(message, ErrorSource.SERVICE, {
      code: meta.code ?? ErrorCode.UNKNOWN,
      originalError: meta.originalError,
    });
  }

  static helper(message: string, meta: Partial<{ code: ErrorCode; originalError: any }> = {}) {
    return new AppError(message, ErrorSource.HELPER, {
      code: meta.code ?? ErrorCode.UNKNOWN,
      originalError: meta.originalError,
    });
  }

  static controller(message: string, meta: Partial<{ code: ErrorCode; originalError: any }> = {}) {
    return new AppError(message, ErrorSource.CONTROLLER, {
      code: meta.code ?? ErrorCode.UNKNOWN,
      originalError: !meta.originalError ? ErrorMessages[meta.code ?? ErrorCode.UNKNOWN] : meta.originalError,
    });
  }

  static webhook(message: string, meta: Partial<{ code: ErrorCode; originalError: any }> = {}) {
    return new AppError(message, ErrorSource.WEBHOOK, {
      code: meta.code ?? ErrorCode.UNKNOWN,
      originalError: !meta.originalError ? ErrorMessages[meta.code ?? ErrorCode.UNKNOWN] : meta.originalError,
    });
  }

  static validation(message: string, meta: Partial<{ originalError?: any }>) {
    return new AppError(message, ErrorSource.VALIDATION, {
      code: ErrorCode.VALIDATION_FAILED,
      originalError: meta.originalError,
    });
  }
}