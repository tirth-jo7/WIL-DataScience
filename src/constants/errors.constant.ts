export enum ErrorSource {
  CONTROLLER = "Controller",
  SERVICE = "Service",
  DATABASE = "Database",
  VALIDATION = "Validation",
  WEBHOOK = "Webhook",
  AUTH = "Authentication",
  UNKNOWN = "Unknown",
  HELPER = "Config"
}

export enum ErrorCode {
  UNKNOWN = "E0000",
  VALIDATION_FAILED = "E1001",
  ZOD_VALIDATION_FAILED = "E1002",
  UNAUTHORIZED = "E1003",
  FORBIDDEN = "E1004",
  NOT_FOUND = "E1005",
  DB_ERROR = "E2001",
  ALREADY_EXISTS = "E2002",
  WRONG_PASSWORD = "E2003",
  INVALID_INPUT = "E2004",
  FILE_UPLOAD_ERROR = "E3001",
  EMAIL_SERVICE_FAILURE = "E4001",
  EMPTY_RESPONSE = "E4002",
  HMAC_VERIFICATION_FAILED = "E5001",
  WEBHOOK_ERROR = "E5002",
  INVALID_OTP = "E1006"
}

export const ErrorMessages: Record<ErrorCode, string> = {
  [ErrorCode.UNKNOWN]: "An unknown error occurred",
  [ErrorCode.VALIDATION_FAILED]: "Validation failed",
  [ErrorCode.ZOD_VALIDATION_FAILED]: "ZOD Validation failed",
  [ErrorCode.UNAUTHORIZED]: "Unauthorized access",
  [ErrorCode.FORBIDDEN]: "Access is forbidden",
  [ErrorCode.NOT_FOUND]: "Resource not found",
  [ErrorCode.DB_ERROR]: "A database error occurred",
  [ErrorCode.FILE_UPLOAD_ERROR]: "File upload failed",
  [ErrorCode.EMAIL_SERVICE_FAILURE]: "Email service is unavailable",
  [ErrorCode.EMPTY_RESPONSE]: "No data returned from service",
  [ErrorCode.ALREADY_EXISTS]: "Already exists with provided data",
  [ErrorCode.WRONG_PASSWORD]: "Invalid credentials",
  [ErrorCode.INVALID_INPUT]: "No proper payload is created",
  [ErrorCode.HMAC_VERIFICATION_FAILED]: "HMAC code invalid",
  [ErrorCode.WEBHOOK_ERROR]: "Webhook failed",
  [ErrorCode.INVALID_OTP]: "Wrong OTP Provided, Verification failed"
};
