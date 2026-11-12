"""Loopback-only offline preview. Run: python -m location_lab.next_stop_web --queue PATH."""
import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .next_stop import NextStopController, load_queue
from .progress_journal import JournalError

PAGE = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Location Lab · 下一站</title><style>
body{font:18px system-ui;background:#101b25;color:#eef6ff;max-width:680px;margin:40px auto;padding:20px}section{background:#1e3040;border-radius:18px;padding:24px;margin:18px 0}button{font:inherit;padding:14px;border-radius:12px;border:0;margin:6px;cursor:pointer}#next{background:#90e6bd;width:100%;font-size:26px}button:disabled{opacity:.4;cursor:not-allowed}small{color:#bfd0dd}h2{font-size:20px}#notice{min-height:28px}</style>
<h1>下一站</h1><p>離線演練 · 未連接 iPhone</p><small>所有操作僅影響記憶體。雲端無法直接存取 Mac 的 USB；此頁不是手機遠端控制。</small>
<section><div id="progress"></div><h2>目前模擬站點</h2><div id="current"></div><h2>下一站</h2><div id="upcoming"></div><p id="address"></p><button id="next" disabled>下一個</button></section>
<p id="state"></p><p id="notice" role="status"></p>
<button id="connect_mock">啟用離線模擬</button><button id="clear">清除／復原（僅模擬）</button><button id="disconnect_mock">模擬斷線</button>
<p><small>啟用後先清除未知狀態，再按下一個。每次只前進一站，不自動播放；清除不重設進度，也不表示實體定位已恢復。使用私人 journal 時重啟保留進度，但須重新啟用與清除；不自動重放。</small></p>
<script>
const token='__TOKEN__';let state=null,busy=false;
const labels={unknown:'未知，請先清除／復原',cleared:'已清除（僅模擬）',active:'模擬中',idle:'尚未開始'};
const errors={ok:'操作完成（僅模擬）',stale_command:'畫面已過期，請確認新狀態後再操作',wrong_session:'工作階段已更換，請重新整理頁面',disconnected:'離線模擬未啟用',recovery_required:'狀態未知，請先清除／復原',end_of_queue:'已到最後一站',backend_failed:'操作失敗，狀態未知；請重新啟用並清除／復原',storage_unavailable:'進度儲存不可用，已停止操作，請保留 journal 並檢查',outcome_unknown:'操作結果未知，已停止操作，請檢查進度並明確復原',request_id_conflict:'重複請求有衝突'};
function controls(){document.querySelectorAll('button').forEach(b=>b.disabled=busy||!state||state.storage_fault);if(state&&!state.storage_fault){document.getElementById('next').disabled=busy||!state.can_next;document.getElementById('clear').disabled=busy||!state.mock_connected;document.getElementById('connect_mock').disabled=busy||state.mock_connected;document.getElementById('disconnect_mock').disabled=busy||!state.mock_connected;}}
async function refresh(){const r=await fetch('/api/state',{headers:{'X-Preview-Token':token},cache:'no-store'});if(!r.ok)throw Error();state=await r.json();document.getElementById('progress').textContent=`進度 ${state.completed} / ${state.total} · ${state.durable_progress?'已啟用私人進度儲存':'未儲存，重啟歸零'}`;document.getElementById('current').textContent=state.current?.name||'尚無已確認的模擬站點';document.getElementById('upcoming').textContent=state.next?.name||'全部完成';document.getElementById('address').textContent=state.next?.address||'';document.getElementById('state').textContent=(state.mock_connected?'離線模擬已啟用 · ':'離線模擬未啟用 · ')+labels[state.state];}
async function act(action){if(busy||!state)return;busy=true;controls();const req={request_id:crypto.randomUUID(),epoch:state.epoch,version:state.version,action};try{const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Preview-Token':token},body:JSON.stringify(req)});if(!r.ok)throw Error();const result=await r.json();document.getElementById('notice').textContent=errors[result.code]||'操作未完成';await refresh();}catch{state=null;document.getElementById('notice').textContent='連線或結果未知，已停用操作。重新整理確認狀態；不會自動重試。';}finally{busy=false;controls();}}
document.querySelectorAll('button').forEach(b=>{b.onclick=e=>{if(e.detail>1)return;act(b.id);};b.onkeydown=e=>{if(e.repeat&&(e.key==='Enter'||e.key===' '))e.preventDefault();};});refresh().catch(()=>{state=null;document.getElementById('notice').textContent='無法讀取狀態，請重新整理';}).finally(controls);
</script></html>'''


def make_server(controller, port=0):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No queue names, coordinates, tokens or request logs.

        def reply(self, status, content, kind="application/json"):
            body = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, auth=False):
            host = "127.0.0.1:" + str(self.server.server_port)
            if self.headers.get("Host") != host or self.headers.get("Origin") not in (None, "http://" + host):
                self.reply(403, '{}')
                return False
            if auth and not secrets.compare_digest(self.headers.get("X-Preview-Token", ""), token):
                self.reply(403, '{}')
                return False
            return True

        def do_GET(self):
            if not self.allowed(auth=self.path != "/"):
                return
            if self.path == "/":
                self.reply(200, PAGE.replace("__TOKEN__", token), "text/html")
            elif self.path == "/api/state":
                self.reply(200, json.dumps(controller.snapshot(), ensure_ascii=False))
            else:
                self.reply(404, '{}')

        def do_POST(self):
            if not self.allowed(auth=True):
                return
            if self.path != "/api/command":
                self.reply(404, '{}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096 or self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
                    raise ValueError()
                self.connection.settimeout(3)
                request = json.loads(self.rfile.read(length))
            except (ValueError, OSError):
                self.reply(400, '{}')
                return
            self.reply(200, json.dumps(controller.execute(request)))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline loopback preview; no device connection")
    parser.add_argument("--queue", required=True, help="explicit private queue JSON outside repository")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--journal", help="private progress path in a mode-0700 directory outside repo")
    parser.add_argument("--backend", choices=("memory", "fake-device"), default="memory")
    parser.add_argument("--device", help="explicit synthetic identity; required for fake-device")
    args = parser.parse_args(argv)
    backend = None
    controller = None
    identity = "memory-mock"
    if args.backend == "fake-device":
        if not args.device:
            parser.error("fake-device requires an explicit --device synthetic identity")
        from .device_boundary import FakeDeviceTransport, SelectedDeviceBackend
        identity = args.device
        try:
            backend = SelectedDeviceBackend(FakeDeviceTransport(identity=identity), identity)
        except (ValueError, RuntimeError, OSError):
            parser.error("fake device owner unavailable; no device operation performed")
    elif args.device:
        parser.error("--device requires --backend fake-device")
    try:
        controller = NextStopController(load_queue(args.queue), backend=backend, journal_path=args.journal, device_identity=identity)
        server = make_server(controller, args.port)
    except (ValueError, OSError, KeyError, JournalError):
        if controller is not None:
            controller.close()
        elif backend is not None:
            backend.close()
        parser.error("cannot load queue or bind loopback preview; verify private path, schema and port")
    print(f"Offline mock only; no iPhone connection. http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
