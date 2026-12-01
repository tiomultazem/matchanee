const ROW_SPECS = [
    ["HEADER",     "AKSI / NO",        44],
    ["NAMA",       "1. NAMA",          44],
    ["ALAMAT",     "2. ALAMAT",        38],
    ["SLS",        "3. SLS / RT",      28],
    ["DESA",       "4. DESA / KEL",    28],
    ["KECAMATAN",  "5. KECAMATAN",     28],
    ["KABUPATEN",  "6. KABUPATEN",     28],
    ["PROVINSI",   "7. PROVINSI",      28],
    ["KECOCOKAN",  "8. KECOCOKAN",     30],
    ["STATUS",     "9. STATUS",        30],
    ["IDSBR",      "10. IDSBR / ID",   28],
    ["PENCARIAN",  "11. GOOGLE",       34]
];

let currentData = null;
let currentCandidates = [];
let recIdx = null;

function escapeHTML(str) {
    if (!str) return '';
    return str.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function setStatus(text, color="#94a3b8") {
    const el = document.getElementById('lbl_status');
    if (el) {
        el.innerText = text;
        el.style.color = color;
    }
}

function parseAlamatSls(raw) {
    if (!raw) return ["-", "-"];
    if (raw.includes("| subsls :")) {
        let p = raw.split("| subsls :");
        return [p[0].trim(), p[1].trim()];
    } else if (raw.includes("|")) {
        let p = raw.split("|");
        return [p[0].trim(), p[1].trim()];
    }
    return [raw.trim(), "-"];
}

const SVG_SUN = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-sun"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`;
const SVG_MOON = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-moon"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('matchapro_theme', theme);
    const btn = document.getElementById('btn_theme');
    if (btn) btn.innerHTML = (theme === 'dark') ? SVG_SUN : SVG_MOON;
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

function renderEmptyState(msg="Semua data selesai dipadankan!") {
    currentData = null;
    currentCandidates = [];
    recIdx = null;

    const gridTbl = document.getElementById('grid_table');
    if (gridTbl) gridTbl.style.display = 'none';
    const emptyEl = document.getElementById('empty_state');
    if (emptyEl) emptyEl.style.display = 'flex';
    const emptyMsg = document.getElementById('empty_msg');
    if (emptyMsg) emptyMsg.innerText = msg;

    const btnRec = document.getElementById('btn_rec');
    if (btnRec) btnRec.style.display = 'none';
    document.querySelectorAll('.btn-action').forEach(b => {
        b.style.opacity = '0.35';
        b.style.pointerEvents = 'none';
    });
    setStatus(msg, "#28c76f");
}

function renderGrid(to_match, candidates, rec_index, rec_score) {
    currentData = to_match;
    currentCandidates = candidates;
    recIdx = rec_index;

    const emptyEl = document.getElementById('empty_state');
    if (emptyEl) emptyEl.style.display = 'none';
    const gridTbl = document.getElementById('grid_table');
    if (gridTbl) gridTbl.style.display = 'table';

    document.querySelectorAll('.btn-action').forEach(b => {
        b.style.opacity = '1';
        b.style.pointerEvents = 'auto';
    });

    const tbody = document.getElementById('grid_body');
    tbody.innerHTML = '';

    const [m_addr, m_sls] = parseAlamatSls(to_match.alamat);
    const m_q = encodeURIComponent((to_match.nama || '') + ' ' + m_addr);

    const targetMap = {
        "HEADER": `<div class="cell-head-tgt">TARGET (#${to_match.id_table})</div>`,
        "NAMA": `<div class="cell-name">${escapeHTML(to_match.nama || '-')}</div>`,
        "ALAMAT": `<div class="cell-addr">${escapeHTML(m_addr)}</div>`,
        "SLS": escapeHTML(m_sls),
        "DESA": escapeHTML(`${to_match.kddesa || ''} - ${to_match.nmdesa || ''}`),
        "KECAMATAN": escapeHTML(`${to_match.kdkec || ''} - ${to_match.nmkec || ''}`),
        "KABUPATEN": escapeHTML(`${to_match.kdkab || ''} - ${to_match.nmkab || ''}`),
        "PROVINSI": escapeHTML(`${to_match.kdprov || ''} - ${to_match.nmprov || ''}`),
        "KECOCOKAN": '<span class="tag" style="background:#1e3a8a;color:#bfdbfe;">DATA ACUAN</span>',
        "STATUS": '<span class="tag" style="background:#1e3a8a;color:#bfdbfe;">PROFILING</span>',
        "IDSBR": `TABLE: ${to_match.id_table}`,
        "PENCARIAN": `<a class="btn-google" href="https://www.google.com/search?q=${m_q}" target="_blank">🔍 Google</a>`
    };

    ROW_SPECS.forEach(([key, label, h], rIdx) => {
        const tr = document.createElement('tr');
        tr.style.minHeight = h + 'px';

        // 1. Label cell (sticky left: 0)
        const tdLabel = document.createElement('td');
        tdLabel.className = 'td-label ' + (rIdx % 2 ? 'zebra' : '');
        tdLabel.innerText = label;
        tr.appendChild(tdLabel);

        // 2. Target cell (sticky left: 95px)
        const tdTarget = document.createElement('td');
        tdTarget.className = 'td-target ' + (rIdx % 2 ? 'zebra' : '');
        tdTarget.innerHTML = targetMap[key];
        tr.appendChild(tdTarget);

        // 3. Candidates
        candidates.forEach((c, idx) => {
            const isRec = (rec_index !== null && idx === rec_index);
            const tdCand = document.createElement('td');
            tdCand.className = 'td-cand ' + (isRec ? 'recommended ' : '') + (rIdx % 2 ? 'zebra' : '');

            const [c_addr, c_sls] = parseAlamatSls(c.alamat);
            const c_q = encodeURIComponent((c.nama || '') + ' ' + c_addr);
            const isActive = (c.status_perusahaan || 'AKTIF').toUpperCase() === 'AKTIF';

            let badgeText = '[Beda Wilayah]';
            let badgeColor = '#64748b';
            if (c.kddesa && c.kddesa === to_match.kddesa && c.kdkec && c.kdkec === to_match.kdkec) {
                badgeText = '[Desa Sama]'; badgeColor = '#38bdf8';
            } else if (c.kdkec && c.kdkec === to_match.kdkec) {
                badgeText = '[Kec Sama]'; badgeColor = '#a855f7';
            } else if (c.kdkab && c.kdkab === to_match.kdkab) {
                badgeText = '[Kab Sama]'; badgeColor = '#94a3b8';
            }

            const candNum = (candidates.length <= 10 && idx === 9) ? '0' : `${idx + 1}`;
            const candMap = {
                "HEADER": `<div class="cand-header-box">
                               <span style="font-weight:bold;color:${isRec?'#eab308':'#f8fafc'};">#${candNum}${isRec?' ★ ('+rec_score+')':''}</span>
                               <button class="btn-pick" onclick="pickCandidate(${idx}, '${c.idsbr}')">Pilih #${candNum}</button>
                           </div>`,
                "NAMA": `<div class="cell-name ${isRec?'rec-name':''}">${escapeHTML(c.nama || '-')}</div>`,
                "ALAMAT": `<div class="cell-addr">${escapeHTML(c_addr)}</div>`,
                "SLS": escapeHTML(c_sls),
                "DESA": escapeHTML(`${c.kddesa || ''} - ${c.nmdesa || ''}`),
                "KECAMATAN": escapeHTML(`${c.kdkec || ''} - ${c.nmkec || ''}`),
                "KABUPATEN": escapeHTML(`${c.kdkab || ''} - ${c.nmkab || ''}`),
                "PROVINSI": escapeHTML(`${c.kdprov || ''} - ${c.nmprov || ''}`),
                "KECOCOKAN": `<span class="tag badge" style="color:${badgeColor}">${badgeText}</span>`,
                "STATUS": `<span class="tag badge ${isActive?'active':'inactive'}">${isActive?'AKTIF':'NONAKTIF'}</span>`,
                "IDSBR": `IDSBR: ${c.idsbr || '-'}`,
                "PENCARIAN": `<a class="btn-google" style="background:#334155" href="https://www.google.com/search?q=${c_q}" target="_blank">🔍 Google</a>`
            };

            tdCand.innerHTML = candMap[key];
            tr.appendChild(tdCand);
        });

        tbody.appendChild(tr);
    });

    // Update Rekomendasi Button
    const btnRec = document.getElementById('btn_rec');
    if (rec_index !== null && candidates.length > 0) {
        btnRec.style.display = 'flex';
        const recNum = (candidates.length <= 10 && rec_index === 9) ? '0' : (rec_index + 1);
        btnRec.innerText = `★ MATCH #${recNum} (${rec_score})`;
    } else {
        btnRec.style.display = 'none';
    }

    document.getElementById('table_wrapper').scrollLeft = 0;
}

async function loadInitial() {
    setStatus("Memuat antrean...", "#38bdf8");
    try {
        const res = await fetch('/api/data');
        const data = await res.json();
        if (data.status === "need_login") {
            openLogin();
            return;
        }
        if (data.current_user) {
            const elU = document.getElementById('txt_user');
            if (elU) elU.innerText = data.current_user;
        }
        if (data.status === "success" && data.to_match && data.to_match.id_table) {
            renderGrid(data.to_match, data.to_possible || [], data.rec_idx, data.rec_score);
            setStatus(`Target #${data.to_match.id_table} (${(data.to_possible || []).length} opsi)`);
        } else {
            renderEmptyState(data.message || "Semua data selesai dipadankan!");
        }
    } catch (err) {
        setStatus("Gagal memuat: " + err, "#ef4444");
    }
}

async function submitDecision(status, idsbr=null, label="Keputusan") {
    if (!currentData || !currentData.id_table) return;
    if (navigator.vibrate) navigator.vibrate(40);
    setStatus(`Menyimpan ${label}...`, "#eab308");
    try {
        const res = await fetch('/api/submit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: status, idsbr: idsbr})
        });
        const data = await res.json();
        if (data.status === "success" && data.to_match && data.to_match.id_table) {
            renderGrid(data.to_match, data.to_possible || [], data.rec_idx, data.rec_score);
            setStatus(`${label} | ID: ${data.to_match.id_table}`, "#22c55e");
        } else {
            renderEmptyState(data.message || "Semua data selesai dipadankan!");
        }
    } catch (err) {
        setStatus("Error: " + err, "#ef4444");
    }
}

function pickCandidate(idx, idsbr) {
    submitDecision('MATCH', idsbr, `Pilih #${idx+1}`);
}

function matchRecommended() {
    if (recIdx !== null && currentCandidates[recIdx]) {
        const c = currentCandidates[recIdx];
        submitDecision('MATCH', c.idsbr, `Rekomendasi #${recIdx+1}`);
    }
}

async function skipItem() {
    if (!currentData || !currentData.id_table) return;
    if (navigator.vibrate) navigator.vibrate(30);
    setStatus("Melewati...", "#94a3b8");
    try {
        const res = await fetch('/api/skip', {method: 'POST'});
        const data = await res.json();
        if (data.status === "success" && data.to_match && data.to_match.id_table) {
            renderGrid(data.to_match, data.to_possible || [], data.rec_idx, data.rec_score);
            setStatus(`Skip | ID: ${data.to_match.id_table}`);
        } else {
            renderEmptyState(data.message || "Semua data selesai dipadankan!");
        }
    } catch (err) {
        setStatus("Error: " + err, "#ef4444");
    }
}

let cachedAccounts = {};

function openLogin() {
    document.getElementById('inp_user').value = '';
    document.getElementById('inp_pass').value = '';
    document.getElementById('login_err').innerText = '';

    fetch('/api/cache').then(r => r.json()).then(cache => {
        cachedAccounts = cache.accounts || {};
        const dl = document.getElementById('accounts_list');
        dl.innerHTML = '';
        Object.keys(cachedAccounts).forEach(u => {
            const opt = document.createElement('option');
            opt.value = u;
            dl.appendChild(opt);
        });
        if (cache.last_kegiatan) {
            document.getElementById('inp_keg').value = cache.last_kegiatan;
        }
    });
    document.getElementById('login_modal').style.display = 'flex';
}

document.getElementById('inp_user').addEventListener('input', function() {
    const val = this.value.trim();
    if (cachedAccounts && cachedAccounts[val]) {
        document.getElementById('inp_pass').value = cachedAccounts[val];
    }
});

async function doLogin() {
    const u = document.getElementById('inp_user').value.trim();
    const p = document.getElementById('inp_pass').value.trim();
    const k = document.getElementById('inp_keg').value.trim();
    const err = document.getElementById('login_err');
    err.innerText = "";
    document.getElementById('btn_login_submit').innerText = "Memverifikasi...";

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: u, password: p, kegiatan_id: k})
        });
        const data = await res.json();
        if (data.status === "success") {
            document.getElementById('login_modal').style.display = 'none';
            document.getElementById('lbl_keg').innerText = '#' + k;
            const elU = document.getElementById('txt_user');
            if (elU) elU.innerText = data.username || u;
            loadInitial();
        } else {
            err.innerText = data.message || "Login gagal";
        }
    } catch (e) {
        err.innerText = "Error: " + e;
    } finally {
        document.getElementById('btn_login_submit').innerText = "Masuk Sekarang";
    }
}

// Hotkeys untuk keyboard Bluetooth tablet
window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'Enter') matchRecommended();
    if (currentCandidates && currentCandidates.length <= 10) {
        if (e.key >= '1' && e.key <= '9') {
            const num = parseInt(e.key) - 1;
            if (currentCandidates[num]) pickCandidate(num, currentCandidates[num].idsbr);
        } else if (e.key === '0') {
            if (currentCandidates[9]) pickCandidate(9, currentCandidates[9].idsbr);
        }
    }
    if (e.key === 'u' || e.key === 'U') submitDecision('UNMATCH');
    if (e.key === 's' || e.key === 'S') skipItem();
    if (e.key === 'i' || e.key === 'I') submitDecision('IGNORE');
});

// PWA Install Prompt & Service Worker
let deferredPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const btnPwa = document.getElementById('btn_pwa');
    if (btnPwa) btnPwa.style.display = 'inline-block';
});

function installPwa() {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(() => {
            deferredPrompt = null;
            const btnPwa = document.getElementById('btn_pwa');
            if (btnPwa) btnPwa.style.display = 'none';
        });
    }
}

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
}

// Load awal
const savedTheme = localStorage.getItem('matchapro_theme') || 'dark';
applyTheme(savedTheme);
loadInitial();
