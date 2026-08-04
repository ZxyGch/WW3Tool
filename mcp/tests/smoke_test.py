#!/usr/bin/env python3
"""MCP stdio 协议端到端冒烟测试：initialize → tools/list → tools/call。

用法（仓库根目录）：
    mcp/.venv/bin/python mcp/tests/smoke_test.py
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

proc = subprocess.Popen(
    [sys.executable, "mcp/ww3tool_mcp.py"],
    cwd=REPO_ROOT,
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)

q = queue.Queue()
def _reader():
    while True:
        line = proc.stdout.readline()
        if not line:
            q.put(None)
            return
        q.put(line.strip())
threading.Thread(target=_reader, daemon=True).start()

def send(payload):
    proc.stdin.write((json.dumps(payload) + "\n").encode())
    proc.stdin.flush()

def recv(timeout=90):
    item = q.get(timeout=timeout)
    if item is None:
        raise RuntimeError("server stdout closed")
    return json.loads(item)

def call(method, params, req_id):
    send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    return recv()

r = call("initialize", {
    "protocolVersion": "2024-11-05", "capabilities": {},
    "clientInfo": {"name": "proto-test", "version": "0.1"},
}, 1)
print("[initialize] server:", r["result"]["serverInfo"], "| tools:", r["result"]["capabilities"].get("tools"))
send({"jsonrpc": "2.0", "method": "notifications/initialized"})

r = call("tools/list", {}, 2)
tools = r["result"]["tools"]
print("[tools/list] count:", len(tools))

r = call("tools/call", {"name": "list_commands", "arguments": {}}, 3)
text = r["result"]["content"][0]["text"]
print("[list_commands] lines:", len(text.splitlines()), "| first:", text.splitlines()[0])

r = call("tools/call", {"name": "ww3tool_print_example", "arguments": {}}, 4)
text = r["result"]["content"][0]["text"]
print("[print_example] first line:", text.splitlines()[0])

tmp = tempfile.mkdtemp(prefix="ww3tool_mcp_test_")
wd = os.path.join(tmp, "workdir")
r = call("tools/call", {"name": "ww3tool_workdir", "arguments": {"path": wd}}, 5)
text = r["result"]["content"][0]["text"]
print("[workdir] first line:", text.splitlines()[0])

r = call("tools/call", {"name": "ww3tool_config", "arguments": {"workdir": wd}}, 6)
text = r["result"]["content"][0]["text"]
print("[config] first line:", text.splitlines()[0])

r = call("tools/call", {"name": "ww3tool_validate", "arguments": {"workdir": wd}}, 7)
text = r["result"]["content"][0]["text"]
print("[validate] first line:", text.splitlines()[0])

r = call("tools/call", {"name": "ww3tool_nonexistent", "arguments": {}}, 8)
print("[unknown-tool] isError:", r["result"].get("isError"))

print("\nALL PROTOCOL TESTS PASSED. temp workdir:", wd)
proc.terminate()
