import json
import uuid
import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import logging
import os

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurazione FastAPI
app = FastAPI()

# Aggiungi middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

# Mappa per salvare le configurazioni dei siti
config_map = {}

# Manifest di base
base_manifest = {
    "id": "com.veezie.streaming",
    "version": "1.0.0",
    "name": "Veezie Streaming Addon",
    "description": "Film, serie, anime e Live TV da siti personalizzati",
    "resources": ["catalog", "meta", "stream"],
    "types": ["movie", "series", "anime", "channel"],
    "catalogs": [
        {"type": "movie", "id": "veezie-movies", "name": "Veezie Movies", "extra": [{"name": "search"}]},
        {"type": "series", "id": "veezie-series", "name": "Veezie Series", "extra": [{"name": "search"}]},
        {"type": "anime", "id": "veezie-anime", "name": "Veezie Anime", "extra": [{"name": "search"}]},
        {"type": "channel", "id": "veezie-channels", "name": "Veezie Live TV", "extra": [{"name": "search"}]},
    ],
}

# Funzione per cercare contenuti sui siti
async def search_on_site(url, query, content_type):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/search?q={query}", headers=headers, timeout=5) as response:
                if response.status != 200:
                    logger.warning(f"Errore nella ricerca su {url}: {response.status}")
                    return []
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                results = []

                # Scraping generico
                for item in soup.select("div[class*='item'], article, .search-result, li"):
                    title = item.select_one("h2, h3, .title, a")
                    link = item.select_one("a[href]")
                    if title and link and link.get("href"):
                        title_text = title.get_text(strip=True)
                        href = link["href"]
                        full_url = href if href.startswith("http") else f"{url.rstrip('/')}/{href.lstrip('/')}"
                        results.append({"title": title_text, "url": full_url, "type": content_type})

                return results
    except Exception as e:
        logger.error(f"Errore durante la ricerca su {url}: {str(e)}")
        return []

# Route per l'interfaccia web
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "manifest": json.dumps(base_manifest, indent=2)
        }
    )

# Route per salvare i siti
@app.post("/configure")
async def configure(request: Request):
    try:
        data = await request.json()
        sites = data.get("sites", [])
        config_id = str(uuid.uuid4()).replace("-", "")
        
        # Normalizza i dati dei siti
        config_sites = []
        for site in sites:
            domain = site.get("domain", "").strip()
            if not domain or not domain.startswith("http"):
                continue
            config_sites.append({
                "domain": domain,
                "enabled": True,
                "types": site.get("types", ["movie", "series"])
            })

        config_map[config_id] = config_sites
        addon_url = f"https://{request.headers['host']}/{config_id}/manifest.json"
        return {"addonUrl": addon_url}
    except Exception as e:
        logger.error(f"Errore nella configurazione: {str(e)}")
        return {"error": f"Configurazione non valida: {str(e)}"}

# Route per il manifest
@app.get("/{config_id}/manifest.json")
async def get_manifest(config_id: str):
    if config_id not in config_map:
        return {"error": "Configurazione non trovata"}
    return base_manifest

# Route per il catalogo (ricerca)
@app.get("/{config_id}/catalog/{content_type}/{catalog_id}.json")
async def catalog_handler(config_id: str, content_type: str, catalog_id: str, request: Request):
    if config_id not in config_map:
        return {"metas": []}

    query = request.query_params.get("search", "")
    if not query:
        return {"metas": []}

    sites = config_map.get(config_id, [])
    metas = []
    for site in sites:
        if content_type in site["types"]:
            results = await search_on_site(site["domain"], query, content_type)
            for result in results:
                meta = {
                    "id": f"veezie:{result['url']}",
                    "type": content_type,
                    "name": result["title"],
                }
                metas.append(meta)

    return {"metas": metas[:50]}

# Route per i metadati (minima)
@app.get("/{config_id}/meta/{content_type}/{item_id}.json")
async def meta_handler(config_id: str, content_type: str, item_id: str):
    if config_id not in config_map:
        return {"meta": {}}

    _, url = item_id.split(":", 1)
    return {
        "meta": {
            "id": item_id,
            "type": content_type,
            "name": url.split("/")[-1]  # Nome approssimativo basato sull'URL
        }
    }

# Route per gli stream
@app.get("/{config_id}/stream/{content_type}/{item_id}.json")
async def stream_handler(config_id: str, content_type: str, item_id: str):
    if config_id not in config_map:
        return {"streams": []}

    _, url = item_id.split(":", 1)
    return {
        "streams": [
            {
                "title": "Veezie Stream",
                "url": url
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
