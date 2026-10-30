import { ReadableStream, TransformStream, WritableStream } from "node:stream/web";

// jsdom's VM context omits these Node globals. MSW's fetch interceptor needs
// the real Web Streams implementations before its modules are evaluated.
for (const [name, value] of Object.entries({
  ReadableStream,
  TransformStream,
  WritableStream,
})) {
  if (!(name in globalThis)) {
    Object.defineProperty(globalThis, name, {
      configurable: true,
      writable: true,
      value,
    });
  }
}
