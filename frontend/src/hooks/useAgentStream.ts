"use client";

import type { AgentEvent } from "@/types";

/** Read an SSE Response and yield each parsed AgentEvent.
 *
 * The stream emits `data: {...json...}\n\n` blocks. A `data: [DONE]\n\n` line
 * terminates the stream. Errors during parsing of a single event are skipped.
 */
export async function consumeAgentStream(
  res: Response,
  onEvent: (event: AgentEvent) => void
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;

  while (!done) {
    const { value, done: streamDone } = await reader.read();
    done = streamDone;
    if (!value) continue;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") {
        done = true;
        break;
      }
      try {
        const parsed = JSON.parse(data) as AgentEvent;
        onEvent(parsed);
      } catch {
        // skip malformed lines
      }
    }
  }
}
