# -*- coding: utf-8 -*-
"""
小秋看盘 - 本地服务 v2
用法: python dashboard_server.py
打开浏览器访问 http://localhost:8765
所有行情数据由服务端抓取，浏览器不直连外网（无视梯子）
"""
import http.server, json, os, webbrowser, threading, time, urllib.request, re
from concurrent.futures import ThreadPoolExecutor, as_completed

PORT = 8766
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUANT_DIR = os.path.join(BASE_DIR, '量化')

def fetch_tencent(codes):
    """服务端抓取腾讯行情，不走浏览器代理"""
    if isinstance(codes, str):
        codes = [codes]
    results = []
    batches = [codes[i:i+50] for i in range(0, len(codes), 50)]

    for batch in batches:
        url = 'http://qt.gtimg.cn/q=' + ','.join(batch)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            raw = urllib.request.urlopen(req, timeout=10).read().decode('gbk', errors='ignore')
            for line in raw.strip().split(';\n'):
                m = re.search(r'="(.+)"$', line.strip())
                if not m:
                    continue
                f = m.group(1).split('~')
                if len(f) < 40:
                    continue
                results.append({
                    'code': f[2],
                    'name': f[1],
                    'price': float(f[3]) if f[3] else 0,
                    'prevClose': float(f[4]) if f[4] else 0,
                    'open': float(f[5]) if f[5] else 0,
                    'chg': float(f[32]) if f[32] else 0,
                    'high': float(f[33]) if f[33] else 0,
                    'low': float(f[34]) if f[34] else 0,
                    'turnover': float(f[38]) if f[38] else 0,
                    'volumeRatio': float(f[49]) if f[49] else 0,
                    'amount': float(f[37]) if f[37] else 0,
                    'limitUp': float(f[47]) if f[47] else 0,
                })
        except Exception as e:
            print(f'  Fetch error: {e}')
    return results


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith('/api/quotes'):
            self._serve_quotes()
        elif self.path == '/api/position':
            self._serve_json('position')
        elif self.path == '/api/watchlist':
            self._serve_json('watchlist')
        elif self.path == '/' or self.path == '/dashboard':
            self.path = '/dashboard.html'
            super().do_GET()
        else:
            super().do_GET()

    def _serve_quotes(self):
        # /api/quotes?codes=sh600110,sz000970,sh000001
        qs = self.path.split('?')[-1] if '?' in self.path else ''
        params = {}
        for p in qs.split('&'):
            if '=' in p:
                k, v = p.split('=', 1)
                params[k] = v
        codes_str = params.get('codes', '')
        codes = codes_str.split(',') if codes_str else []
        data = fetch_tencent(codes) if codes else []
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self, kind):
        if kind == 'position':
            path = os.path.join(QUANT_DIR, '.position.json')
        else:
            path = os.path.join(QUANT_DIR, '.my_watchlist.json')

        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error(500, str(e))

    def log_message(self, format, *args):
        pass


def main():
    os.chdir(BASE_DIR)
    # 绑定所有网卡，方便手机/平板访问
    server = http.server.HTTPServer(('0.0.0.0', PORT), DashboardHandler)
    print(f'XiaoQiu Dashboard: http://localhost:{PORT}')
    print('  Server fetches all stock data (bypasses proxy)')
    print('  Browser only talks to localhost - no CORS issues')
    print('  Close this window to stop')

    def open_browser():
        time.sleep(0.5)
        webbrowser.open(f'http://localhost:{PORT}')

    threading.Thread(target=open_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nClosed')
        server.shutdown()


if __name__ == '__main__':
    main()
