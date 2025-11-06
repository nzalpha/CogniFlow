# agent.py

import asyncio
import yaml
import httpx
import json
from core.loop import AgentLoop
from core.session import MultiMCP

def log(stage: str, msg: str):
    """Simple timestamped console logger."""
    import datetime
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")


async def get_telegram_query():
    """Listen to Telegram SSE stream and return the next user message."""
    print("🛰️ Waiting for Telegram message...")
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", "http://127.0.0.1:8081/events") as stream:
            async for line in stream.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    try:
                        data = json.loads(line.replace("data:", "").strip())
                        query = data.get("query", "").strip()
                        if query:
                            print(f"📩 Received Telegram message: {query}")
                            return query
                    except json.JSONDecodeError:
                        print("⚠️ Invalid JSON from SSE stream, skipping.")
                        continue


async def main():
    print("🧠 Cortex-R Agent Ready")

    # Wait for Telegram-triggered query
    user_input = await get_telegram_query()

    # Load MCP server configs
    with open("config/profiles.yaml", "r") as f:
        profile = yaml.safe_load(f)
        mcp_servers = profile.get("mcp_servers", [])

    # Initialize and run agent
    multi_mcp = MultiMCP(server_configs=mcp_servers)
    print("Agent before initialize")
    await multi_mcp.initialize()

    agent = AgentLoop(user_input=user_input, dispatcher=multi_mcp)

    try:
        final_response = await agent.run()
        print("\n💡 Final Answer:\n", final_response.replace("FINAL_ANSWER:", "").strip())
    except Exception as e:
        log("fatal", f"Agent failed: {e}")
        raise

    print("✅ Agent completed run and exiting.")


if __name__ == "__main__":
    asyncio.run(main())



# # agent.py

# import asyncio
# import yaml
# from core.loop import AgentLoop
# from core.session import MultiMCP
# import pdb
# import httpx
# import json

# async def get_telegram_query():
#     """Listen to Telegram SSE stream and return the next user message."""
#     print("🛰️ Waiting for Telegram message...")
#     async with httpx.AsyncClient(timeout=None) as client:
#         async with client.stream("GET", "http://127.0.0.1:8081/events") as stream:
#             async for line in stream.aiter_lines():
#                 if line.startswith("data:"):
#                     data = json.loads(line.replace("data:", "").strip())
#                     query = data.get("query", "").strip()
#                     if query:
#                         print(f"📩 Received Telegram message: {query}")
#                         return query


# def log(stage: str, msg: str):
#     """Simple timestamped console logger."""
#     import datetime
#     now = datetime.datetime.now().strftime("%H:%M:%S")
#     print(f"[{now}] [{stage}] {msg}")


# async def main():
    
#     print("🧠 Cortex-R Agent Ready")
#     pdb.set_trace()
#     user_input = await get_telegram_query()

#     # Load MCP server configs from profiles.yaml
#     with open("config/profiles.yaml", "r") as f:
#         profile = yaml.safe_load(f)
#         mcp_servers = profile.get("mcp_servers", [])

#     multi_mcp = MultiMCP(server_configs=mcp_servers)
#     print("Agent before initialize")
#     await multi_mcp.initialize()

#     agent = AgentLoop(
#         user_input=user_input,
#         dispatcher=multi_mcp  # now uses dynamic MultiMCP
#     )

#     try:
#         final_response = await agent.run()
#         print("\n💡 Final Answer:\n", final_response.replace("FINAL_ANSWER:", "").strip())

#     except Exception as e:
#         log("fatal", f"Agent failed: {e}")
#         raise


# if __name__ == "__main__":
#     asyncio.run(main())


# # Find the ASCII values of characters in INDIA and then return sum of exponentials of those values.
# # How much Anmol singh paid for his DLF apartment via Capbridge? 
# # What do you know about Don Tapscott and Anthony Williams?
# # What is the relationship between Gensol and Go-Auto?
# # which course are we teaching on Canvas LMS?
# # Summarize this page: https://theschoolof.ai/
# # What is the log value of the amount that Anmol singh paid for his DLF apartment via Capbridge? 