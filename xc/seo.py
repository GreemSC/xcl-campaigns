"""Search engines and link previews: <head> tags of each page, sitemap.xml, robots.txt, the share card.

The board is a tool for XCL contributors (who does what, test reports, duplicate PRs and issues, a JSON API for
coding agents); how far GTA VI gets is one of its pages, not the whole point. Titles and descriptions say so.
Nothing here writes a time of day: deploy/publish.sh skips a push when only "HH:MM UTC" stamps changed."""
import datetime
import json
import os
import shutil
from html import escape as e

BASE = os.environ.get("XC_BASE_URL", "https://greemsc.github.io/xcl-campaigns").rstrip("/")
REPO = os.environ.get("XC_REPO", "xcl-dev/xcl")
SITE = "XCL contributor board"
DESC = ("Community board that helps XCL contributors coordinate: who works on what, test reports, duplicate PRs and "
        "issues, a JSON API for agents, and how far testers report GTA VI (GTA 6) gets.")
CARD = "og.png"                 # 1200x630, repository root, copied into the site (made by xc/seo.py card)
ICON = "favicon.svg"
PAGES = {}                      # path -> (title, description), filled by head() during one render pass

XCL = {"@type": "SoftwareSourceCode", "name": "XCL", "codeRepository": f"https://github.com/{REPO}",
       "description": "Compatibility layer for running Xbox Series X|S games you own on a Windows PC."}
GAME = {"@type": "VideoGame", "name": "Grand Theft Auto VI", "alternateName": ["GTA VI", "GTA 6"]}


def url(path):
    return f"{BASE}/" if path in ("", "index.html") else f"{BASE}/{path}"


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def head(title, description=None, path=None, crumb=None):
    """Tags for <head>. path = file name in the site ("index.html", "campaign-1269.html"); without it, only the
    description is written (no canonical, not in the sitemap). crumb = short page name for the breadcrumb."""
    d = description or DESC
    o = [f'<meta name="description" content="{e(d)}">', '<meta name="theme-color" content="#2f6f4f">',
         f'<link rel="icon" href="{ICON}" type="image/svg+xml">']
    for env, name in (("XC_GOOGLE_VERIFY", "google-site-verification"), ("XC_BING_VERIFY", "msvalidate.01")):
        if os.environ.get(env):
            o.append(f'<meta name="{name}" content="{e(os.environ[env])}">')
    if path is None:
        return "".join(o)
    PAGES[path] = (title, d)
    u, img = url(path), f"{BASE}/{CARD}"
    o += [f'<link rel="canonical" href="{e(u)}">',
          '<meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large">',
          '<meta property="og:type" content="website">', f'<meta property="og:site_name" content="{SITE}">',
          f'<meta property="og:title" content="{e(title)}">', f'<meta property="og:description" content="{e(d)}">',
          f'<meta property="og:url" content="{e(u)}">', f'<meta property="og:image" content="{e(img)}">',
          '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
          f'<meta property="og:image:alt" content="{SITE}: tasks, test reports, duplicates and GTA VI progress for XCL">',
          '<meta property="og:locale" content="en_US">', '<meta name="twitter:card" content="summary_large_image">',
          f'<meta name="twitter:title" content="{e(title)}">', f'<meta name="twitter:description" content="{e(d)}">',
          f'<meta name="twitter:image" content="{e(img)}">',
          '<script type="application/ld+json">' + json.dumps(graph(title, d, path, crumb), ensure_ascii=False,
                                                              separators=(",", ":")).replace("</", "<\\/") + "</script>"]
    return "".join(o)


def graph(title, d, path, crumb):
    """schema.org: the site, this page, its breadcrumb; on the home page also the open data (Google Dataset Search)."""
    site = {"@type": "WebSite", "@id": f"{BASE}/#website", "url": f"{BASE}/", "name": SITE,
            "alternateName": ["XCL board", "xcl-campaigns"], "description": DESC, "inLanguage": "en",
            "creator": {"@type": "Person", "name": "GreemSC", "url": "https://github.com/GreemSC"}, "about": [XCL, GAME]}
    pg = {"@type": "WebPage", "@id": url(path), "url": url(path), "name": title, "description": d, "inLanguage": "en",
          "isPartOf": {"@id": f"{BASE}/#website"}, "dateModified": today(), "about": [XCL, GAME],
          "audience": {"@type": "Audience", "audienceType": "XCL contributors, testers and coding agents"},
          "primaryImageOfPage": {"@type": "ImageObject", "url": f"{BASE}/{CARD}", "width": 1200, "height": 630}}
    out = [site, pg]
    if path not in ("", "index.html"):
        pg["breadcrumb"] = {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE, "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": crumb or title.split(" · ")[0], "item": url(path)}]}
    else:
        out.append({"@type": "Dataset", "@id": f"{BASE}/#data", "name": "XCL project data for contributors",
                    "description": "Machine-readable state of the XCL project (xcl-dev/xcl) built every few minutes from "
                                   "public GitHub data (unofficial, made by contributors): campaign tasks and who holds them, measurement results per hardware "
                                   "class, test reports and the furthest GTA VI stage reported per platform, duplicate pull requests and "
                                   "issues, open PRs per file and code area.",
                    "url": f"{BASE}/", "isAccessibleForFree": True, "dateModified": today(), "inLanguage": "en",
                    "creator": site["creator"],
                    "keywords": ["XCL", "GTA VI", "GTA 6", "Xbox Series", "compatibility layer", "Wine", "Proton",
                                 "duplicate pull requests", "test reports", "open source coordination"],
                    "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{BASE}/{p}"}
                                     for p in ("api/v2/index.json", "api/progress.json", "api/overview.json",
                                               "api/duplicates.json")]})
    return {"@context": "https://schema.org", "@graph": out}


def write(out):
    """sitemap.xml (HTML pages seen this pass + llms.txt + api/v2/index.json), robots.txt, icon and share card.
    A robots.txt under /xcl-campaigns/ is not read by crawlers (only the host root's is): the sitemap is submitted in
    Google Search Console / Bing Webmaster Tools; robots.txt is kept for tools that look for it next to the site."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in (CARD, ICON):
        if os.path.exists(os.path.join(here, f)):
            shutil.copy(os.path.join(here, f), f"{out}/{f}")
    day = today()
    rank = lambda p: (p != "index.html", not p.startswith("campaign-"), p)
    urls = [(url(p), "1.0" if p == "index.html" else "0.8" if p.startswith("campaign-") else "0.6")
            for p in sorted(PAGES, key=rank) if os.path.exists(f"{out}/{p}")]
    urls += [(f"{BASE}/{p}", "0.3") for p in ("llms.txt", "api/v2/index.json") if os.path.exists(f"{out}/{p}")]
    with open(f"{out}/sitemap.xml", "w") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 + "".join(f"<url><loc>{e(u)}</loc><lastmod>{day}</lastmod><priority>{p}</priority></url>\n" for u, p in urls)
                 + "</urlset>\n")
    with open(f"{out}/robots.txt", "w") as fh:
        fh.write(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    return {"sitemap_urls": len(urls)}


def card(path=CARD):
    """Draw the 1200x630 share card (run once by hand: python -m xc.seo; needs Pillow and Noto Sans)."""
    from PIL import Image, ImageDraw, ImageFont
    font = lambda w, s: ImageFont.truetype(f"/usr/share/fonts/noto/NotoSans-{w}.ttf", s)
    im = Image.new("RGB", (1200, 630), "#161615")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 1200, 10), fill="#6fc196")
    d.text((72, 70), "XCL contributor board", font=font("Bold", 76), fill="#ecebe6")
    d.text((72, 172), "Coordinate work on XCL, the Xbox Series to PC layer", font=font("Regular", 38), fill="#c9c8c1")
    y = 270
    for line in ("Who works on what: campaign tasks and claims", "Test reports and measurements per GPU and OS",
                 "Duplicate PRs and issues, a JSON API for agents", "How far GTA VI gets on Windows and Linux"):
        d.ellipse((76, y + 17, 92, y + 33), fill="#6fc196")
        d.text((112, y), line, font=font("Regular", 34), fill="#ecebe6")
        y += 62
    d.text((72, 548), "greemsc.github.io/xcl-campaigns · unofficial, built from public GitHub data",
           font=font("Regular", 26), fill="#9d9c95")
    im.save(path, optimize=True)
    return path


if __name__ == "__main__":
    print(card())
