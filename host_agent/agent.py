import asyncio
import os
import subprocess

import psutil
from aiohttp import web


TOKEN = os.environ.get("AGENT_TOKEN", "changeme")
SHELL_USER = os.environ.get("SHELL_USER", "ubot-shell")
BIND_HOST = os.environ.get("BIND_HOST", "172.17.0.1")
BIND_PORT = int(os.environ.get("BIND_PORT", "8765"))
ALLOWED_POWER = {"reboot", "shutdown"}


def _auth(request: web.Request) -> bool:
    h = request.headers.get("Authorization", "")
    return h == f"Bearer {TOKEN}"


async def metrics(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.Response(status=401)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        temps = None

    return web.json_response({
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram": {"total": vm.total, "used": vm.used, "percent": vm.percent},
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent},
        "boot_time": psutil.boot_time(),
        "temps": {k: [t.current for t in v] for k, v in (temps or {}).items()},
    })


async def power(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.Response(status=401)
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")
    action = data.get("action")
    if action not in ALLOWED_POWER:
        return web.Response(status=400, text="bad action")
    subprocess.Popen(["systemctl", action])
    return web.json_response({"ok": True})


async def exec_cmd(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.Response(status=401)
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")
    cmd = (data.get("command") or "").strip()
    if not cmd:
        return web.Response(status=400, text="no command")
    try:
        proc = await asyncio.create_subprocess_exec(
            "su", "-", SHELL_USER, "-c", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return web.json_response({
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": stdout.decode(errors="replace")[:4000],
        })
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return web.json_response({"ok": False, "output": "timeout 30s", "exit_code": -1})


app = web.Application()
app.router.add_get("/metrics", metrics)
app.router.add_post("/power", power)
app.router.add_post("/exec", exec_cmd)


if __name__ == "__main__":
    web.run_app(app, host=BIND_HOST, port=BIND_PORT)
