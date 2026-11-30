import sys
import subprocess
import importlib.util

_REQUIRED_PACKAGES = ["flask", "requests", "jinja2"]
for _pkg in _REQUIRED_PACKAGES:
    if importlib.util.find_spec(_pkg) is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", _pkg])

import os
import re
import json
import socket
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib.parse import quote_plus
from flask import Flask, request, jsonify, render_template, send_from_directory
from jinja2 import FileSystemLoader

CACHE_FILE = os.path.join(os.path.dirname(__file__), ".auth_cache.json")

EXCLUDE_WORDS = {
    'dan', 'yang', 'dari', 'pada', 'atau', 'dengan', 'untuk', 'jalan', 'jln', 'jl',
    'gang', 'blok', 'nomor', 'no', 'rt', 'rw', 'kab', 'kec', 'kel', 'prov', 'kota',
    'kabupaten', 'kecamatan', 'kelurahan', 'desa', 'pt', 'cv', 'tbk', 'ud', 'fa'
}

def normalize_text(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', (text or '').lower())).strip()

def tokenize_text(text):
    norm = normalize_text(text)
    if not norm:
        return []
    return list(dict.fromkeys([t for t in norm.split() if len(t) > 2 and t not in EXCLUDE_WORDS]))

def token_overlap_ratio(src_tokens, tgt_tokens):
    if not src_tokens or not tgt_tokens:
        return 0.0
    tgt_set = set(tgt_tokens)
    return sum(1 for t in src_tokens if t in tgt_set) / max(len(src_tokens), 1)

def calculate_similarity_score(candidate, to_match):
    m_name = normalize_text(to_match.get("nama"))
    c_name = normalize_text(candidate.get("nama"))
    m_addr = normalize_text(to_match.get("alamat"))
    c_addr = normalize_text(candidate.get("alamat"))
    score = 0

    if m_name and c_name:
        if m_name == c_name:
            score += 100
        elif m_name in c_name or c_name in m_name:
            score += 72
        score += round(token_overlap_ratio(tokenize_text(m_name), tokenize_text(c_name)) * 55)

    if m_addr and c_addr:
        if m_addr == c_addr:
            score += 45
        elif m_addr in c_addr or c_addr in m_addr:
            score += 28
        score += round(token_overlap_ratio(tokenize_text(m_addr), tokenize_text(c_addr)) * 28)

    if candidate.get("kdkec") and candidate.get("kdkec") == to_match.get("kdkec"):
        score += 16
    if candidate.get("kdkab") and candidate.get("kdkab") == to_match.get("kdkab"):
        score += 10
    if candidate.get("kdprov") and candidate.get("kdprov") == to_match.get("kdprov"):
        score += 6

    return score

def find_recommended_index(candidates, to_match):
    rec_idx = None
    rec_score = 0
    rec_is_active = False

    for idx, c in enumerate(candidates):
        score = calculate_similarity_score(c, to_match)
        is_active = (c.get("status_perusahaan") or "").upper() == "AKTIF"

        if score < 35:
            continue

        should_pick = (
            rec_idx is None or
            (is_active and not rec_is_active) or
            (is_active == rec_is_active and score > rec_score)
        )

        if should_pick:
            rec_idx = idx
            rec_score = score
            rec_is_active = is_active

    return rec_idx, rec_score

def parse_alamat_sls(alamat_raw):
    if not alamat_raw:
        return "-", "-"
    if "| subsls :" in alamat_raw:
        p = alamat_raw.split("| subsls :", 1)
        return p[0].strip(), p[1].strip()
    elif "|" in alamat_raw:
        p = alamat_raw.split("|", 1)
        return p[0].strip(), p[1].strip()
    return alamat_raw.strip(), "-"

def get_wilayah_badge(c, to_match):
    if c.get("kddesa") and c.get("kddesa") == to_match.get("kddesa") and \
       c.get("kdkec") and c.get("kdkec") == to_match.get("kdkec"):
        return "[Desa Sama]", "#38bdf8"
    if c.get("kdkec") and c.get("kdkec") == to_match.get("kdkec"):
        return "[Kec Sama]", "#a855f7"
    if c.get("kdkab") and c.get("kdkab") == to_match.get("kdkab"):
        return "[Kab Sama]", "#94a3b8"
    return "[Beda Wilayah]", "#64748b"

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class MatchManager:
    def __init__(self):
        self.session = None
        self.current_user = None
        self.matching_csrf = None
        self.kegiatan_id = "36"
        self.base_url = None
        self.data_url = None
        self.current_data = None
        self.current_candidates = []
        self.rec_idx = None
        self.rec_score = 0
        self.prefetched_data = None
        self.is_busy = False
        self.lock = threading.Lock()

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_cache(self, username, password, kegiatan_id="36"):
        data = self.load_cache()
        if "accounts" not in data:
            data["accounts"] = {}
        data["accounts"][username] = password
        data["last_kegiatan"] = kegiatan_id
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def login(self, username, password, kegiatan_id="36"):
        username = str(username).strip()
        password = str(password).strip()
        kegiatan_id = str(kegiatan_id).strip()

        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=2)
        s.mount("https://", adapter)
        s.mount("http://", adapter)

        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36 OPR/139.0.0.0",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive"
        })

        login_url = "https://matchapro.web.bps.go.id/login"
        res_get = s.get(login_url, timeout=12)
        res_get.raise_for_status()

        token_match = re.search(r'name="_token"\s+value="([^"]+)"', res_get.text) or \
                      re.search(r'<meta name="csrf-token"\s+content="([^"]+)">', res_get.text)
        if not token_match:
            raise ValueError("CSRF Token tidak ditemukan pada halaman login.")

        csrf_token = token_match.group(1)
        payload = {"_token": csrf_token, "username": username, "password_default": password}
        headers_post = {
            "Origin": "https://matchapro.web.bps.go.id",
            "Referer": login_url,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        res_post = s.post(login_url, data=payload, headers=headers_post, timeout=12)
        res_post.raise_for_status()

        if "logout" not in res_post.text.lower() and res_post.url == login_url:
            error_match = re.search(r'class="invalid-feedback"[^>]*>\s*<strong>([^<]+)</strong>', res_post.text) or \
                          re.search(r'class="alert[^"]*"[^>]*>([^<]+)</div>', res_post.text)
            err_detail = error_match.group(1).strip() if error_match else "Kredensial ditolak oleh server BPS."
            raise ValueError(err_detail)

        self.save_cache(username, password, kegiatan_id)

        self.session = s
        self.current_user = username
        self.kegiatan_id = kegiatan_id
        self.base_url = f"https://matchapro.web.bps.go.id/matching/kegiatan/{kegiatan_id}"
        self.data_url = f"{self.base_url}/data"

        res_page = s.get(self.base_url, timeout=12)
        res_page.raise_for_status()
        match_csrf = re.search(r'name="_token"\s+value="([^"]+)"', res_page.text) or \
                     re.search(r'<meta name="csrf-token"\s+content="([^"]+)">', res_page.text)
        self.matching_csrf = match_csrf.group(1) if match_csrf else csrf_token
        self.prefetched_data = None
        return True

    def fetch_data(self, skip_id=""):
        headers = {
            "Origin": "https://matchapro.web.bps.go.id",
            "Referer": self.base_url,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        payload = {"_token": self.matching_csrf, "skip_data": skip_id}
        r = self.session.post(self.data_url, data=payload, headers=headers, timeout=12)
        r.raise_for_status()
        return r.json()

    def start_prefetch(self, skip_id):
        self.prefetched_data = None
        if not skip_id:
            return

        def _bg():
            try:
                res = self.fetch_data(skip_id)
                if res.get("status") == "success" and res.get("to_match"):
                    self.prefetched_data = res
            except Exception:
                self.prefetched_data = None

        threading.Thread(target=_bg, daemon=True).start()

    def get_current_or_next(self):
        with self.lock:
            if self.prefetched_data:
                data = self.prefetched_data
                self.prefetched_data = None
            else:
                data = self.fetch_data()

            to_match = data.get("to_match") if isinstance(data, dict) else None
            if data.get("status") == "success" and isinstance(to_match, dict) and to_match.get("id_table"):
                candidates = data.get("to_possible", [])
                rec_idx, rec_score = find_recommended_index(candidates, to_match)

                self.current_data = to_match
                self.current_candidates = candidates
                self.rec_idx = rec_idx
                self.rec_score = rec_score

                # Trigger prefetch antrean berikutnya
                self.start_prefetch(to_match.get("id_table"))
            else:
                self.current_data = None
                self.current_candidates = []
                self.rec_idx = None
                self.rec_score = 0
                if isinstance(data, dict):
                    data["to_match"] = None
            return data

    def submit_decision(self, status, idsbr=None):
        if not self.current_data or not self.current_data.get("id_table"):
            return {"status": "success", "message": "Semua data selesai dipadankan!", "to_match": None}

        to_match_id = self.current_data.get("id_table")

        def _async_post():
            try:
                headers = {
                    "Origin": "https://matchapro.web.bps.go.id",
                    "Referer": self.base_url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                }
                payload = {"_token": self.matching_csrf, "to_match_id": to_match_id, "status": status}
                if idsbr is not None:
                    payload["idsbr"] = idsbr
                self.session.post(self.base_url, data=payload, headers=headers, timeout=12)
            except Exception as e:
                print(f"[ERROR SUBMIT] ID {to_match_id}: {e}")

        # Jalankan simpan di background
        threading.Thread(target=_async_post, daemon=True).start()

        # Ambil item berikutnya (instan jika prefetch siap)
        return self.get_current_or_next()

    def skip_current(self):
        if not self.current_data or not self.current_data.get("id_table"):
            return {"status": "success", "message": "Semua data selesai dipadankan!", "to_match": None}
        skip_id = self.current_data.get("id_table")
        with self.lock:
            if self.prefetched_data:
                data = self.prefetched_data
                self.prefetched_data = None
            else:
                data = self.fetch_data(skip_id=skip_id)

            to_match = data.get("to_match") if isinstance(data, dict) else None
            if data.get("status") == "success" and isinstance(to_match, dict) and to_match.get("id_table"):
                candidates = data.get("to_possible", [])
                rec_idx, rec_score = find_recommended_index(candidates, to_match)
                self.current_data = to_match
                self.current_candidates = candidates
                self.rec_idx = rec_idx
                self.rec_score = rec_score
                self.start_prefetch(to_match.get("id_table"))
            else:
                self.current_data = None
                self.current_candidates = []
                self.rec_idx = None
                self.rec_score = 0
                if isinstance(data, dict):
                    data["to_match"] = None
            return data


mgr = MatchManager()
app = Flask(__name__, static_folder="static", static_url_path="")
app.jinja_loader = FileSystemLoader(["templates", "."])


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")

@app.route("/icon.svg")
def app_icon():
    return send_from_directory("static", "icon.svg", mimetype="image/svg+xml")

@app.route("/style.css")
def css_style():
    return send_from_directory("static", "style.css", mimetype="text/css")

@app.route("/app.js")
def js_app():
    return send_from_directory("static", "app.js", mimetype="application/javascript")

@app.route("/api/cache")
def api_cache():
    return jsonify(mgr.load_cache())

@app.route("/api/login", methods=["POST"])
def api_login():
    req = request.get_json() or {}
    user = req.get("username", "")
    pwd = req.get("password", "")
    keg = req.get("kegiatan_id", "36")
    try:
        mgr.login(user, pwd, keg)
        return jsonify({"status": "success", "username": mgr.current_user})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/data")
def api_data():
    if not mgr.session:
        return jsonify({"status": "need_login"})

    try:
        data = mgr.get_current_or_next()
        to_m = data.get("to_match") if isinstance(data, dict) else None
        if data.get("status") == "success" and isinstance(to_m, dict) and to_m.get("id_table"):
            data["rec_idx"] = mgr.rec_idx
            data["rec_score"] = mgr.rec_score
        else:
            if isinstance(data, dict):
                data["to_match"] = None
        if isinstance(data, dict):
            data["current_user"] = mgr.current_user
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/submit", methods=["POST"])
def api_submit():
    req = request.get_json() or {}
    status = req.get("status", "UNMATCH")
    idsbr = req.get("idsbr")
    try:
        data = mgr.submit_decision(status, idsbr)
        to_m = data.get("to_match") if isinstance(data, dict) else None
        if data.get("status") == "success" and isinstance(to_m, dict) and to_m.get("id_table"):
            data["rec_idx"] = mgr.rec_idx
            data["rec_score"] = mgr.rec_score
        else:
            if isinstance(data, dict):
                data["to_match"] = None
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/skip", methods=["POST"])
def api_skip():
    try:
        data = mgr.skip_current()
        to_m = data.get("to_match") if isinstance(data, dict) else None
        if data.get("status") == "success" and isinstance(to_m, dict) and to_m.get("id_table"):
            data["rec_idx"] = mgr.rec_idx
            data["rec_score"] = mgr.rec_score
        else:
            if isinstance(data, dict):
                data["to_match"] = None
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 5000
    print("\n" + "=" * 65)
    print("  MATCHANEE PWA SERVER BERJALAN (MODULAR)")
    print("=" * 65)
    print(f"  Akses dari PC           : http://localhost:{port}")
    print(f"  Akses dari Tablet Huawei: http://{local_ip}:{port}")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
