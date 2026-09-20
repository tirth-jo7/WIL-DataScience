export const DB_NAME_LIST = [
  'Roster'
] as const;

export type DBName = typeof DB_NAME_LIST[number]