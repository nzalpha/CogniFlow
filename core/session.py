# core/session.py

import os
import sys
from typing import Optional, Any, List, Dict
from types import SimpleNamespace

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCP:
    """
    Lightweight wrapper for one-time MCP tool calls using stdio transport.
    Each call spins up a new subprocess and terminates cleanly.
    """

    def __init__(
        self,
        server_script: str = "mcp_server_2.py",
        working_dir: Optional[str] = None,
        server_command: Optional[str] = None,
    ):
        self.server_script = server_script
        self.working_dir = working_dir or os.getcwd()
        self.server_command = server_command or sys.executable

    async def list_tools(self):
        server_params = StdioServerParameters(
            command=self.server_command,
            args=[self.server_script],
            cwd=self.working_dir
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return tools_result.tools

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        server_params = StdioServerParameters(
            command=self.server_command,
            args=[self.server_script],
            cwd=self.working_dir
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, arguments=arguments)


class MultiMCP:
    """
    Stateless version: discovers tools from multiple MCP servers, but reconnects per tool call.
    Each call_tool() uses a fresh session based on tool-to-server mapping.
    """

    def __init__(self, server_configs: List[dict]):
        self.server_configs = server_configs
        self.tool_map: Dict[str, Dict[str, Any]] = {}  # tool_name → {config, tool}

    async def initialize(self):
        print("in MultiMCP initialize")
        for config in self.server_configs:
            if "script" in config:
                await self._register_stdio_server(config)
            elif "host" in config:
                self._register_http_server(config)
            else:
                print(f"⚠️ Skipping server config lacking 'script' or 'host': {config}")

    async def _register_stdio_server(self, config: Dict[str, Any]) -> None:
        """Discover tools from a traditional stdio-based MCP server."""
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=[config["script"]],
                cwd=config.get("cwd", os.getcwd())
            )
            print(f"→ Scanning tools from: {config['script']} in {params.cwd}")
            async with stdio_client(params) as (read, write):
                print("Connection established, creating session...")
                try:
                    async with ClientSession(read, write) as session:
                        print("[agent] Session created, initializing...")
                        await session.initialize()
                        print("[agent] MCP session initialized")
                        tools = await session.list_tools()
                        tool_names = [tool.name for tool in tools.tools]
                        print(f"→ Tools received: {tool_names}")
                        for tool in tools.tools:
                            self.tool_map[tool.name] = {
                                "config": {**config, "transport": "stdio"},
                                "tool": tool,
                                "transport": "stdio",
                            }
                except Exception as se:
                    print(f"❌ Session error: {se}")
        except Exception as e:
            script_name = config.get("script", "<unknown>")
            print(f"❌ Error initializing MCP server {script_name}: {e}")

    def _register_http_server(self, config: Dict[str, Any]) -> None:
        """Register statically defined HTTP tools from REST-style services."""
        tools = config.get("tools") or []
        if not tools:
            print(f"⚠️ HTTP server {config.get('name', config.get('host'))} has no tools defined; skipping.")
            return

        registered = []
        for tool_def in tools:
            tool_name = tool_def.get("name")
            endpoint = tool_def.get("endpoint")
            if not tool_name or not endpoint:
                print(f"⚠️ Invalid tool definition {tool_def}; requires 'name' and 'endpoint'.")
                continue

            tool_obj = SimpleNamespace(
                name=tool_name,
                description=tool_def.get("description") or config.get("description", ""),
                parameters=tool_def.get("parameters") or {},
            )
            self.tool_map[tool_name] = {
                "config": {**config, "transport": "http"},
                "tool": tool_obj,
                "transport": "http",
                "endpoint": endpoint,
                "method": (tool_def.get("method") or "POST").upper(),
            }
            registered.append(tool_name)

        if registered:
            print(
                f"→ Registered HTTP tools from {config.get('name', config.get('host'))}: {registered}"
            )

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        entry = self.tool_map.get(tool_name)
        if not entry:
            raise ValueError(f"Tool '{tool_name}' not found on any server.")

        config = entry["config"]
        transport = entry.get("transport", "stdio")

        if transport == "stdio":
            params = StdioServerParameters(
                command=sys.executable,
                args=[config["script"]],
                cwd=config.get("cwd", os.getcwd())
            )

            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(tool_name, arguments)

        if transport == "http":
            host = config.get("host")
            endpoint = entry.get("endpoint")
            method = entry.get("method", "POST").upper()
            if not host or not endpoint:
                raise ValueError(f"HTTP tool '{tool_name}' lacks host or endpoint configuration.")

            url = host.rstrip("/") + endpoint
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    if method == "GET":
                        response = await client.get(url, params=arguments)
                    else:
                        response = await client.post(url, json=arguments)
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"HTTP tool '{tool_name}' request failed: {exc}") from exc

            # Normalize to mimic MCP TextContent responses.
            return SimpleNamespace(content=SimpleNamespace(text=response.text))

        raise ValueError(f"Unsupported transport '{transport}' for tool '{tool_name}'.")

    async def list_all_tools(self) -> List[str]:
        return list(self.tool_map.keys())

    def get_all_tools(self) -> List[Any]:
        return [entry["tool"] for entry in self.tool_map.values()]

    async def shutdown(self):
        pass  # no persistent sessions to close
