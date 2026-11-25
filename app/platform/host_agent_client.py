import logging

import aiohttp

from app.config import settings


log = logging.getLogger("ubot.host_agent")


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.host_agent_token}"}


async def get_metrics() -> dict | None:
    if not settings.host_agent_url:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{settings.host_agent_url}/metrics", headers=_headers(), timeout=5
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        log.warning("Host-agent metrics: %s", e)
    return None


async def power_action(action: str) -> tuple[bool, str]:
    if not settings.host_agent_url:
        return False, "host-agent не настроен"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{settings.host_agent_url}/power",
                json={"action": action},
                headers=_headers(),
                timeout=5,
            ) as resp:
                if resp.status == 200:
                    return True, ""
                return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)


async def exec_command(command: str) -> dict:
    if not settings.host_agent_url:
        return {"ok": False, "output": "host-agent не настроен", "exit_code": -1}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{settings.host_agent_url}/exec",
                json={"command": command},
                headers=_headers(),
                timeout=40,
            ) as resp:
                return await resp.json()
    except Exception as e:
        return {"ok": False, "output": str(e), "exit_code": -1}
