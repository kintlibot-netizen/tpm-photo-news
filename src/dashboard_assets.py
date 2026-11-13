"""Style sheet, script, icons and font embedding for dashboard/index.html (and the read only copy for David).

Everything is inlined into the one page: Inter is embedded as data URIs and the icons are inline SVG, so the file works
offline from file:// with no CDN. This module holds no data and reads no secrets.

The design system: Inter, one neutral slate palette plus the TPM cyan accent, an 8px spacing grid, cards with a subtle
border, radii of 8, 12 and 16px, and one status chip colour per meaning (green done, amber waiting, blue sent,
red failed, grey out of the flow).
"""
from __future__ import annotations

import base64
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
    "start": '<path d="M4 19.5V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14.5"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20"/>'
             '<path d="M9 8h7M9 12h5"/>',
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "attention": '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4M12 17.5v.5"/>',
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
            f'{_PATHS.get(name, _PATHS["overview"])}</svg>')


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
--bg:#f5f7fa;--surface:#ffffff;--surface-2:#f8fafc;--line:#e2e8f0;--line-strong:#cbd5e1;
--ink:#0f172a;--ink-2:#334155;--muted:#5b6679;
--accent:#0e7490;--accent-ink:#155e75;--accent-bright:#22d3ee;--accent-tint:#ecfeff;--accent-line:#a5f3fc;
--green:#166534;--green-bg:#dcfce7;--green-line:#86efac;
--amber:#92400e;--amber-bg:#fef3c7;--amber-line:#fcd34d;
--blue:#1e40af;--blue-bg:#dbeafe;--blue-line:#93c5fd;
--red:#991b1b;--red-bg:#fee2e2;--red-line:#fca5a5;
--slate:#475569;--slate-bg:#f1f5f9;--slate-line:#cbd5e1;
--s1:8px;--s2:16px;--s3:24px;--s4:32px;--s5:40px;--s6:48px;
--r1:8px;--r2:12px;--r3:16px;
--t-xs:12px;--t-sm:13px;--t-md:14px;--t-lg:16px;--t-xl:20px;--t-2xl:24px;--t-3xl:32px;
--shadow:0 1px 2px rgba(15,23,42,.06);
--shadow-lg:0 16px 40px rgba(15,23,42,.22);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:var(--font);font-size:var(--t-md);line-height:1.5;color:var(--ink);background:var(--bg);font-weight:400}
body.lock{overflow:hidden}
h1,h2,h3,h4,p,ol,ul,dl,dd{margin:0}
ol,ul{padding:0;list-style:none}
button{font:inherit;color:inherit}
a{color:var(--accent);text-underline-offset:2px}
a:hover{color:var(--accent-ink)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
[hidden]{display:none !important}
.ic{width:20px;height:20px;flex:none;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.muted{color:var(--muted)}
.small{font-size:var(--t-xs)}

/* shell */
.app{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}
.sidebar{position:sticky;top:0;align-self:start;height:100vh;display:flex;flex-direction:column;gap:var(--s3);
background:var(--surface);border-right:1px solid var(--line);padding:var(--s3) var(--s2);overflow-y:auto}
.brand{display:flex;align-items:center;gap:12px;padding:0 var(--s1)}
.brand svg{width:36px;height:36px;flex:none}
.brand-name{font-weight:600;font-size:var(--t-lg);line-height:1.2;color:var(--ink)}
.brand-sub{font-size:var(--t-xs);color:var(--muted)}
.nav{display:flex;flex-direction:column;gap:4px}
.nav button{display:flex;align-items:center;gap:12px;width:100%;padding:8px 12px;border:0;border-radius:var(--r1);
background:none;cursor:pointer;color:var(--ink-2);font-weight:600;font-size:var(--t-md);text-align:left}
.nav button:hover{background:var(--slate-bg)}
.nav button[aria-current=page]{background:var(--accent-tint);color:var(--accent-ink);box-shadow:inset 3px 0 0 var(--accent)}
.nav .badge{margin-left:auto;min-width:24px;padding:0 8px;border-radius:999px;background:var(--slate-bg);color:var(--slate);
font-size:var(--t-xs);font-weight:600;text-align:center;line-height:20px}
.nav .badge.alert{background:var(--amber-bg);color:var(--amber)}
.side-foot{margin-top:auto;display:flex;flex-direction:column;gap:var(--s1);padding:var(--s2);border:1px solid var(--line);
border-radius:var(--r2);background:var(--surface-2);font-size:var(--t-xs);color:var(--muted)}
.side-foot strong{display:flex;align-items:center;gap:8px;color:var(--ink-2);font-size:var(--t-sm);font-weight:600}
.side-foot .ic{width:16px;height:16px;color:var(--accent)}
.main{min-width:0;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap;
padding:var(--s1) var(--s4);min-height:64px;background:rgba(255,255,255,.97);border-bottom:1px solid var(--line)}
.crumb{font-weight:600;font-size:var(--t-lg);margin-right:auto}
.stat{display:flex;flex-direction:column;min-width:0;max-width:300px}
.stat .lbl{font-size:var(--t-xs);color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.stat .val{font-size:var(--t-sm);color:var(--ink);font-weight:600;overflow-wrap:anywhere}
.stat .sub{font-size:var(--t-xs);color:var(--muted)}
.who{display:flex;flex-direction:column;gap:2px}
.who label{font-size:var(--t-xs);color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.who input{width:180px;padding:6px 10px}
.banner{display:flex;align-items:center;gap:var(--s2);padding:12px var(--s4);background:var(--amber-bg);
border-bottom:1px solid var(--amber-line);color:var(--amber);font-weight:600;font-size:var(--t-md)}
.banner .ic{width:18px;height:18px}
.content{width:100%;max-width:1100px;margin:0 auto;padding:var(--s4) var(--s4) var(--s6)}
.page{display:flex;flex-direction:column;gap:var(--s3)}
.page-head h1{font-size:var(--t-2xl);line-height:1.25;font-weight:600}
.page-head p{margin-top:4px;color:var(--muted);max-width:720px}
.section-title{font-size:var(--t-lg);font-weight:600;margin-top:var(--s1)}
.generated{font-size:var(--t-xs);color:var(--muted)}

/* cards and panels */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:var(--s2)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);padding:var(--s2);
box-shadow:var(--shadow);min-width:0}
.card .k{font-size:var(--t-xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.card .v{font-size:var(--t-3xl);line-height:1.2;font-weight:600;margin-top:8px;overflow-wrap:anywhere}
.card .n{font-size:var(--t-xs);color:var(--muted);margin-top:4px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);box-shadow:var(--shadow);min-width:0;overflow:hidden}
.panel.pad{padding:var(--s2) var(--s3)}
.panel-head{display:flex;align-items:center;gap:var(--s1);padding:var(--s2) var(--s3);border-bottom:1px solid var(--line);flex-wrap:wrap}
.panel-head h2{font-size:var(--t-lg);font-weight:600}
.panel-head .count{margin-left:auto;color:var(--muted);font-size:var(--t-sm)}
.panel-body{padding:var(--s3)}
.intro{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:var(--s3);padding:var(--s3);
background:var(--surface);border:1px solid var(--accent-line);border-radius:var(--r3);box-shadow:var(--shadow)}
.intro h2{font-size:var(--t-xl);font-weight:600;line-height:1.3}
.intro p{color:var(--ink-2);margin-top:var(--s1)}
.intro ol{display:flex;flex-direction:column;gap:var(--s1);margin-top:var(--s2)}
.intro li{display:flex;gap:var(--s1);align-items:flex-start;font-size:var(--t-sm);color:var(--ink-2)}
.intro li b{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;flex:none;
background:var(--accent);color:#fff;font-size:var(--t-xs)}
.todo{border-left:1px solid var(--line);padding-left:var(--s3);display:flex;flex-direction:column;gap:var(--s1)}
.todo h3{font-size:var(--t-sm);text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.todo .big{font-size:var(--t-3xl);font-weight:600;line-height:1.1}

/* status chips */
.pill,.tag{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2px 10px;font-size:var(--t-xs);
font-weight:600;line-height:20px;border:1px solid;max-width:100%;overflow-wrap:anywhere;white-space:normal}
.pill::before,.tag.stage::before,.tag.dot::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.pill-official,.st-ok{color:var(--green);background:var(--green-bg);border-color:var(--green-line)}
.pill-rumor,.st-held{color:var(--amber);background:var(--amber-bg);border-color:var(--amber-line)}
.st-alert{color:var(--blue);background:var(--blue-bg);border-color:var(--blue-line)}
.pill-rejected,.st-rej,.st-dry{color:var(--slate);background:var(--slate-bg);border-color:var(--slate-line)}
.st-fail{color:var(--red);background:var(--red-bg);border-color:var(--red-line)}
.st-accent{color:var(--accent-ink);background:var(--accent-tint);border-color:var(--accent-line)}
.tag-plain{color:var(--slate);background:var(--surface);border-color:var(--line-strong)}
.tag-sample{color:#fff;background:var(--ink);border-color:var(--ink);letter-spacing:.06em}
.chips{display:flex;flex-wrap:wrap;gap:var(--s1);align-items:center}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:8px;padding:8px 16px;border-radius:var(--r1);border:1px solid var(--line-strong);
background:var(--surface);color:var(--ink);font-weight:600;font-size:var(--t-sm);cursor:pointer;line-height:20px;text-decoration:none}
.btn:hover{background:var(--slate-bg);color:var(--ink)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:var(--accent-ink);color:#fff}
.btn.small{padding:4px 10px;font-size:var(--t-xs)}
.btn[aria-disabled=true]{opacity:.55;cursor:not-allowed}
.btn .ic{width:16px;height:16px}
.copy.done{background:var(--green-bg);border-color:var(--green-line);color:var(--green)}

/* attention list */
.attention li{display:flex;align-items:flex-start;gap:var(--s2);padding:var(--s2) var(--s3);border-bottom:1px solid var(--line)}
.attention li:last-child{border-bottom:0}
.att-ic{width:32px;height:32px;border-radius:var(--r1);display:flex;align-items:center;justify-content:center;flex:none}
.att-ic .ic{width:18px;height:18px}
.att-ic.amber{background:var(--amber-bg);color:var(--amber)}
.att-ic.red{background:var(--red-bg);color:var(--red)}
.att-ic.green{background:var(--green-bg);color:var(--green)}
.att-ic.blue{background:var(--blue-bg);color:var(--blue)}
.att-text{min-width:0;flex:1}
.att-title{font-weight:600;overflow-wrap:anywhere}
.att-note{font-size:var(--t-sm);color:var(--muted);overflow-wrap:anywhere}
.all-clear{display:flex;align-items:center;gap:var(--s2);padding:var(--s4) var(--s3);color:var(--ink-2)}

/* pipeline */
.flow{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:var(--s2)}
.flow li{position:relative;min-width:0}
.flow li:not(:last-child)::after{content:"";position:absolute;top:36px;right:-14px;width:12px;height:12px;border-top:2px solid var(--line-strong);
border-right:2px solid var(--line-strong);transform:rotate(45deg);z-index:1}
.stage-box{display:flex;flex-direction:column;gap:4px;width:100%;height:100%;padding:var(--s2) 12px;text-align:left;cursor:pointer;
background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);box-shadow:var(--shadow)}
.stage-box:hover{border-color:var(--accent)}
.stage-num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;
background:var(--accent);color:#fff;font-size:var(--t-xs);font-weight:600}
.stage-name{font-weight:600;font-size:var(--t-sm);line-height:1.3;min-height:34px;margin-top:4px}
.stage-count{font-size:var(--t-3xl);line-height:1.2;font-weight:600}
.stage-hint{font-size:var(--t-xs);color:var(--muted)}
.stage-box.is-wait{border-color:var(--amber-line);background:#fffbeb}

/* toolbar and tables */
.toolbar{display:flex;gap:var(--s1);flex-wrap:wrap;align-items:center;padding:var(--s2) var(--s3);border-bottom:1px solid var(--line)}
input,select{font:inherit;font-size:var(--t-sm);color:var(--ink);background:var(--surface);border:1px solid var(--line-strong);
border-radius:var(--r1);padding:8px 12px;min-width:0;line-height:20px}
input[type=search]{flex:1 1 240px}
select{flex:0 1 176px}
.count-note{margin-left:auto;font-size:var(--t-sm);color:var(--muted)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{padding:12px 16px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);font-size:var(--t-sm);overflow-wrap:anywhere}
thead th{background:var(--surface-2);font-size:var(--t-xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;
white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tr.story{cursor:pointer}
tr.story:hover td{background:var(--surface-2)}
td.name{font-weight:600}
td.when{white-space:nowrap}
.sort{border:0;background:none;padding:0;font:inherit;color:inherit;text-transform:inherit;letter-spacing:inherit;cursor:pointer;
display:inline-flex;align-items:center;gap:4px}
.sort:hover{color:var(--ink)}
.sort .arr::after{content:"";display:inline-block;border:4px solid transparent;border-top-color:var(--line-strong);margin-top:4px}
th[aria-sort=ascending] .arr::after{border-top-color:transparent;border-bottom-color:var(--accent);margin-top:-4px}
th[aria-sort=descending] .arr::after{border-top-color:var(--accent)}
.row-title{border:0;background:none;padding:0;font:inherit;font-size:var(--t-md);font-weight:600;color:var(--ink);text-align:left;cursor:pointer}
.row-title:hover{color:var(--accent-ink);text-decoration:underline}
.row-tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.empty{display:flex;flex-direction:column;align-items:center;gap:var(--s1);padding:var(--s5) var(--s3);text-align:center;color:var(--muted)}
td.empty-cell{text-align:center;color:var(--muted);padding:var(--s4)}

/* drawer and lightbox */
.scrim{position:fixed;inset:0;background:rgba(15,23,42,.45);z-index:20}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(560px,100vw);background:var(--surface);z-index:21;box-shadow:var(--shadow-lg);
display:flex;flex-direction:column}
.drawer-head{display:flex;align-items:center;justify-content:space-between;padding:var(--s2) var(--s3);border-bottom:1px solid var(--line)}
.drawer-head span{font-size:var(--t-xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.drawer-body{padding:var(--s3);overflow-y:auto;display:flex;flex-direction:column;gap:var(--s3)}
.drawer-body h2{font-size:var(--t-xl);line-height:1.3;font-weight:600;overflow-wrap:anywhere}
.drawer-body h3{font-size:var(--t-xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:var(--s1)}
.kv{display:grid;grid-template-columns:132px minmax(0,1fr);gap:8px 16px;font-size:var(--t-sm)}
.kv dt{color:var(--muted)}
.kv dd{overflow-wrap:anywhere}
.src-list li{padding:8px 0;border-bottom:1px solid var(--line);font-size:var(--t-sm);overflow-wrap:anywhere}
.src-list li:last-child{border-bottom:0}
code{font-family:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace;font-size:var(--t-xs);background:var(--slate-bg);border:1px solid var(--line);
border-radius:6px;padding:2px 8px;overflow-wrap:anywhere}
.why{font-size:var(--t-sm);color:var(--ink-2)}
.summary{font-size:var(--t-sm);color:var(--ink-2)}
.make{font-size:var(--t-sm);color:var(--ink-2)}
.lightbox{position:fixed;inset:0;z-index:30;background:rgba(15,23,42,.92);display:flex;flex-direction:column;align-items:center;
justify-content:center;gap:var(--s2);padding:var(--s3)}
.lb-bar{display:flex;align-items:center;gap:var(--s2);color:#e2e8f0;font-size:var(--t-sm);width:100%;max-width:960px}
.lb-bar .lb-title{margin-right:auto;font-weight:600;overflow-wrap:anywhere}
.lb-stage{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;max-width:100%}
.lb-stage img{max-width:100%;max-height:calc(100vh - 160px);border-radius:var(--r1);background:#0f172a;display:block}
.lightbox .btn{background:#1e293b;border-color:#334155;color:#fff}
.lightbox .btn:hover{background:#334155}
.fb-tile{display:flex;align-items:center;justify-content:center;width:320px;height:420px;max-width:100%;border-radius:var(--r1);
background:var(--slate-bg);color:var(--muted);font-size:var(--t-sm);text-align:center;padding:var(--s2)}

/* carousels */
.car-list{display:flex;flex-direction:column;gap:var(--s3)}
.carousel-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r3);box-shadow:var(--shadow);overflow:hidden}
.carousel-card.flash{outline:2px solid var(--accent)}
.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--s2);flex-wrap:wrap;padding:var(--s3) var(--s3) 0}
.card-head .story-title{font-size:var(--t-xl);line-height:1.3;font-weight:600;overflow-wrap:anywhere;flex:1 1 320px}
.carousel-card .meta{padding:4px var(--s3) 0;font-size:var(--t-xs);color:var(--muted);overflow-wrap:anywhere}
.car-body{display:grid;grid-template-columns:180px minmax(0,1fr);gap:var(--s3);padding:var(--s3)}
.thumb{position:relative;display:block;aspect-ratio:3/4;border-radius:var(--r1);overflow:hidden;background:var(--slate-bg);border:1px solid var(--line)}
.thumb img{width:100%;height:100%;object-fit:contain;display:block;background:#0b1d42}
.thumb .fb{display:none;position:absolute;inset:0;align-items:center;justify-content:center;text-align:center;padding:8px;font-size:var(--t-xs);
color:var(--muted);background:var(--slate-bg)}
.thumb.broken img{display:none}
.thumb.broken .fb{display:flex}
button.slide{padding:0;border:0;background:none;cursor:pointer;border-radius:var(--r1);display:block;width:100%}
button.slide:hover .thumb{border-color:var(--accent)}
.thumbs{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:var(--s1)}
.strip-label{font-size:var(--t-xs);color:var(--muted);margin-bottom:var(--s1);font-weight:600}
.slide-n{display:flex;justify-content:center;gap:6px;align-items:center;font-size:var(--t-xs);color:var(--muted);margin-top:4px}
.slide-n a{font-weight:600}
.car-right{display:flex;flex-direction:column;gap:var(--s2);min-width:0}
.car-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:var(--s2);padding:0 var(--s3) var(--s3)}
.box{border:1px solid var(--line);border-radius:var(--r2);padding:var(--s2);background:var(--surface-2);min-width:0;display:flex;flex-direction:column;gap:var(--s1)}
.box h3{font-size:var(--t-sm);font-weight:600}
.box .cap{font-size:var(--t-sm);color:var(--ink-2);white-space:pre-wrap;overflow-wrap:anywhere}
.box .box-top{display:flex;align-items:center;justify-content:space-between;gap:var(--s1)}
.box ul{display:flex;flex-direction:column;gap:4px;font-size:var(--t-sm);overflow-wrap:anywhere}
.facts{display:grid;grid-template-columns:130px minmax(0,1fr);gap:6px 12px;font-size:var(--t-sm)}
.facts dt{color:var(--muted)}
.facts dd{margin:0;overflow-wrap:anywhere}
.dl-row{display:flex;flex-wrap:wrap;gap:var(--s1);align-items:center}
.review-area{padding:var(--s2) var(--s3);border-top:1px solid var(--line);background:var(--surface-2);font-size:var(--t-sm);display:flex;flex-direction:column;gap:var(--s1)}
.review{display:flex;gap:var(--s1);flex-wrap:wrap;align-items:center}
.review-group{display:flex;gap:var(--s1);flex-wrap:wrap;align-items:center}
.review .reason{flex:1 1 200px}
.review .post-url{flex:1 1 220px}
.act{display:inline-flex;align-items:center;padding:8px 16px;border-radius:var(--r1);border:1px solid var(--accent);background:var(--accent);
color:#fff;font-weight:600;font-size:var(--t-sm);cursor:pointer}
.act.secondary{background:var(--surface);color:var(--ink);border-color:var(--line-strong)}
.copy-row{display:flex;gap:var(--s1);flex-wrap:wrap}
.copy-row summary{cursor:pointer;color:var(--muted);font-size:var(--t-xs)}
.sample-banner{padding:var(--s1) var(--s3);background:var(--amber-bg);border-top:1px solid var(--amber-line);color:var(--amber);font-size:var(--t-sm);font-weight:600}
.no-slides{display:flex;align-items:center;justify-content:center;aspect-ratio:3/4;border:1px dashed var(--line-strong);border-radius:var(--r1);
color:var(--muted);font-size:var(--t-sm);text-align:center;padding:var(--s2)}

/* how it works and start here */
.nodes{display:grid;gap:var(--s3);grid-template-columns:repeat(4,minmax(0,1fr))}
.node{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);padding:var(--s2);box-shadow:var(--shadow);
display:flex;flex-direction:column;gap:var(--s1);min-width:0}
.node.human{border-color:var(--amber-line);background:#fffbeb}
.node .nic{width:40px;height:40px;border-radius:var(--r1);display:flex;align-items:center;justify-content:center;background:var(--accent-tint);color:var(--accent-ink)}
.node.human .nic{background:var(--amber-bg);color:var(--amber)}
.node h3{font-size:var(--t-md);font-weight:600;line-height:1.3}
.node p{font-size:var(--t-sm);color:var(--muted)}
.steps{counter-reset:step;display:flex;flex-direction:column}
.steps li{counter-increment:step;display:grid;grid-template-columns:32px minmax(0,1fr);gap:var(--s2);padding:var(--s2) var(--s3);border-bottom:1px solid var(--line)}
.steps li:last-child{border-bottom:0}
.steps li::before{content:counter(step);display:flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;
background:var(--accent);color:#fff;font-weight:600;font-size:var(--t-sm)}
.rules{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:var(--s2)}
.rules li{display:flex;gap:var(--s1);align-items:flex-start;padding:var(--s2);border:1px solid var(--line);border-radius:var(--r2);background:var(--surface);font-size:var(--t-sm)}
.rules .ic{color:var(--green);width:18px;height:18px;margin-top:2px}
.start-hero{padding:var(--s4);background:var(--surface);border:1px solid var(--accent-line);border-radius:var(--r3)}
.start-hero h1{font-size:var(--t-2xl);font-weight:600;line-height:1.3}
.start-hero p{margin-top:var(--s1);color:var(--ink-2);font-size:var(--t-lg);max-width:760px}

.toast{position:fixed;right:20px;bottom:20px;max-width:440px;padding:12px 16px;border-radius:var(--r2);z-index:40;
box-shadow:var(--shadow-lg);font-size:var(--t-md)}
.toast.ok{background:var(--green-bg);color:var(--green);border:1px solid var(--green-line)}
.toast.err{background:var(--red-bg);color:var(--red);border:1px solid var(--red-line)}
.toast a{color:inherit;font-weight:600}

/* responsive: laptop widths and below */
@media (max-width:1240px){
.content{padding:var(--s3)}
.topbar{padding:var(--s1) var(--s3)}
.flow{grid-template-columns:repeat(4,minmax(0,1fr))}
.flow li:nth-child(4)::after{display:none}
.nodes{grid-template-columns:repeat(2,minmax(0,1fr))}
.car-body{grid-template-columns:150px minmax(0,1fr)}
.intro{grid-template-columns:minmax(0,1fr)}
.todo{border-left:0;padding-left:0;border-top:1px solid var(--line);padding-top:var(--s2)}
}
@media (max-width:900px){
.app{grid-template-columns:minmax(0,1fr)}
.sidebar{position:static;height:auto;flex-direction:row;flex-wrap:wrap;align-items:center;border-right:0;border-bottom:1px solid var(--line);padding:var(--s2)}
.nav{flex-direction:row;flex-wrap:wrap}
.nav button{width:auto}
.side-foot{display:none}
.topbar{position:static}
.flow,.nodes{grid-template-columns:repeat(2,minmax(0,1fr))}
.flow li::after{display:none !important}
.car-body{grid-template-columns:minmax(0,1fr)}
.thumbs{grid-template-columns:repeat(3,minmax(0,1fr))}
.kv,.facts{grid-template-columns:minmax(0,1fr)}
.adv{width:100%}
}
/* phones */
@media (max-width:600px){
.content{padding:var(--s2)}
.topbar{gap:var(--s1);padding:var(--s1) var(--s2)}
.crumb{width:100%}
.stat{max-width:none}
.who input{width:100%}
.cards{grid-template-columns:repeat(2,minmax(0,1fr))}
.card .v{font-size:var(--t-2xl)}
.thumbs{grid-template-columns:repeat(2,minmax(0,1fr))}
.card-head,.car-body,.car-cols{padding-left:var(--s2);padding-right:var(--s2)}
.start-hero{padding:var(--s3)}
.start-hero p{font-size:var(--t-md)}
.nodes,.flow{grid-template-columns:minmax(0,1fr)}
th,td{padding:10px 12px}
.hide-sm{display:none}
.banner{padding:12px var(--s2)}
}
/* the Advanced area of the sidebar (Kint only) */
.adv{margin-top:var(--s1);border-top:1px solid var(--line);padding-top:var(--s1)}
.adv summary{cursor:pointer;padding:6px 12px;font-size:var(--t-xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.adv .nav-sub{display:flex;flex-direction:column;gap:4px;margin-top:4px}
.adv .nav-sub button{font-weight:500;font-size:var(--t-sm)}
.start-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--s2)}
.start-steps li{display:flex;gap:var(--s1);align-items:flex-start;padding:var(--s2);background:var(--surface);border:1px solid var(--line);
border-radius:var(--r2);font-size:var(--t-sm);color:var(--ink-2)}
.start-steps li b{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;flex:none;
background:var(--accent);color:#fff;font-size:var(--t-xs)}
@media (max-width:900px){.start-steps{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:600px){.start-steps{grid-template-columns:minmax(0,1fr)}}
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
      name = document.body.getAttribute('data-home') || 'start';
    }
    pages.forEach(function (p) { p.hidden = p.getAttribute('data-page') !== name; });
    var label = '';
    navs.forEach(function (b) {
      if (b.getAttribute('data-nav') === name) {
        b.setAttribute('aria-current', 'page'); label = b.getAttribute('data-label');
        var holder = b.closest('details'); if (holder) { holder.open = true; }
      }
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
      toast(button.getAttribute('data-kind') === 'caption' ? 'Caption copied.' : 'Command copied. Paste it into PowerShell.', true);
    }, function () { toast('Could not copy. Select the text and copy it by hand.', false); });
  });

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

  /* ---------- story drawer ---------- */
  var drawer = $('#drawer'), scrim = $('#scrim'), drawerBody = $('#drawer-body'), drawerOpener = null;
  function openDrawer(id, opener) {
    var tpl = document.getElementById(id);
    if (!tpl || !drawer) { return; }
    drawerBody.innerHTML = '';
    drawerBody.appendChild(tpl.content.cloneNode(true));
    drawer.hidden = false; scrim.hidden = false;
    document.body.classList.add('lock');
    drawerOpener = opener || document.activeElement;
    $('#drawer-close').focus();
  }
  function closeDrawer() {
    if (!drawer || drawer.hidden) { return; }
    drawer.hidden = true; scrim.hidden = true;
    document.body.classList.remove('lock');
    if (drawerOpener && drawerOpener.focus) { drawerOpener.focus(); }
  }
  if (scrim) { scrim.addEventListener('click', closeDrawer); }
  if ($('#drawer-close')) { $('#drawer-close').addEventListener('click', closeDrawer); }
  document.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-drawer]');
    if (opener) { openDrawer(opener.getAttribute('data-drawer'), opener); return; }
    var row = event.target.closest('tr.story');
    if (row && !event.target.closest('a')) {
      var title = row.querySelector('[data-drawer]');
      if (title) { openDrawer(title.getAttribute('data-drawer'), title); }
    }
  });

  /* ---------- go to another page ---------- */
  document.addEventListener('click', function (event) {
    var go = event.target.closest('[data-go]');
    if (!go) { return; }
    closeDrawer();
    show(go.getAttribute('data-go'));
    var stage = go.getAttribute('data-stage');
    if (stage !== null && go.getAttribute('data-go') === 'stories') {
      var select = $('#f-stage');
      if (select) { select.value = stage; applyStories(); }
    }
    var target = go.getAttribute('data-target');
    if (target) {
      var holder = document.getElementById(target);
      if (holder) {
        holder.hidden = false;
        holder.scrollIntoView({ block: 'start' });
        holder.classList.add('flash');
        setTimeout(function () { holder.classList.remove('flash'); }, 1800);
      }
    }
  });

  /* ---------- stories: filter and sort ---------- */
  var body = $('#story-list');
  var rows = $$('#story-list tr.story');
  var controls = {
    search: $('#search'), label: $('#f-label'), brand: $('#f-brand'),
    stage: $('#f-stage'), status: $('#f-status'), range: $('#f-range')
  };
  var DAY = 24 * 60 * 60 * 1000;
  function applyStories() {
    if (!controls.search) { return; }
    var text = controls.search.value.trim().toLowerCase();
    var range = controls.range ? controls.range.value : 'all';
    var cutoff = range === '24h' ? Date.now() - DAY : range === '7d' ? Date.now() - 7 * DAY : 0;
    var shown = 0;
    rows.forEach(function (row) {
      var d = row.dataset;
      function pick(el) { return el ? el.value : ''; }
      var ok = (!text || d.text.indexOf(text) !== -1)
        && (!pick(controls.label) || d.label === controls.label.value)
        && (!pick(controls.brand) || d.brand === controls.brand.value)
        && (!pick(controls.stage) || d.stage === controls.stage.value)
        && (!pick(controls.status) || d.status === controls.status.value)
        && (!cutoff || Number(d.ts) >= cutoff);
      row.hidden = !ok;
      if (ok) { shown += 1; }
    });
    var count = $('#count');
    if (count) { count.textContent = shown + ' of ' + rows.length + ' stories shown'; }
  }
  Object.keys(controls).forEach(function (key) {
    var el = controls[key];
    if (el) { el.addEventListener('input', applyStories); el.addEventListener('change', applyStories); }
  });
  var sortKey = 'ts', sortDir = -1;
  function sortRows() {
    if (!body || !rows.length) { return; }
    var numeric = sortKey === 'ts' || sortKey === 'stagei';
    rows.sort(function (a, b) {
      var x = a.dataset[sortKey], y = b.dataset[sortKey];
      var order = numeric ? Number(x) - Number(y) : String(x).localeCompare(String(y));
      return order * sortDir;
    });
    rows.forEach(function (row) { body.appendChild(row); });
    $$('#story-table th[data-col]').forEach(function (th) {
      th.setAttribute('aria-sort', th.getAttribute('data-col') === sortKey ? (sortDir === 1 ? 'ascending' : 'descending') : 'none');
    });
  }
  $$('#story-table .sort').forEach(function (button) {
    button.addEventListener('click', function () {
      var key = button.getAttribute('data-sort');
      if (key === sortKey) { sortDir = -sortDir; } else { sortKey = key; sortDir = key === 'ts' ? -1 : 1; }
      sortRows();
    });
  });
  sortRows();
  applyStories();

  /* ---------- activity: filter ---------- */
  var events = $$('#activity-list tr.ev');
  var aType = $('#a-type'), aSearch = $('#a-search'), aRange = $('#a-range'), aCount = $('#a-count');
  function applyActivity() {
    if (!aType) { return; }
    var text = aSearch.value.trim().toLowerCase();
    var cutoff = aRange.value === '24h' ? Date.now() - DAY : aRange.value === '7d' ? Date.now() - 7 * DAY : 0;
    var shown = 0;
    events.forEach(function (row) {
      var ok = (!aType.value || row.getAttribute('data-type') === aType.value)
        && (!text || row.getAttribute('data-text').indexOf(text) !== -1)
        && (!cutoff || Number(row.getAttribute('data-ts')) >= cutoff);
      row.hidden = !ok;
      if (ok) { shown += 1; }
    });
    if (aCount) { aCount.textContent = shown + ' of ' + events.length + ' events shown'; }
  }
  [aType, aSearch, aRange].forEach(function (el) {
    if (el) { el.addEventListener('input', applyActivity); el.addEventListener('change', applyActivity); }
  });
  applyActivity();

  /* ---------- carousels: drafts or samples ---------- */
  var kind = $('#carousel-kind');
  function applyKind() {
    if (!kind) { return; }
    $$('#carousel-list .carousel-card').forEach(function (card) {
      card.hidden = !(kind.value === 'all' || card.getAttribute('data-kind') === kind.value);
    });
  }
  if (kind) { kind.addEventListener('change', applyKind); applyKind(); }

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
    } else if (drawer && !drawer.hidden) {
      if (event.key === 'Escape') { closeDrawer(); } else { trap(drawer, event); }
    }
  });

  show(location.hash.replace('#', '') || document.body.getAttribute('data-home') || 'start');
})();
"""
