import type {
  RagRequest,
  RagResponse,
} from './rag.types.ts';

export class RagClient {
  constructor(
    private readonly baseUrl: string,
  ) { }

  async query(
    request: RagRequest,
  ): Promise<RagResponse> {
    const response = await fetch(
      `${this.baseUrl}/query`,
      {
        method: 'POST',

        headers: {
          'Content-Type': 'application/json',
        },

        body: JSON.stringify(request),
      },
    );

    if (!response.ok) {
      throw new Error(
        `RAG API failed: ${response.status} ${response.statusText}`,
      );
    }

    return response.json() as Promise<RagResponse>;
  }
}