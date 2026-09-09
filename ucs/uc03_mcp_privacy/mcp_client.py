"""Synchronous MCP client for scripts and tests that drive the UC-03 server directly.

The official ``mcp`` SDK is asyncio-based. This wrapper spawns the server as a
child process over stdio, runs the session in a background thread with its own
event loop, and exposes ``list_tools`` / ``call_tool`` as ordinary blocking
calls. The demo smoke and the stdio tests use it; the chat goes through a
model host (``utils.generation.claude_mcp``) instead, because there the model,
not our code, chooses the tools.

Usage::

    with McpStdioClient(env={"UC03_SECURITY": "strict"}) as client:
        names = [t["name"] for t in client.list_tools()]
        found = client.call_tool("search_contacts", {"query": "Novák"})
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from typing import Any


class McpStdioClient:
    """Persistent stdio MCP session with a blocking call surface.

    Args:
        server_command: Command line of the server; defaults to this package's server.
        env: Extra environment variables for the server process (profile, paths).
        connect_timeout: Seconds to wait for the MCP handshake.
        call_timeout: Seconds to wait for one tool call.
    """

    def __init__(
        self,
        *,
        server_command: list[str] | None = None,
        env: dict[str, str] | None = None,
        connect_timeout: float = 20.0,
        call_timeout: float = 120.0,
    ) -> None:
        """Configure the session (see the class docstring); does not spawn the server yet."""
        self._server_command = server_command or [
            sys.executable,
            "-m",
            "ucs.uc03_mcp_privacy.server",
        ]
        self._env = dict(env or {})
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: Any | None = None
        self._exit_stack: Any | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self.server_stderr: str = ""

    # ------------------------------------------------------------------ life cycle

    def __enter__(self) -> "McpStdioClient":
        """Call `start` and return self."""
        self.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        """Call `close`, regardless of whether the block raised."""
        self.close()

    def start(self) -> None:
        """Spawn the server and complete the MCP handshake; raises what the SDK raised."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._thread_main, name="uc03-mcp-client", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=self._connect_timeout):
            raise TimeoutError(f"MCP handshake did not complete within {self._connect_timeout}s")
        if self._start_error is not None:
            raise RuntimeError(f"MCP server failed to start: {self._start_error}")

    def close(self) -> None:
        """Close the session and stop the server process.

        After a failed start the loop thread is already winding down on its own
        (the startup coroutine returns and the thread closes its loop), so only a
        live session gets the shutdown coroutine and the explicit ``loop.stop``.
        """
        loop = self._loop
        if loop is not None and self._session is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._async_shutdown(), loop)
            try:
                future.result(timeout=5.0)
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:  # the thread closed the loop meanwhile
                pass
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self._thread = None
        self._loop = None
        self._session = None

    # ------------------------------------------------------------------ calls

    def list_tools(self) -> list[dict[str, Any]]:
        """The advertised tools: name, description, inputSchema."""
        result = self._run(self._session.list_tools())
        return [
            {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema}
            for t in result.tools
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call one tool and return its JSON payload (a dict for every UC-03 tool but ``whoami``)."""
        result = self._run(self._session.call_tool(name, arguments or {}))
        texts = [getattr(block, "text", None) for block in (result.content or [])]
        texts = [t for t in texts if t]
        if getattr(result, "isError", False):
            # The SDK rejected the call (argument validation, an exception in the tool):
            # hand it back in the same shape as a tool's own refusal.
            return {"ok": False, "error": "tool_error", "message": "\n".join(texts)}
        if not texts:
            return {}
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]

    def _run(self, coro: Any) -> Any:
        """Schedule `coro` on the client's background loop and block for its result.

        Raises:
            RuntimeError: The client has not been started.
            TimeoutError: The call did not finish within `call_timeout`; the
                coroutine is cancelled, though a write may already have
                reached the server.
        """
        if self._loop is None or self._session is None:
            raise RuntimeError("MCP client not started")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=self._call_timeout)
        except TimeoutError:
            try:
                future.cancel()
            except RuntimeError:  # loop already closed
                pass
            raise TimeoutError(
                f"MCP call did not answer within {self._call_timeout}s; it was cancelled "
                "(a write may still have completed on the server)"
            ) from None

    # ------------------------------------------------------------------ async side

    def _thread_main(self) -> None:
        """Background-thread body: own an event loop, start the session, then serve calls."""
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_startup())
            if self._start_error is None:
                loop.run_forever()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            loop.close()

    async def _async_startup(self) -> None:
        """Spawn the server over stdio and complete the MCP handshake.

        Any exception is stored on `_start_error` for `start` to raise on the
        caller's thread, rather than propagating here.
        """
        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        try:
            env = os.environ.copy()
            env.update(self._env)
            params = StdioServerParameters(
                command=self._server_command[0], args=self._server_command[1:], env=env
            )
            stack = AsyncExitStack()
            self._exit_stack = stack
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._session = session
        except BaseException as exc:  # noqa: BLE001 - reported to the caller thread
            self._start_error = exc
        finally:
            self._ready.set()

    async def _async_shutdown(self) -> None:
        """Close the session and the server process; the owning thread stops the loop afterwards."""
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._exit_stack = None


__all__ = ["McpStdioClient"]
