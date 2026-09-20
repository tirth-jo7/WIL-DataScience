
import defaultBot from './configs/telegram.config.ts';
import { TelegramHandler } from './telegram/telegram.handler.ts';

const telegramHandler = new TelegramHandler(
  defaultBot,
  'http://localhost:8000',
);

telegramHandler.register();

await defaultBot.start();