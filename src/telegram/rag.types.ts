export interface RagRequest {
  requestId: string;

  channel: 'telegram';

  user: {
    id: number;
    username?: string;
    firstName?: string;
  };

  message: {
    text: string;
    timestamp: string;
  };
}

export interface RagSource {
  title: string;
  url: string;
}

export interface RagResponse {
  requestId: string;

  response: {
    text: string;
  };

  classification: {
    type: 'navigation' | 'crisis' | 'unsupported';
    confidence: number;
  };

  sources: RagSource[];

  safety: {
    crisisDetected: boolean;
    clinicalAdvice: boolean;
  };
}