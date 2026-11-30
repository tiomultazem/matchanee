import os
import re
import json
import threading
import webbrowser
from urllib.parse import quote_plus
import tkinter as tk
import requests
from requests.adapters import HTTPAdapter
import customtkinter as ctk

CACHE_FILE = os.path.join(os.path.dirname(__file__), ".auth_cache.json")

# Spesifikasi Baris Kompak (Tinggi terukur & efisien)
ROW_SPECS = [
    ("HEADER",     "AKSI / NO",        44),
    ("NAMA",       "1. NAMA",          42),
    ("ALAMAT",     "2. ALAMAT",        40),
    ("SLS",        "3. SLS / RT",      26),
    ("DESA",       "4. DESA / KEL",    26),
    ("KECAMATAN",  "5. KECAMATAN",     26),
    ("KABUPATEN",  "6. KABUPATEN",     26),
    ("PROVINSI",   "7. PROVINSI",      26),
    ("KECOCOKAN",  "8. KECOCOKAN",     28),
    ("STATUS",     "9. STATUS",        28),
    ("IDSBR",      "10. IDSBR / ID",   26),
    ("PENCARIAN",  "11. GOOGLE",       32),
]
TOTAL_H = sum(h for _, _, h in ROW_SPECS)  # 370 px

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

def get_wilayah_badge(candidate, to_match):
    c_desa = candidate.get("kddesa") or ""
    m_desa = to_match.get("kddesa") or ""
    c_kec  = candidate.get("kdkec") or ""
    m_kec  = to_match.get("kdkec") or ""
    c_kab  = candidate.get("kdkab") or ""
    m_kab  = to_match.get("kdkab") or ""

    if c_desa and m_desa and c_desa == m_desa and c_kec == m_kec and c_kab == m_kab:
        return "DESA SAMA", "#22c55e"
    elif c_kec and m_kec and c_kec == m_kec and c_kab == m_kab:
        return "KEC SAMA", "#06b6d4"
    elif c_kab and m_kab and c_kab == m_kab:
        return "KAB SAMA", "#eab308"
    return "BEDA WIL", "#64748b"


class AuthCache:
    @staticmethod
    def load():
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @staticmethod
    def save(username, password, kegiatan_id="36"):
        data = AuthCache.load()
        if "accounts" not in data:
            data["accounts"] = {}
        data["accounts"][username] = password
        data["last_user"] = username
        data["last_kegiatan"] = kegiatan_id
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


class MatchaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Matchanee - Desktop Matching App")
        self.geometry("1200x495")
        self.minsize(980, 485)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.session = None
        self.matching_csrf = None
        self.kegiatan_id = "36"
        self.base_url = None
        self.data_url = None
        self.current_data = None
        self.current_candidates = []
        self.rec_idx = None
        self.skip_id = ""
        self.is_busy = False
        self.prefetched_data = None

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)

        self.bind_events()
        self.show_login_screen()

    def bind_events(self):
        self.bind("<Return>", lambda e: self.on_hotkey_match_recommended())
        for i in range(1, 10):
            self.bind(str(i), lambda e, idx=i: self.on_hotkey_number(idx))
        self.bind("0", lambda e: self.on_hotkey_number(10))
        self.bind("u", lambda e: self.on_action_unmatch())
        self.bind("U", lambda e: self.on_action_unmatch())
        self.bind("s", lambda e: self.on_action_skip())
        self.bind("S", lambda e: self.on_action_skip())
        self.bind("i", lambda e: self.on_action_ignore())
        self.bind("I", lambda e: self.on_action_ignore())

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    # ---------------- LOGIN SCREEN ---------------- #
    def show_login_screen(self):
        self.clear_container()
        cache = AuthCache.load()
        accounts = cache.get("accounts", {})
        last_user = cache.get("last_user", "")
        last_kegiatan = cache.get("last_kegiatan", "36")

        login_box = ctk.CTkFrame(self.container, width=400, corner_radius=12)
        login_box.place(relx=0.5, rely=0.5, anchor="center")

        title = ctk.CTkLabel(login_box, text="MATCHANEE LOGIN", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(padx=30, pady=(26, 6))

        sub = ctk.CTkLabel(login_box, text="Desktop Matching App", text_color="#94a3b8", font=ctk.CTkFont(size=11))
        sub.pack(padx=30, pady=(0, 18))

        ctk.CTkLabel(login_box, text="Username:", anchor="w", font=ctk.CTkFont(size=11, weight="bold")).pack(fill="x", padx=30, pady=(4, 2))
        user_list = list(accounts.keys()) if accounts else [""]
        self.entry_user = ctk.CTkComboBox(login_box, values=user_list, command=self.on_user_select, height=34)
        self.entry_user.set(last_user if last_user else (user_list[0] if user_list else ""))
        self.entry_user.pack(fill="x", padx=30, pady=(0, 10))

        ctk.CTkLabel(login_box, text="Password:", anchor="w", font=ctk.CTkFont(size=11, weight="bold")).pack(fill="x", padx=30, pady=(4, 2))
        self.entry_pass = ctk.CTkEntry(login_box, show="•", height=34)
        self.entry_pass.pack(fill="x", padx=30, pady=(0, 10))

        if last_user and last_user in accounts:
            self.entry_pass.insert(0, accounts[last_user])

        ctk.CTkLabel(login_box, text="ID Kegiatan:", anchor="w", font=ctk.CTkFont(size=11, weight="bold")).pack(fill="x", padx=30, pady=(4, 2))
        self.entry_kegiatan = ctk.CTkEntry(login_box, height=34)
        self.entry_kegiatan.insert(0, str(last_kegiatan))
        self.entry_kegiatan.pack(fill="x", padx=30, pady=(0, 18))

        self.btn_login = ctk.CTkButton(login_box, text="Masuk ke MatchaPro", font=ctk.CTkFont(size=13, weight="bold"), height=38, command=self.start_login)
        self.btn_login.pack(fill="x", padx=30, pady=(0, 10))

        self.lbl_login_status = ctk.CTkLabel(login_box, text="", font=ctk.CTkFont(size=11))
        self.lbl_login_status.pack(padx=30, pady=(0, 20))

    def on_user_select(self, selected_user):
        cache = AuthCache.load()
        acc = cache.get("accounts", {})
        if selected_user in acc:
            self.entry_pass.delete(0, "end")
            self.entry_pass.insert(0, acc[selected_user])

    def start_login(self):
        user = self.entry_user.get().strip()
        pwd = self.entry_pass.get().strip()
        keg_id = self.entry_kegiatan.get().strip()

        if not user or not pwd:
            self.lbl_login_status.configure(text="Username dan password wajib diisi!", text_color="#ef4444")
            return

        self.btn_login.configure(state="disabled", text="Memverifikasi...")
        self.lbl_login_status.configure(text="Menghubungkan ke server...", text_color="#38bdf8")

        threading.Thread(target=self._async_login, args=(user, pwd, keg_id), daemon=True).start()

    def _async_login(self, user, pwd, keg_id):
        try:
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
                raise ValueError("Token CSRF gagal diekstraksi.")

            csrf_token = token_match.group(1)
            payload = {"_token": csrf_token, "username": user, "password_default": pwd}
            headers_post = {
                "Origin": "https://matchapro.web.bps.go.id",
                "Referer": login_url,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            res_post = s.post(login_url, data=payload, headers=headers_post, timeout=12)
            res_post.raise_for_status()

            if "logout" not in res_post.text.lower() and res_post.url == login_url:
                raise ValueError("Kredensial ditolak.")

            AuthCache.save(user, pwd, keg_id)

            self.session = s
            self.kegiatan_id = keg_id
            self.base_url = f"https://matchapro.web.bps.go.id/matching/kegiatan/{keg_id}"
            self.data_url = f"{self.base_url}/data"

            res_page = s.get(self.base_url, timeout=12)
            res_page.raise_for_status()
            match_csrf = re.search(r'name="_token"\s+value="([^"]+)"', res_page.text) or \
                         re.search(r'<meta name="csrf-token"\s+content="([^"]+)">', res_page.text)
            self.matching_csrf = match_csrf.group(1) if match_csrf else csrf_token

            self.after(0, self.show_matching_screen)

        except Exception as e:
            self.after(0, lambda: self._on_login_failed(str(e)))

    def _on_login_failed(self, err_msg):
        self.btn_login.configure(state="normal", text="Masuk ke MatchaPro")
        self.lbl_login_status.configure(text=f"Login Gagal: {err_msg}", text_color="#ef4444")

    # ---------------- MATCHING SCREEN ---------------- #
    def show_matching_screen(self):
        self.clear_container()

        # Top Bar
        top_bar = ctk.CTkFrame(self.container, height=44, corner_radius=0)
        top_bar.pack(fill="x", side="top")

        lbl_keg = ctk.CTkLabel(top_bar, text=f"Kegiatan #{self.kegiatan_id}", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_keg.pack(side="left", padx=14)

        self.lbl_status = ctk.CTkLabel(top_bar, text="Siap.", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        self.lbl_status.pack(side="left", padx=8)

        btn_logout = ctk.CTkButton(top_bar, text="Ganti Akun", width=80, height=26, fg_color="#475569", hover_color="#334155", font=ctk.CTkFont(size=11), command=self.show_login_screen)
        btn_logout.pack(side="right", padx=12)

        btn_refresh = ctk.CTkButton(top_bar, text="Refresh", width=70, height=26, font=ctk.CTkFont(size=11), command=self.fetch_initial_data)
        btn_refresh.pack(side="right", padx=(0, 4))

        # Bottom Bar
        bottom_bar = ctk.CTkFrame(self.container, height=44, corner_radius=0, fg_color="#090d16")
        bottom_bar.pack(fill="x", side="bottom")

        btn_unmatch = ctk.CTkButton(bottom_bar, text="[u] Unmatch", width=95, height=28, fg_color="#ea580c", hover_color="#c2410c", font=ctk.CTkFont(size=11, weight="bold"), command=self.on_action_unmatch)
        btn_unmatch.pack(side="left", padx=(12, 4), pady=6)

        btn_skip = ctk.CTkButton(bottom_bar, text="[s] Skip", width=75, height=28, fg_color="#475569", hover_color="#334155", font=ctk.CTkFont(size=11), command=self.on_action_skip)
        btn_skip.pack(side="left", padx=4, pady=6)

        btn_ignore = ctk.CTkButton(bottom_bar, text="[i] Ignore", width=75, height=28, fg_color="#dc2626", hover_color="#b91c1c", font=ctk.CTkFont(size=11), command=self.on_action_ignore)
        btn_ignore.pack(side="left", padx=4, pady=6)

        self.lbl_hotkey_hint = ctk.CTkLabel(bottom_bar, text="[Enter]: Match Rekomendasi | [1-9]: Match Nomor | Scroll Mouse: Geser Horizontal Cepat",
                                            font=ctk.CTkFont(size=11), text_color="#94a3b8")
        self.lbl_hotkey_hint.pack(side="right", padx=16)

        # Horizontal Scrollbar (ditaruh tepat di atas bottom_bar)
        self.scroll_x = ctk.CTkScrollbar(self.container, orientation="horizontal", height=12)
        self.scroll_x.pack(fill="x", side="bottom", padx=6, pady=(1, 3))

        # Workspace Container (Fit to Table)
        self.table_area = tk.Frame(self.container, bg="#090d16", height=TOTAL_H)
        self.table_area.pack(fill="both", expand=True, padx=6, pady=(4, 1))

        # Pinned Frame: Left (Label + Target)
        self.pinned_frame = tk.Frame(self.table_area, bg="#0f172a", width=290, height=TOTAL_H, bd=1, relief="solid")
        self.pinned_frame.pack(side="left", fill="y", padx=(0, 4))
        self.pinned_frame.pack_propagate(False)

        # Horizontal Scroll Area using Tkinter Canvas (60 FPS Smooth)
        self.canvas_scroll = tk.Canvas(self.table_area, bg="#090d16", highlightthickness=0, bd=0, height=TOTAL_H, xscrollincrement=20)
        self.canvas_scroll.pack(side="left", fill="both", expand=True)
        self.scroll_x.configure(command=self.canvas_scroll.xview)
        self.canvas_scroll.configure(xscrollcommand=self.scroll_x.set)

        self.inner_scroll_frame = tk.Frame(self.canvas_scroll, bg="#090d16", height=TOTAL_H)
        self.canvas_win = self.canvas_scroll.create_window((0, 0), window=self.inner_scroll_frame, anchor="nw", height=TOTAL_H)

        self.inner_scroll_frame.bind("<Configure>", lambda e: self.canvas_scroll.configure(scrollregion=self.canvas_scroll.bbox("all")))

        # Mousewheel binding langsung ke Horizontal Scroll (Instan & Mulus)
        self.canvas_scroll.bind_all("<MouseWheel>", self._on_mousewheel_horizontal)

        self.fetch_initial_data()

    def _on_mousewheel_horizontal(self, event):
        # Gerakkan horizontal kanvas langsung saat mousewheel diputar
        if self.canvas_scroll.winfo_exists():
            delta = -1 * (event.delta // 120) * 3
            self.canvas_scroll.xview_scroll(delta, "units")

    def fetch_initial_data(self):
        if self.is_busy:
            return
        self.is_busy = True
        self.prefetched_data = None
        self.lbl_status.configure(text="Memuat antrean...", text_color="#38bdf8")
        threading.Thread(target=self._async_fetch_worker, daemon=True).start()

    def _async_fetch_worker(self):
        try:
            headers = {
                "Origin": "https://matchapro.web.bps.go.id",
                "Referer": self.base_url,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            payload = {"_token": self.matching_csrf, "skip_data": self.skip_id}
            self.skip_id = ""

            r = self.session.post(self.data_url, data=payload, headers=headers, timeout=12)
            r.raise_for_status()
            data = r.json()

            self.after(0, lambda: self._apply_new_data(data))
        except Exception as e:
            self.after(0, lambda: self._on_action_error(f"Gagal memuat: {e}"))

    def _start_prefetch(self, skip_id):
        self.prefetched_data = None
        if not skip_id:
            return
        threading.Thread(target=self._async_prefetch_worker, args=(skip_id,), daemon=True).start()

    def _async_prefetch_worker(self, skip_id):
        try:
            headers = {
                "Origin": "https://matchapro.web.bps.go.id",
                "Referer": self.base_url,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            payload = {"_token": self.matching_csrf, "skip_data": skip_id}
            r = self.session.post(self.data_url, data=payload, headers=headers, timeout=12)
            r.raise_for_status()
            res = r.json()
            if res.get("status") == "success" and res.get("to_match"):
                self.prefetched_data = res
        except Exception:
            self.prefetched_data = None

    def submit_and_fetch_next(self, status, idsbr=None, cand_idx=None):
        if self.is_busy or not self.current_data:
            return

        to_match_id = self.current_data.get("id_table")
        label = f"Match #{cand_idx}" if status == "MATCH" else status

        # PREFETCH HIT: Tampilkan antrean berikutnya seketika (0 ms)!
        if self.prefetched_data is not None:
            next_data = self.prefetched_data
            self.prefetched_data = None

            self._apply_new_data(next_data)
            self.lbl_status.configure(text=f"Tersimpan {label} (Instan) | ID: {next_data.get('to_match', {}).get('id_table')}", text_color="#22c55e")
            threading.Thread(target=self._async_submit_only, args=(to_match_id, status, idsbr), daemon=True).start()
        else:
            # CACHE MISS: Tunggu sekuensial jika user klik sebelum prefetch tuntas
            self.is_busy = True
            self.lbl_status.configure(text=f"Menyimpan {label} & mengambil antrean...", text_color="#eab308")
            threading.Thread(target=self._pipeline_submit_fetch, args=(to_match_id, status, idsbr), daemon=True).start()

    def _async_submit_only(self, to_match_id, status, idsbr):
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

            res = self.session.post(self.base_url, data=payload, headers=headers, timeout=12)
            res.raise_for_status()
        except Exception as e:
            self.after(0, lambda: self.lbl_status.configure(text=f"Gagal simpan ID {to_match_id}: {e}", text_color="#ef4444"))

    def _pipeline_submit_fetch(self, to_match_id, status, idsbr):
        try:
            headers = {
                "Origin": "https://matchapro.web.bps.go.id",
                "Referer": self.base_url,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }

            # 1. POST Submit
            payload_sub = {"_token": self.matching_csrf, "to_match_id": to_match_id, "status": status}
            if idsbr is not None:
                payload_sub["idsbr"] = idsbr

            res_sub = self.session.post(self.base_url, data=payload_sub, headers=headers, timeout=12)
            res_sub.raise_for_status()

            # 2. POST Fetch Data Berikutnya Seketika
            payload_fetch = {"_token": self.matching_csrf, "skip_data": ""}
            res_fetch = self.session.post(self.data_url, data=payload_fetch, headers=headers, timeout=12)
            res_fetch.raise_for_status()
            data_next = res_fetch.json()

            self.after(0, lambda: self._apply_new_data(data_next))
        except Exception as e:
            self.after(0, lambda: self._on_action_error(f"Error jaringan: {e}"))

    def _on_action_error(self, msg):
        self.is_busy = False
        self.lbl_status.configure(text=msg, text_color="#ef4444")

    def _apply_new_data(self, data):
        self.is_busy = False

        if data.get("status") != "success":
            self.lbl_status.configure(text=f"Respon: {data.get('message')}", text_color="#ef4444")
            return

        to_match = data.get("to_match")
        if not to_match:
            self.lbl_status.configure(text="Semua data selesai dipadankan!", text_color="#22c55e")
            self._render_empty_state()
            return

        self.current_data = to_match
        self.current_candidates = data.get("to_possible", [])
        self.rec_idx, self.rec_score = find_recommended_index(self.current_candidates, to_match)

        self.lbl_status.configure(text=f"Target ID: {to_match.get('id_table')} ({len(self.current_candidates)} kandidat)", text_color="#94a3b8")
        self._render_transposed_compact_grid(to_match, self.current_candidates, self.rec_idx, self.rec_score)

        # Prefetch antrean berikutnya saat user sedang membaca data saat ini
        self._start_prefetch(to_match.get("id_table"))

    def _render_empty_state(self):
        for w in self.pinned_frame.winfo_children(): w.destroy()
        for w in self.inner_scroll_frame.winfo_children(): w.destroy()
        lbl = ctk.CTkLabel(self.pinned_frame, text="Kegiatan selesai.\nTidak ada data tersisa.", font=ctk.CTkFont(size=13, weight="bold"))
        lbl.pack(pady=40, padx=20)

    # ---------------- RENDER GRID TRANSPOSISI RINGKAS & BERGARIS TEGAS ---------------- #
    def _render_transposed_compact_grid(self, to_match, candidates, rec_idx, rec_score):
        for w in self.pinned_frame.winfo_children(): w.destroy()
        for w in self.inner_scroll_frame.winfo_children(): w.destroy()

        # Warna Garis Zebra & Pembatas Tegas (Border)
        BG_ROW = ["#1e293b", "#0f172a"]
        BG_TGT = ["#1e3a5f", "#13233a"]
        BG_CND = ["#1a2234", "#101623"]
        BG_REC = ["#33270f", "#261d0b"]
        BD_COLOR = "#334155"

        # Lebar Kolom Kompak: Memungkinkan 6-7 kandidat terlihat sekaligus
        W_LABEL = 95
        W_TARGET = 195
        W_CAND = 165

        # ---------------- 1. KOLOM LABEL (PINNED) ---------------- #
        col_label = tk.Frame(self.pinned_frame, width=W_LABEL, height=TOTAL_H, bg="#0f172a")
        col_label.pack(side="left", fill="y")
        col_label.pack_propagate(False)

        for r_idx, (r_key, r_label, r_h) in enumerate(ROW_SPECS):
            bg = BG_ROW[r_idx % 2]
            cell = tk.Frame(col_label, height=r_h, bg=bg, highlightbackground=BD_COLOR, highlightthickness=1)
            cell.pack(fill="x")
            cell.pack_propagate(False)

            tk.Label(cell, text=r_label, font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg=bg, anchor="w", padx=6).pack(fill="both", expand=True)

        # ---------------- 2. KOLOM TARGET (PINNED) ---------------- #
        m_alamat, m_sls = parse_alamat_sls(to_match.get("alamat", "-"))
        col_target = tk.Frame(self.pinned_frame, width=W_TARGET, height=TOTAL_H, bg="#0f172a")
        col_target.pack(side="left", fill="y")
        col_target.pack_propagate(False)

        m_q = quote_plus(f"{to_match.get('nama', '')} {m_alamat}")
        target_dict = {
            "HEADER":    f"DATA TARGET (ID: {to_match.get('id_table')})",
            "NAMA":      to_match.get("nama", "-"),
            "ALAMAT":    m_alamat,
            "SLS":       m_sls,
            "DESA":      f"{to_match.get('kddesa', '')} - {to_match.get('nmdesa', '')}",
            "KECAMATAN": f"{to_match.get('kdkec', '')} - {to_match.get('nmkec', '')}",
            "KABUPATEN": f"{to_match.get('kdkab', '')} - {to_match.get('nmkab', '')}",
            "PROVINSI":  f"{to_match.get('kdprov', '')} - {to_match.get('nmprov', '')}",
            "KECOCOKAN": "DATA ACUAN",
            "STATUS":    "PROFILING",
            "IDSBR":     f"TABLE: {to_match.get('id_table')}",
            "PENCARIAN": f"https://www.google.com/search?q={m_q}"
        }

        for r_idx, (r_key, _, r_h) in enumerate(ROW_SPECS):
            bg = BG_TGT[r_idx % 2]
            cell = tk.Frame(col_target, height=r_h, bg=bg, highlightbackground="#1d4ed8", highlightthickness=1)
            cell.pack(fill="x")
            cell.pack_propagate(False)

            val = target_dict[r_key]
            if r_key == "HEADER":
                tk.Label(cell, text=val, font=("Segoe UI", 9, "bold"), fg="#60a5fa", bg=bg, anchor="w", padx=6).pack(fill="both", expand=True)
            elif r_key == "PENCARIAN":
                btn = ctk.CTkButton(cell, text="🔍 Google", height=22, fg_color="#1d4ed8", hover_color="#1e40af", font=ctk.CTkFont(size=10),
                                    command=lambda url=val: webbrowser.open(url))
                btn.pack(fill="x", padx=4, pady=3)
            elif r_key in ("KECOCOKAN", "STATUS"):
                tk.Label(cell, text=val, font=("Segoe UI", 8, "bold"), fg="#bfdbfe", bg="#1e3a8a", padx=4, pady=1).pack(side="left", padx=6)
            else:
                fw = "bold" if r_key == "NAMA" else "normal"
                col = "#f8fafc" if r_key == "NAMA" else "#cbd5e1"
                tk.Label(cell, text=str(val), font=("Segoe UI", 8, fw), fg=col, bg=bg, wraplength=W_TARGET - 14, justify="left", anchor="w", padx=6).pack(fill="both", expand=True)

        # ---------------- 3. KOLOM KANDIDAT BERGULIR HORIZONTAL ---------------- #
        if not candidates:
            empty = tk.Label(self.inner_scroll_frame, text="Tidak ada kandidat padanan ditemukan. Gunakan tombol [u] Unmatch.", font=("Segoe UI", 11), fg="#94a3b8", bg="#090d16", padx=20, pady=20)
            empty.pack(pady=40)
            self.canvas_scroll.itemconfig(self.canvas_win, width=500, height=TOTAL_H)
            self.canvas_scroll.configure(scrollregion=(0, 0, 500, TOTAL_H))
            return

        for idx, c in enumerate(candidates, 1):
            is_rec = (rec_idx is not None and (idx - 1) == rec_idx)
            c_status = (c.get("status_perusahaan") or "AKTIF").upper()
            c_alamat, c_sls = parse_alamat_sls(c.get("alamat", "-"))
            badge_text, badge_color = get_wilayah_badge(c, to_match)

            col_cand = tk.Frame(self.inner_scroll_frame, width=W_CAND, height=TOTAL_H, bg="#090d16")
            col_cand.pack(side="left", fill="y", padx=1)
            col_cand.pack_propagate(False)

            c_q = quote_plus(f"{c.get('nama', '')} {c_alamat}")
            cand_dict = {
                "HEADER":     f"#{idx}" + (f" ★ ({rec_score})" if is_rec else ""),
                "NAMA":       c.get("nama", "-"),
                "ALAMAT":     c_alamat,
                "SLS":        c_sls,
                "DESA":       f"{c.get('kddesa', '')} - {c.get('nmdesa', '')}",
                "KECAMATAN":  f"{c.get('kdkec', '')} - {c.get('nmkec', '')}",
                "KABUPATEN":  f"{c.get('kdkab', '')} - {c.get('nmkab', '')}",
                "PROVINSI":   f"{c.get('kdprov', '')} - {c.get('nmprov', '')}",
                "KECOCOKAN":  badge_text,
                "STATUS":     c_status,
                "IDSBR":      f"IDSBR: {c.get('idsbr', '-')}",
                "PENCARIAN":  f"https://www.google.com/search?q={c_q}"
            }

            for r_idx, (r_key, _, r_h) in enumerate(ROW_SPECS):
                bg = BG_REC[r_idx % 2] if is_rec else BG_CND[r_idx % 2]
                bd = "#eab308" if is_rec else BD_COLOR
                bd_w = 2 if (is_rec and r_key == "HEADER") else 1

                cell = tk.Frame(col_cand, height=r_h, bg=bg, highlightbackground=bd, highlightthickness=bd_w)
                cell.pack(fill="x")
                cell.pack_propagate(False)

                val = cand_dict[r_key]
                if r_key == "HEADER":
                    h_box = tk.Frame(cell, bg=bg)
                    h_box.pack(fill="both", expand=True, padx=4)
                    tk.Label(h_box, text=val, font=("Segoe UI", 9, "bold"), fg="#eab308" if is_rec else "#f8fafc", bg=bg).pack(side="left")

                    btn_m = ctk.CTkButton(h_box, text=f"Pilih #{idx}", width=60, height=22, fg_color="#16a34a", hover_color="#15803d", font=ctk.CTkFont(size=10, weight="bold"),
                                          command=lambda c_obj=c, i=idx: self.submit_and_fetch_next("MATCH", c_obj.get("idsbr"), i))
                    btn_m.pack(side="right")
                elif r_key == "PENCARIAN":
                    btn = ctk.CTkButton(cell, text="🔍 Google", height=22, fg_color="#334155", hover_color="#1e293b", font=ctk.CTkFont(size=10),
                                        command=lambda url=val: webbrowser.open(url))
                    btn.pack(fill="x", padx=4, pady=3)
                elif r_key == "KECOCOKAN":
                    tk.Label(cell, text=badge_text, font=("Segoe UI", 8, "bold"), fg=badge_color, bg="#090d16", padx=4, pady=1).pack(side="left", padx=6)
                elif r_key == "STATUS":
                    st_col = "#22c55e" if c_status == "AKTIF" else "#ef4444"
                    tk.Label(cell, text=c_status, font=("Segoe UI", 8, "bold"), fg=st_col, bg="#090d16", padx=4, pady=1).pack(side="left", padx=6)
                else:
                    fw = "bold" if r_key == "NAMA" else "normal"
                    col = "#fde047" if (r_key == "NAMA" and is_rec) else ("#f8fafc" if r_key == "NAMA" else "#cbd5e1")
                    tk.Label(cell, text=str(val), font=("Segoe UI", 8, fw), fg=col, bg=bg, wraplength=W_CAND - 12, justify="left", anchor="w", padx=6).pack(fill="both", expand=True)

        # Update Canvas Window & Scrollregion secara pasti
        total_w = len(candidates) * (W_CAND + 2)
        self.inner_scroll_frame.update_idletasks()
        self.canvas_scroll.itemconfig(self.canvas_win, width=total_w, height=TOTAL_H)
        self.canvas_scroll.configure(scrollregion=(0, 0, total_w, TOTAL_H))
        self.canvas_scroll.xview_moveto(0.0)

    # ---------------- HOTKEYS HANDLER ---------------- #
    def on_hotkey_match_recommended(self):
        if self.rec_idx is not None and self.current_candidates and self.rec_idx < len(self.current_candidates):
            c = self.current_candidates[self.rec_idx]
            self.submit_and_fetch_next("MATCH", c.get("idsbr"), self.rec_idx + 1)

    def on_hotkey_number(self, num):
        idx = num - 1
        if self.current_candidates and 0 <= idx < len(self.current_candidates):
            c = self.current_candidates[idx]
            self.submit_and_fetch_next("MATCH", c.get("idsbr"), num)

    def on_action_unmatch(self):
        self.submit_and_fetch_next("UNMATCH")

    def on_action_skip(self):
        if not self.current_data:
            return
        if self.prefetched_data is not None:
            next_data = self.prefetched_data
            self.prefetched_data = None
            self._apply_new_data(next_data)
            self.lbl_status.configure(text=f"Dilewati | ID: {next_data.get('to_match', {}).get('id_table')}", text_color="#94a3b8")
        else:
            self.skip_id = self.current_data.get("id_table")
            self.fetch_initial_data()

    def on_action_ignore(self):
        self.submit_and_fetch_next("IGNORE")


if __name__ == "__main__":
    app = MatchaApp()
    app.mainloop()
