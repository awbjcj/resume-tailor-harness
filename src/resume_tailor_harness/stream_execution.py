"""Run an async provider stream from a synchronous, cancellable run worker."""

import asyncio
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from typing import Any

worker_tools: ContextVar[bool] = ContextVar("conversation_worker_tools", default=False)


def interruptible_stream(
    agent: Any, prompt: str, checkpoint: Callable[[], None], close: Callable
) -> Iterator[Any]:
    """Keep one producer task/context and at most one buffered event.

    Polling the run checkpoint while awaiting network I/O lets Stop cancel a
    silent provider, including before the first token. Closing the iterator
    cancels and joins the task before releasing the spend gate.
    """
    with asyncio.Runner() as runtime:
        loop = runtime.get_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        end = object()

        async def produce():
            token = worker_tools.set(True)
            stream = agent.arun(
                prompt, stream=True, stream_events=True, yield_run_output=True
            )
            try:
                async for item in stream:
                    await queue.put(item)
            except Exception as exc:
                await queue.put(exc)
            finally:
                try:
                    await stream.aclose()
                finally:
                    worker_tools.reset(token)
            await queue.put(end)

        producer = loop.create_task(produce())
        pending = None
        try:
            while True:
                checkpoint()
                pending = loop.create_task(queue.get())
                while not pending.done():
                    loop.run_until_complete(
                        asyncio.wait(
                            {pending, producer},
                            timeout=0.05,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    )
                    checkpoint()
                    if producer.done() and queue.empty() and not pending.done():
                        producer.result()
                        return
                item = pending.result()
                if item is end:
                    return
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            if pending is not None:
                pending.cancel()
            producer.cancel()
            loop.run_until_complete(
                asyncio.gather(
                    producer,
                    *([pending] if pending is not None else []),
                    return_exceptions=True,
                )
            )
            loop.run_until_complete(close())
