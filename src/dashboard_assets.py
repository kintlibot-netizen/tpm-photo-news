"""Style sheet, script, icons and font embedding for dashboard/index.html (and the read only copy for David).

Everything is inlined into the one page: Inter is embedded as data URIs and the icons are inline SVG, so the file works
offline from file:// with no CDN. This module holds no data and reads no secrets.

The design system: Inter, one neutral slate palette plus the TPM cyan accent, an 8px spacing grid, cards with a subtle
border, radii of 8, 12 and 16px, and one status chip colour per meaning (green done, amber waiting, blue sent,
red failed, grey out of the flow).
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

FONT_FILES = ((400, "Inter-Regular.ttf"), (600, "Inter-SemiBold.ttf"))


def font_face_css(fonts_dir: Path) -> str:
    """@font-face rules with the font files embedded. A missing file is skipped, so the page falls back
    to the system font and still builds."""
    rules = []
    for weight, name in FONT_FILES:
        try:
            data = (Path(fonts_dir) / name).read_bytes()
        except OSError:
            continue
        encoded = base64.b64encode(data).decode("ascii")
        rules.append(
            "@font-face{font-family:\"Inter\";font-style:normal;font-weight:%d;font-display:swap;"
            "src:url(data:font/ttf;base64,%s) format(\"truetype\")}" % (weight, encoded)
        )
    return "".join(rules)


_PATHS = {
    "stories": '<path d="M4 6h16M4 12h16M4 18h10"/>',
    "carousels": '<rect x="3" y="5" width="13" height="14" rx="2"/><path d="M19 7v10M22 9v6"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "sources": '<path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1.5"/>',
    "how": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17v.5"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "check": '<path d="M5 12.5 10 17l9-10"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "send": '<path d="M21 3 10 14M21 3l-7 18-4-7-7-4z"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "lock": '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    "share": '<path d="M12 3v12M7 8l5-5 5 5M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>',
}


def icon(name: str) -> str:
    """An inline stroke icon. Decorative: hidden from screen readers."""
    return (f'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            f'{_PATHS.get(name, _PATHS["how"])}</svg>')


BRAND_MARK = (
    '<svg viewBox="0 0 36 36" aria-hidden="true" focusable="false">'
    '<rect width="36" height="36" rx="9" fill="#0f172a"/>'
    '<circle cx="18" cy="18" r="9" fill="none" stroke="#22d3ee" stroke-width="2.5"/>'
    '<circle cx="18" cy="18" r="3.5" fill="#22d3ee"/>'
    '<rect x="24" y="8" width="5" height="3" rx="1.5" fill="#e2e8f0"/></svg>'
)


CSS = r"""
:root{
--font:"Inter","Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;
--bg:#f4f6f9;--surface:#ffffff;--surface-2:#f8fafc;--line:#e6eaf0;--line-strong:#cfd6e0;
--ink:#0b1220;--ink-2:#334155;--muted:#5b6679;
--accent:#0e7490;--accent-ink:#155e75;--accent-bright:#22d3ee;--accent-tint:#ecfeff;--accent-line:#a5f3fc;
--side:#0b1220;--side-2:#131c2e;--side-ink:#cbd5e1;--side-muted:#8391a7;
--green:#166534;--green-bg:#dcfce7;--green-line:#86efac;
--amber:#92400e;--amber-bg:#fef3c7;--amber-line:#fcd34d;
--blue:#1e40af;--blue-bg:#dbeafe;--blue-line:#93c5fd;
--red:#991b1b;--red-bg:#fee2e2;--red-line:#fca5a5;
--slate:#475569;--slate-bg:#f1f5f9;--slate-line:#cbd5e1;
--s1:8px;--s2:16px;--s3:24px;--s4:32px;--s5:40px;--s6:48px;
--r1:8px;--r2:12px;--r3:16px;
--t-xs:12px;--t-sm:13px;--t-md:14px;--t-lg:16px;--t-xl:20px;--t-2xl:26px;
--shadow:0 1px 2px rgba(11,18,32,.05),0 2px 8px rgba(11,18,32,.04);
--shadow-hover:0 2px 4px rgba(11,18,32,.06),0 12px 28px rgba(11,18,32,.10);
--shadow-lg:0 16px 40px rgba(11,18,32,.22);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:var(--font);font-size:var(--t-md);line-height:1.55;color:var(--ink);background:var(--bg);
-webkit-font-smoothing:antialiased}
body.lock{overflow:hidden}
h1,h2,h3,h4,p,ol,ul,dl,dd{margin:0}
ol,ul{padding:0;list-style:none}
button{font:inherit;color:inherit}
a{color:var(--accent);text-underline-offset:2px}
a:hover{color:var(--accent-ink)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
[hidden]{display:none !important}
.ic{width:18px;height:18px;flex:none;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.muted{color:var(--muted)}
.small{font-size:var(--t-xs)}

/* shell: dark sidebar, light canvas */
.app{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh;
background:linear-gradient(to right,var(--side) 240px,transparent 240px)}
.sidebar{position:sticky;top:0;align-self:start;height:100vh;display:flex;flex-direction:column;gap:var(--s4);
background:var(--side);color:var(--side-ink);padding:var(--s3) var(--s2);overflow-y:auto}
.brand{display:flex;align-items:center;gap:12px;padding:0 var(--s1)}
.brand svg{width:34px;height:34px;flex:none}
.brand-name{font-weight:600;font-size:15px;line-height:1.2;color:#fff;letter-spacing:-.01em}
.brand-sub{font-size:var(--t-xs);color:var(--side-muted)}
.nav{display:flex;flex-direction:column;gap:2px}
.nav button{display:flex;align-items:center;gap:12px;width:100%;padding:9px 12px;border:0;border-radius:var(--r1);
background:none;cursor:pointer;color:var(--side-ink);font-weight:500;font-size:var(--t-md);text-align:left;
transition:background .15s,color .15s}
.nav button:hover{background:var(--side-2);color:#fff}
.nav button[aria-current=page]{background:rgba(34,211,238,.12);color:#fff}
.nav button[aria-current=page] .ic{color:var(--accent-bright)}
.nav .badge{margin-left:auto;min-width:22px;padding:0 7px;border-radius:999px;background:var(--side-2);color:var(--side-ink);
font-size:11px;font-weight:600;text-align:center;line-height:20px}
.nav button[aria-current=page] .badge{background:var(--accent-bright);color:var(--side)}
.side-foot{margin-top:auto;display:flex;flex-direction:column;gap:6px;padding:var(--s2);border-radius:var(--r2);
background:var(--side-2);font-size:var(--t-xs);color:var(--side-muted)}
.side-foot strong{display:flex;align-items:center;gap:8px;color:#fff;font-size:var(--t-sm);font-weight:600}
.side-foot .ic{width:15px;height:15px;color:var(--accent-bright)}
.side-foot .gen{color:var(--side-muted);opacity:.85}
.main{min-width:0;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:var(--s2);flex-wrap:wrap;
padding:12px var(--s5);min-height:64px;background:rgba(244,246,249,.88);backdrop-filter:saturate(1.4) blur(10px);
-webkit-backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.crumb{font-weight:600;font-size:var(--t-lg);letter-spacing:-.01em}
.health{display:flex;align-items:center;gap:10px;min-width:0;flex:1 1 320px;margin-right:auto}
.health-text{font-size:var(--t-sm);color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.who{display:flex;flex-direction:column;gap:2px}
.who label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.who input{width:170px;padding:6px 10px}
.banner{display:flex;align-items:center;gap:12px;padding:12px var(--s5);background:var(--amber-bg);
border-bottom:1px solid var(--amber-line);color:var(--amber);font-weight:600;font-size:var(--t-md)}
.banner .ic{width:18px;height:18px}
.content{padding:var(--s4) var(--s5) var(--s6);max-width:1320px;width:100%}
.page{display:flex;flex-direction:column;gap:var(--s3)}
.page-head h1{font-size:var(--t-2xl);font-weight:650;letter-spacing:-.02em;line-height:1.2}
.page-head p{margin-top:6px;color:var(--muted);font-size:var(--t-lg);max-width:760px}

/* status tags and pills */
.tag{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:var(--t-xs);
font-weight:600;line-height:1.5;border:1px solid transparent;white-space:normal}
.tag.dot::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;flex:none}
.st-ok,.st-alert{background:var(--green-bg);color:var(--green);border-color:var(--green-line)}
.st-held{background:var(--amber-bg);color:var(--amber);border-color:var(--amber-line)}
.st-accent{background:var(--accent-tint);color:var(--accent-ink);border-color:var(--accent-line)}
.st-fail{background:var(--red-bg);color:var(--red);border-color:var(--red-line)}
.st-rej,.st-dry{background:var(--slate-bg);color:var(--slate);border-color:var(--slate-line)}
.pill{display:inline-flex;align-items:center;padding:2px 9px;border-radius:6px;font-size:11px;font-weight:600;
letter-spacing:.02em;line-height:1.6}
.p-brand{background:var(--ink);color:#fff}
.p-official{background:var(--accent-tint);color:var(--accent-ink)}
.p-rumor{background:#f3e8ff;color:#6b21a8}
.chip-row{display:flex;flex-wrap:wrap;gap:8px}

/* buttons and inputs */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:8px 14px;border-radius:var(--r1);
border:1px solid var(--line-strong);background:var(--surface);color:var(--ink);font-weight:600;font-size:var(--t-sm);
cursor:pointer;text-decoration:none;transition:background .15s,border-color .15s,box-shadow .15s}
.btn:hover{background:var(--surface-2);border-color:var(--ink-2);color:var(--ink)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:var(--accent-ink);border-color:var(--accent-ink);color:#fff}
.btn.small{padding:5px 10px;font-size:var(--t-xs)}
.btn.small .ic{width:14px;height:14px}
.btn[aria-disabled=true]{opacity:.55;cursor:not-allowed}
.btn.done{background:var(--green-bg);border-color:var(--green-line);color:var(--green)}
input,select{font:inherit;font-size:var(--t-sm);padding:7px 10px;border:1px solid var(--line-strong);border-radius:var(--r1);
background:var(--surface);color:var(--ink);min-width:0}
input:focus,select:focus{outline:2px solid var(--accent-line);border-color:var(--accent)}

/* hero tiles */
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--s2)}
.tile{display:flex;gap:14px;align-items:flex-start;padding:18px;background:var(--surface);border:1px solid var(--line);
border-radius:var(--r3);box-shadow:var(--shadow)}
.tile-ic{display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:var(--accent-tint);
color:var(--accent);flex:none}
.tile.ok .tile-ic{background:var(--green-bg);color:var(--green)}
.tile.warn .tile-ic{background:var(--amber-bg);color:var(--amber)}
.tile-v{font-size:22px;font-weight:650;letter-spacing:-.02em;line-height:1.2;overflow-wrap:anywhere}
.tile-k{font-size:var(--t-sm);font-weight:600;color:var(--ink-2);margin-top:2px}
.tile-n{font-size:var(--t-xs);color:var(--muted)}

/* panels */
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r3);box-shadow:var(--shadow);overflow:hidden}
.panel-head{display:flex;align-items:center;gap:var(--s2);padding:14px var(--s3);border-bottom:1px solid var(--line)}
.panel-head h2{font-size:var(--t-lg);font-weight:600;margin-right:auto}
.panel-head .count{font-size:var(--t-xs);color:var(--muted);font-weight:600}
.panel-body{padding:var(--s2) var(--s3);display:flex;flex-direction:column;gap:12px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:var(--t-sm)}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;
padding:10px var(--s3);background:var(--surface-2);border-bottom:1px solid var(--line)}
td{padding:10px var(--s3);border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
td.name{font-weight:600}
.toolbar{display:flex;justify-content:flex-end}

/* empty states */
.empty-state{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;padding:var(--s6) var(--s3);
background:var(--surface);border:1px dashed var(--line-strong);border-radius:var(--r3)}
.empty-ic{display:grid;place-items:center;width:48px;height:48px;border-radius:14px;background:var(--accent-tint);color:var(--accent)}
.empty-ic .ic{width:22px;height:22px}
.empty-state h3{font-size:var(--t-lg);font-weight:600}
.empty-state p{color:var(--muted);max-width:440px}

/* carousel gallery cards */
.car-list{display:flex;flex-direction:column;gap:var(--s3)}
.carousel-card{display:grid;grid-template-columns:minmax(240px,320px) minmax(0,1fr);background:var(--surface);
border:1px solid var(--line);border-radius:var(--r3);box-shadow:var(--shadow);overflow:hidden;transition:box-shadow .2s}
.carousel-card:hover{box-shadow:var(--shadow-hover)}
.cc-cover{background:linear-gradient(160deg,#0b1220,#16243b);padding:var(--s3);display:flex;align-items:center;justify-content:center}
.cc-foot{grid-column:1 / -1;padding:var(--s3);border-top:1px solid var(--line);display:flex;flex-direction:column;gap:14px}
.cc-foot>details:first-child{border-top:0;padding-top:0}
.cc-body{padding:var(--s3);display:flex;flex-direction:column;gap:14px;min-width:0}
.cc-head{display:flex;flex-direction:column;gap:8px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.story-title{font-size:var(--t-xl);line-height:1.3;font-weight:650;letter-spacing:-.01em;overflow-wrap:anywhere}
.strip-label{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.slide{display:block;width:100%;padding:0;border:0;background:none;cursor:zoom-in;position:relative}
.thumb{display:block;position:relative;aspect-ratio:4/5;border-radius:10px;overflow:hidden;background:#0f172a;
box-shadow:0 1px 3px rgba(0,0,0,.18)}
.thumb img{display:block;width:100%;height:100%;object-fit:cover;transition:transform .25s}
.slide:hover .thumb img{transform:scale(1.03)}
.thumb .fb{display:none;position:absolute;inset:0;place-items:center;color:#94a3b8;font-size:var(--t-xs);text-align:center;padding:8px}
.thumb.broken img{display:none}
.thumb.broken .fb{display:grid}
.cover .thumb{border-radius:12px;box-shadow:0 12px 32px rgba(0,0,0,.45)}
.cover-badge{position:absolute;left:10px;bottom:10px;display:inline-flex;align-items:center;gap:6px;padding:4px 10px;
border-radius:999px;background:rgba(11,18,32,.78);color:#fff;font-size:11px;font-weight:600}
.cover-badge .ic{width:13px;height:13px}
.thumbs{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:10px}
.tcell{display:flex;flex-direction:column;gap:4px;min-width:0}
.slide-n{display:flex;align-items:center;justify-content:space-between;gap:4px;font-size:11px;color:var(--muted);font-weight:600}
.slide-n .btn.small{padding:2px 7px;font-size:11px}
.slide-n .btn.small .ic{width:12px;height:12px}
.no-image{font-size:10px}
.no-slides{color:var(--muted);font-size:var(--t-sm)}
.dl-row{display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.car-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.box{border:1px solid var(--line);border-radius:var(--r2);padding:14px;background:var(--surface-2);min-width:0;
display:flex;flex-direction:column;gap:8px}
.box h3{font-size:var(--t-sm);font-weight:600}
.box-top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.box ul{display:flex;flex-direction:column;gap:4px;font-size:var(--t-sm);overflow-wrap:anywhere}
.cap{white-space:pre-line;font-size:var(--t-sm);color:var(--ink-2);max-height:150px;overflow-y:auto}
.facts{display:grid;grid-template-columns:110px minmax(0,1fr);gap:4px 12px;font-size:var(--t-sm)}
.facts dt{color:var(--muted);font-weight:600}
.facts dd{overflow-wrap:anywhere}
details.more,details.caps,details.copy-row{border-top:1px solid var(--line);padding-top:12px}
details.held{border:0;padding:0}
details.held>summary{padding:4px 0}
details>summary{cursor:pointer;font-weight:600;font-size:var(--t-sm);color:var(--ink-2);list-style:none;display:flex;
align-items:center;gap:8px}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"";width:7px;height:7px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;
transform:rotate(-45deg);transition:transform .15s;margin-right:2px}
details[open]>summary::before{transform:rotate(45deg)}
details[open]>summary{margin-bottom:12px}
details.copy-row[open]{display:flex;flex-wrap:wrap;gap:8px}
details.copy-row[open]>summary{width:100%;margin-bottom:4px}
.note-line{padding:10px 14px;border-radius:var(--r2);background:var(--accent-tint);color:var(--accent-ink);font-size:var(--t-sm)}
.review-area{display:flex;flex-direction:column;gap:12px;border-top:1px solid var(--line);padding-top:14px}
.review{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.review-group{display:inline-flex;flex-wrap:wrap;gap:8px;align-items:center}
.act{padding:8px 16px;border-radius:var(--r1);border:1px solid var(--accent);background:var(--accent);color:#fff;
font-weight:600;font-size:var(--t-sm);cursor:pointer}
.act:hover{background:var(--accent-ink)}
.act.secondary{background:var(--surface);color:var(--ink);border-color:var(--line-strong)}
.act.secondary:hover{background:var(--surface-2)}
.flash{animation:flash 1.8s ease}
@keyframes flash{0%{box-shadow:0 0 0 4px var(--accent-line)}100%{box-shadow:var(--shadow)}}

/* photo news */
.news-list{display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);
border-radius:var(--r3);box-shadow:var(--shadow);overflow:hidden}
.news-item{display:flex;gap:var(--s3);padding:18px var(--s3);border-bottom:1px solid var(--line);transition:background .15s}
.news-item:last-child{border-bottom:0}
.news-item:hover{background:var(--surface-2)}
.ni-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px}
.ni-top{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.ni-when{font-size:var(--t-xs);color:var(--muted)}
.ni-title{font-size:var(--t-lg);font-weight:600;line-height:1.35;overflow-wrap:anywhere}
.ni-title a{color:var(--ink);text-decoration:none}
.ni-title a:hover{color:var(--accent);text-decoration:underline}
.ni-sum{color:var(--ink-2);font-size:var(--t-sm)}
.ni-src{display:flex;align-items:center;gap:6px;font-size:var(--t-xs);color:var(--muted)}
.ni-src .ic{width:13px;height:13px}
.ni-src span{display:flex;flex-wrap:wrap;gap:4px 10px}
.ni-side{flex:none;max-width:280px;display:flex;flex-direction:column;align-items:flex-end;gap:6px}

/* how it works */
.steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--s2)}
.step{position:relative;padding:var(--s3);background:var(--surface);border:1px solid var(--line);border-radius:var(--r3);
box-shadow:var(--shadow);display:flex;flex-direction:column;gap:8px}
.step-n{position:absolute;top:16px;right:18px;font-size:var(--t-xs);font-weight:700;color:var(--line-strong)}
.step-ic{display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:var(--accent-tint);color:var(--accent)}
.step h3{font-size:var(--t-lg);font-weight:600}
.step p{color:var(--muted);font-size:var(--t-sm)}
.rules{display:flex;flex-direction:column;gap:10px;padding:var(--s2) var(--s3)}
.rules li{display:flex;gap:10px;align-items:flex-start;font-size:var(--t-sm)}
.rules .ic{color:var(--green);width:17px;height:17px;margin-top:2px}

/* lightbox */
.lightbox{position:fixed;inset:0;z-index:30;background:rgba(6,10,18,.94);display:flex;flex-direction:column;align-items:center;
gap:var(--s2);padding:var(--s2)}
.lb-bar{display:flex;align-items:center;gap:12px;color:#e2e8f0;font-size:var(--t-sm);width:100%;max-width:960px}
.lb-bar .lb-title{margin-right:auto;font-weight:600;overflow-wrap:anywhere}
.lb-stage{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;max-width:100%}
.lb-stage img{max-width:100%;max-height:calc(100vh - 110px);border-radius:var(--r2);background:#0f172a;display:block;
box-shadow:0 20px 60px rgba(0,0,0,.5)}
.fb-tile{color:#94a3b8;padding:var(--s4)}
.lightbox .btn{background:#1e293b;border-color:#334155;color:#fff}
.lightbox .btn:hover{background:#334155}

.toast{position:fixed;right:20px;bottom:20px;max-width:440px;padding:12px 16px;border-radius:var(--r2);z-index:40;
box-shadow:var(--shadow-lg);font-size:var(--t-md)}
.toast.ok{background:var(--green-bg);color:var(--green);border:1px solid var(--green-line)}
.toast.err{background:var(--red-bg);color:var(--red);border:1px solid var(--red-line)}
.toast a{color:inherit;font-weight:600}

@media (prefers-reduced-motion:reduce){*{transition:none !important;animation:none !important}}

/* responsive */
@media (max-width:1180px){
.content{padding:var(--s3)}
.topbar{padding:12px var(--s3)}
.banner{padding:12px var(--s3)}
.tiles,.steps{grid-template-columns:repeat(2,minmax(0,1fr))}
.carousel-card{grid-template-columns:minmax(200px,260px) minmax(0,1fr)}
}
@media (max-width:860px){
.app{grid-template-columns:minmax(0,1fr);background:none}
.sidebar{position:sticky;top:0;z-index:6;height:auto;flex-direction:row;align-items:center;gap:var(--s2);padding:10px 12px;overflow:visible}
.brand-sub,.side-foot{display:none}
.brand-name,.crumb,.who,#export-david{display:none}
.nav{flex-direction:row;gap:4px;overflow-x:auto;flex:1;scrollbar-width:none}
.nav button{width:auto;flex:none;padding:8px 10px;font-size:var(--t-sm)}
.topbar{position:static;padding:12px var(--s2)}
.health{flex-basis:100%;order:2}
.health-text{white-space:normal}
.content{padding:var(--s2) var(--s2) var(--s5)}
.page-head h1{font-size:22px}
.page-head p{font-size:var(--t-md)}
.tiles{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.tile{padding:14px;gap:10px}
.tile-ic{width:32px;height:32px}
.tile-v{font-size:18px}
.carousel-card{grid-template-columns:minmax(0,1fr)}
.cc-cover{padding:var(--s2);justify-content:center}
.cc-cover .slide{max-width:340px}
.cc-body,.cc-foot{padding:var(--s2)}
.thumbs{grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.steps{grid-template-columns:minmax(0,1fr)}
.news-item{flex-direction:column;gap:10px;padding:14px var(--s2)}
.ni-side{flex-direction:row;flex-wrap:wrap;align-items:flex-start;max-width:none}
.facts{grid-template-columns:minmax(0,1fr)}
.who input{width:140px}
}
"""

JS = r"""
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var mode = document.body.getAttribute('data-mode');
  var live = location.protocol === 'http:' && mode === 'local';

  /* ---------- messages ---------- */
  var toastBox = $('#toast'), toastTimer = null;
  function toast(message, ok, link) {
    if (!toastBox) { return; }
    toastBox.textContent = message;
    if (link) {
      var a = document.createElement('a');
      a.href = link; a.textContent = ' Download it'; a.setAttribute('download', '');
      toastBox.appendChild(a);
    }
    toastBox.className = 'toast ' + (ok ? 'ok' : 'err');
    toastBox.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastBox.hidden = true; }, link ? 20000 : 7000);
  }

  /* ---------- pages ---------- */
  var pages = $$('[data-page]');
  var navs = $$('.nav [data-nav]');
  function show(name) {
    if (!pages.some(function (p) { return p.getAttribute('data-page') === name; })) {
      name = document.body.getAttribute('data-home') || 'review';
    }
    pages.forEach(function (p) { p.hidden = p.getAttribute('data-page') !== name; });
    var label = '';
    navs.forEach(function (b) {
      if (b.getAttribute('data-nav') === name) { b.setAttribute('aria-current', 'page'); label = b.getAttribute('data-label'); }
      else { b.removeAttribute('aria-current'); }
    });
    var crumb = $('#crumb');
    if (crumb) { crumb.textContent = label; }
    try { history.replaceState(null, '', '#' + name); } catch (e) { /* a file page may refuse this; harmless */ }
    window.scrollTo(0, 0);
  }
  navs.forEach(function (b) { b.addEventListener('click', function () { show(b.getAttribute('data-nav')); }); });
  window.addEventListener('hashchange', function () { show(location.hash.replace('#', '')); });

  /* ---------- copy ---------- */
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) { return navigator.clipboard.writeText(text); }
    return new Promise(function (resolve, reject) {
      var box = document.createElement('textarea');
      box.value = text; box.setAttribute('readonly', '');
      box.style.position = 'fixed'; box.style.opacity = '0';
      document.body.appendChild(box); box.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(box);
      if (ok) { resolve(); } else { reject(new Error('copy failed')); }
    });
  }
  function reviewerName() { var box = $('#reviewer'); return box ? box.value.trim() : ''; }
  document.addEventListener('click', function (event) {
    var button = event.target.closest('.copy');
    if (!button) { return; }
    var text = button.getAttribute('data-copy') || '';
    var who = reviewerName();
    if (who && text.indexOf('--by "Name"') !== -1) { text = text.replace('--by "Name"', '--by "' + who.replace(/"/g, '') + '"'); }
    copyText(text).then(function () {
      button.classList.add('done');
      setTimeout(function () { button.classList.remove('done'); }, 1400);
      toast(button.getAttribute('data-kind') === 'caption' ? 'Caption copied.'
        : (typeof COMMAND_COPIED !== 'undefined' ? COMMAND_COPIED : 'Copied.'), true);
    }, function () { toast('Could not copy. Select the text and copy it by hand.', false); });
  });

  /* LOCAL-ONLY START: review buttons, the review server and command copies (never in David's read only copy) */
  var COMMAND_COPIED = 'Command copied. Paste it into PowerShell.';
  /* ---------- review buttons ---------- */
  function post(url, payload, done) {
    fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
      body: JSON.stringify(payload)
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) { return { ok: res.ok, body: body }; });
    }).then(done).catch(function () {
      toast('Could not reach the review server. Is Open Review Dashboard still running?', false);
    });
  }
  $$('[data-action]').forEach(function (button) {
    button.addEventListener('click', function () {
      var card = button.closest('.carousel-card');
      var action = button.getAttribute('data-action');
      var base = button.getAttribute('data-base') || '';
      var who = reviewerName();
      var payload = { action: action, folder: button.getAttribute('data-folder') };
      var command = '';
      if (who) { payload.reviewer = who; }
      if (action === 'approve') {
        if (!who) { toast('Type your name in the box at the top of the page first.', false); return; }
        command = base + ' --by "' + who.replace(/"/g, '') + '"';
      } else if (action === 'reject') {
        var reasonBox = card.querySelector('.reason');
        var reason = reasonBox ? reasonBox.value.trim() : '';
        if (!reason) { toast('Type a reason for rejecting first.', false); return; }
        payload.reason = reason;
        command = base + ' --reason "' + reason.replace(/"/g, "'") + '"';
      } else if (action === 'posted') {
        var accountBox = card.querySelector('.account');
        var urlBox = card.querySelector('.post-url');
        var link = urlBox ? urlBox.value.trim() : '';
        if (!link) { toast('Paste the link to the post first.', false); return; }
        payload.account = accountBox ? accountBox.value : '';
        payload.url = link;
        command = base + ' --account ' + payload.account + ' --url "' + link.replace(/"/g, '') + '"';
      } else { return; }
      if (live) {
        post('/api/review', payload, function (result) {
          toast(result.ok ? (result.body.message || 'Done.') : (result.body.error || 'Not done.'), result.ok);
          if (result.ok) { setTimeout(function () { location.reload(); }, 1500); }
        });
      } else {
        copyText(command).then(function () { toast('Command copied. Paste it into PowerShell in the project folder.', true); },
          function () { toast('Could not copy. Open Review Dashboard to use the buttons.', false); });
      }
    });
  });

  /* LOCAL-ONLY END */

  /* ---------- downloads: real downloads through the review server, the prebuilt files otherwise ---------- */
  if (live) {
    $$('[data-live-href]').forEach(function (a) {
      a.setAttribute('href', a.getAttribute('data-live-href'));
      a.removeAttribute('aria-disabled');
      a.removeAttribute('title');
    });
  }
  document.addEventListener('click', function (event) {
    var a = event.target.closest('a[aria-disabled=true]');
    if (!a) { return; }
    event.preventDefault();
    toast(a.getAttribute('title') || 'Not available in this copy.', false);
  });

  /* LOCAL-ONLY START: the Export for David button */
  /* ---------- export for David ---------- */
  var exportButton = $('#export-david');
  if (exportButton) {
    exportButton.addEventListener('click', function () {
      if (!live) {
        copyText(exportButton.getAttribute('data-copy') || '').then(function () {
          toast('Command copied. Paste it into PowerShell, or double-click Export for David.bat.', true);
        }, function () { toast('Double-click Export for David.bat in the project folder.', false); });
        return;
      }
      exportButton.setAttribute('aria-disabled', 'true');
      toast('Building the copy for David. This can take a minute.', true);
      post('/api/export', {}, function (result) {
        exportButton.removeAttribute('aria-disabled');
        toast(result.ok ? result.body.message : (result.body.error || 'The export was not made.'), result.ok,
          result.ok ? result.body.download : null);
      });
    });
  }

  /* LOCAL-ONLY END */

  /* ---------- focus trap ---------- */
  function trap(container, event) {
    if (event.key !== 'Tab') { return; }
    var items = $$('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])', container)
      .filter(function (el) { return el.offsetParent !== null; });
    if (!items.length) { return; }
    var first = items[0], last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  /* ---------- go to another page ---------- */
  document.addEventListener('click', function (event) {
    var go = event.target.closest('[data-go]');
    if (!go) { return; }
    show(go.getAttribute('data-go'));
  });

  /* ---------- phones: captions start folded so the slides come first ---------- */
  if (window.matchMedia && window.matchMedia('(max-width:860px)').matches) {
    $$('details.caps').forEach(function (d) { d.removeAttribute('open'); });
  }

  /* ---------- images that fail to load ---------- */
  function markBroken(img) {
    var holder = img.closest('.thumb');
    if (holder) { holder.classList.add('broken'); }
  }
  $$('img[data-fb]').forEach(function (img) {
    img.addEventListener('error', function () { markBroken(img); });
    if (img.complete && img.naturalWidth === 0) { markBroken(img); }
  });

  /* ---------- lightbox ---------- */
  var box = $('#lightbox'), stage = $('#lb-stage'), counter = $('#lb-count'), lbTitle = $('#lb-title');
  var group = [], at = 0, lbOpener = null;
  function paint() {
    var current = group[at];
    stage.innerHTML = '';
    var picture = document.createElement('img');
    picture.alt = current.getAttribute('data-alt') || 'Slide';
    picture.addEventListener('error', function () {
      stage.innerHTML = '';
      var tile = document.createElement('div');
      tile.className = 'fb-tile';
      tile.textContent = 'This slide image could not be found.';
      stage.appendChild(tile);
    });
    picture.src = current.getAttribute('data-src');
    stage.appendChild(picture);
    counter.textContent = 'Slide ' + (at + 1) + ' of ' + group.length;
    lbTitle.textContent = current.getAttribute('data-title') || '';
  }
  function openLightbox(button) {
    if (!box) { return; }
    group = $$('[data-lb="' + button.getAttribute('data-lb') + '"]');
    at = Math.max(0, group.indexOf(button));
    lbOpener = button;
    paint();
    box.hidden = false;
    document.body.classList.add('lock');
    $('#lb-close').focus();
  }
  function closeLightbox() {
    if (!box || box.hidden) { return; }
    box.hidden = true;
    document.body.classList.remove('lock');
    if (lbOpener) { lbOpener.focus(); }
  }
  function step(delta) {
    if (!group.length) { return; }
    at = (at + delta + group.length) % group.length;
    paint();
  }
  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-lb]');
    if (button) { openLightbox(button); }
  });
  if (box) {
    $('#lb-close').addEventListener('click', closeLightbox);
    $('#lb-prev').addEventListener('click', function () { step(-1); });
    $('#lb-next').addEventListener('click', function () { step(1); });
    box.addEventListener('click', function (event) { if (event.target === box) { closeLightbox(); } });
  }
  document.addEventListener('keydown', function (event) {
    if (box && !box.hidden) {
      if (event.key === 'Escape') { closeLightbox(); }
      else if (event.key === 'ArrowRight') { step(1); }
      else if (event.key === 'ArrowLeft') { step(-1); }
      else { trap(box, event); }
    }
  });

  show(location.hash.replace('#', '') || document.body.getAttribute('data-home') || 'review');
})();
"""

_LOCAL_ONLY = re.compile(r"/\* LOCAL-ONLY START.*?/\* LOCAL-ONLY END \*/", re.S)


def script_for(mode: str) -> str:
    """The page script. Kint's page gets all of it. David's read only copy ("share") gets the same script without the
    review buttons, the review server calls, the Export for David button and the command copy text, so the copy holds
    no command, no PowerShell wording and no way to change anything."""
    if mode != "share":
        return JS
    return _LOCAL_ONLY.sub("", JS)
