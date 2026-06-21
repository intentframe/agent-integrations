export class BridgeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BridgeError";
  }
}

export class BridgeHttpError extends BridgeError {
  readonly statusCode: number;
  readonly body: unknown;
  readonly expected?: number;

  constructor(statusCode: number, body: unknown, expected?: number) {
    super(
      expected !== undefined
        ? `expected HTTP ${expected}, got ${statusCode}: ${JSON.stringify(body)}`
        : `HTTP ${statusCode}: ${JSON.stringify(body)}`,
    );
    this.name = "BridgeHttpError";
    this.statusCode = statusCode;
    this.body = body;
    this.expected = expected;
  }
}
