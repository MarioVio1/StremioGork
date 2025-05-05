from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from contextlib import asynccontextmanager
import os
import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
from curl_cffi.requests import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
import logging

# Configura logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Carica config.json
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

# Configurazione proxy
config = load_config()
proxies = {"http": config["Proxy_Settings"]["webshare"], "https": config["Proxy_Settings"]["webshare"]}
MFP_URL = config["Proxy_Settings"]["mediaflow"]
MFP_PASSWORD = config["Proxy_Settings"]["mediaflow_password"]

# Header realistici
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/"
}

# Chiave TMDB
TMDB_API_KEY = "9f6dbcbddf9565f6a0f004fca81f83ee"

# Funzione per proxyare stream con MediaFlow
def proxy_stream_with_mediaflow(url, host=None):
    encoded_url = urllib.parse.quote(url)
    if host:
        encoded_host = urllib.parse.quote(host)
        return f"{MFP_URL}/extractor/video?api_password={MFP_PASSWORD}&d={encoded_url}&host={encoded_host}&redirect_stream=false"
    return f"{MFP_URL}/proxy?url={encoded_url}&api_password={MFP_PASSWORD}"

# Funzione per ottenere metadati TMDB
async def get_tmdb_metadata(id, client, type="movie"):
    try:
        if id.startswith("tmdb:"):
            tmdb_id = id.replace("tmdb:", "")
            logger.info(f"Risoluzione TMDB ID diretto: {tmdb_id}")
        elif id.startswith("tt"):
            url = f"https://api.themoviedb.org/3/find/{id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
            logger.info(f"Richiesta TMDB per IMDb ID: {url}")
            response = await client.get(url, headers=HEADERS, timeout=10, proxies=proxies)
            response.raise_for_status()
            data = response.json()
            if data["movie_results"]:
                tmdb_id = data["movie_results"][0]["id"]
                logger.info(f"Trovato TMDB ID per film: {tmdb_id}")
            elif data["tv_results"]:
                tmdb_id = data["tv_results"][0]["id"]
                logger.info(f"Trovato TMDB ID per serie: {tmdb_id}")
            else:
                logger.error(f"Nessun risultato TMDB per {id}")
                return {
                    "title": "Unknown",
                    "poster": config["General"]["Icon"],
                    "description": "Contenuto non trovato",
                    "genres": ["Streaming"]
                }
        else:
            tmdb_id = id
            logger.info(f"Usato ID diretto: {tmdb_id}")

        url = f"https://api.themoviedb.org/3/{'movie' if type == 'movie' else 'tv'}/{tmdb_id}?api_key={TMDB_API_KEY}&language=it-IT"
        logger.info(f"Richiesta metadati TMDB: {url}")
        response = await client.get(url, headers=HEADERS, timeout=10, proxies=proxies)
        response.raise_for_status()
        data = response.json()

        if not data.get("id"):
            logger.error(f"Risposta TMDB vuota o invalida per {tmdb_id}")
            return {
                "title": "Unknown",
                "poster": config["General"]["Icon"],
                "description": "Contenuto non trovato",
                "genres": ["Streaming"]
            }

        title = data.get("title", data.get("name", "Unknown"))
        poster = f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get("poster_path") else config["General"]["Icon"]
        description = data.get("overview", f"Stream per {title}")
        genres = [genre["name"] for genre in data.get("genres", [])]

        logger.info(f"Metadati trovati per {id}: {title}")
        return {
            "title": title,
            "poster": poster,
            "description": description,
            "genres": genres
        }
    except Exception as e:
        logger.error(f"Errore TMDB per {id}: {str(e)}")
        return {
            "title": "Unknown",
            "poster": config["General"]["Icon"],
            "description": f"Errore nel recupero dei metadati: {str(e)}",
            "genres": ["Streaming"]
        }

# ... (le funzioni di scraping rimangono invariate rispetto alla versione precedente)

# Manifest
MANIFEST = {
    "id": "com.mariovio01.stremio",
    "version": "1.0.0",
    "name": "Mario's Stremio Addon",
    "description": "Addon per streaming HTTPS di film, serie e anime in italiano",
    "resources": ["stream", "meta"],
    "types": ["movie", "series"],
    "catalogs": [],
    "logo": "https://creazilla-store.fra1.digitaloceanspaces.com/emojis/49647/pizza-emoji-clipart-md.png"
}

def respond_with(data):
    resp = JSONResponse(data)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = '*'
    return resp

# Endpoint per la homepage
@app.get("/", response_class=FileResponse)
async def homepage():
    return FileResponse("static/index.html")

# Endpoint per il manifest
@app.get("/{config:path}/manifest.json")
def addon_manifest(config: str):
    return respond_with(MANIFEST)

@app.get("/manifest.json")
def manifest():
    return respond_with(MANIFEST)

# Endpoint per gli stream (invariato)
@app.get("/{config:path}/stream/{type}/{id}.json")
@limiter.limit("5/second")
async def stream(request: Request, config: str, type: str, id: str):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    config_data = load_config()
    streams = []

    provider_map = {
        "SC": "StreamingCommunity",
        "CB1": "CB01_meme",
        "CB2": "CB01_net",
        "ES1": "Eurostreaming_my",
        "ES2": "Eurostreaming_esq",
        "FM": "Filmez",
        "AD": "Altadefinizione",
        "GS": "Guardaserie",
        "TF": "Tantifilm",
        "AW": "AnimeWorld",
        "AU": "AnimeUnity",
        "TI": "ToonItalia",
        "AS": "AnimeSaturn",
        "LC": "LordChannel",
        "SW": "StreamingWatch",
        "DDL": "DDLStream",
        "OST": "OnlineSerieTV",
        "GHD": "GuardaHD"
    }
    provider_maps = {name: "0" for name in provider_map.values()}
    config_providers = config.split("|") if "|" in config else config.split("%7C")
    for provider in config_providers:
        if provider in provider_map:
            provider_maps[provider_map[provider]] = "1"

    MFP = "0"
    if "MFP[" in config:
        mfp_data = config.split("MFP[")[1].split(")")[0]
        MFP_URL, MFP_PASSWORD = mfp_data.split(",")
        MFP_PASSWORD = MFP_PASSWORD[:-2]
        MFP = "1"

    async with AsyncSession(proxies=proxies) as client:
        metadata = await get_tmdb_metadata(id, client, type)
        search_query = metadata["title"] if metadata["title"] != "Unknown" else id.replace("tmdb:", "").replace("tt", "")

        logger.info(f"Ricerca stream per {type}/{id} con query: {search_query}")

        for site_name, site in config_data["Siti"].items():
            if site["enabled"] and provider_maps.get(site_name, "0") == "1":
                url = site["url"]
                use_proxy = site.get(f"{site_name[:2]}_PROXY", 0) == 1
                logger.info(f"Ricerca stream su {site_name} per {search_query}")

                site_streams = []
                if site_name == "StreamingCommunity":
                    site_streams = await scrape_streamingcommunity(url, search_query, client, use_proxy)
                elif site_name in ["CB01_meme", "CB01_net"]:
                    site_streams = await scrape_cb01(url, search_query, client, use_proxy)
                elif site_name in ["Eurostreaming_my", "Eurostreaming_esq"]:
                    site_streams = await scrape_eurostreaming(url, search_query, client, use_proxy)
                elif site_name == "Filmez":
                    site_streams = await scrape_filmez(url, search_query, client, use_proxy)
                elif site_name == "Altadefinizione":
                    site_streams = await scrape_altadefinizione(url, search_query, client, use_proxy)
                elif site_name == "Guardaserie":
                    site_streams = await scrape_guardaserie(url, search_query, client, use_proxy)
                elif site_name == "Tantifilm":
                    site_streams = await scrape_tantifilm(url, search_query, client, use_proxy)
                elif site_name == "AnimeWorld":
                    site_streams = await scrape_animeworld(url, search_query, client, use_proxy)
                elif site_name == "AnimeUnity":
                    site_streams = await scrape_animeunity(url, search_query, client, use_proxy)
                elif site_name == "ToonItalia":
                    site_streams = await scrape_toonitalia(url, search_query, client, use_proxy)
                elif site_name == "AnimeSaturn":
                    site_streams = await scrape_animesaturn(url, search_query, client, use_proxy)
                elif site_name == "LordChannel":
                    site_streams = await scrape_lordchannel(url, search_query, client, use_proxy)
                elif site_name == "StreamingWatch":
                    site_streams = await scrape_streamingwatch(url, search_query, client, use_proxy)
                elif site_name == "DDLStream":
                    site_streams = await scrape_ddlstream(url, search_query, client, use_proxy)
                elif site_name == "OnlineSerieTV":
                    site_streams = await scrape_onlineserietv(url, search_query, client, use_proxy)
                elif site_name == "GuardaHD":
                    site_streams = await scrape_guardahd(url, search_query, client, use_proxy)

                for stream in site_streams:
                    behavior_hints = {}
                    if "d000d.com" in stream:
                        behavior_hints = {
                            "notWebReady": True,
                            "proxyHeaders": {"request": {"Referer": "https://d000d.com/"}}
                        }
                    elif "mixdrop" in stream and MFP == "1":
                        stream = proxy_stream_with_mediaflow(stream, "Mixdrop")
                    elif "maxstream" in stream:
                        stream = proxy_stream_with_mediaflow(stream)

                    streams.append({
                        "title": f"{config['General']['Icon']}{site_name}",
                        "url": stream,
                        "behaviorHints": behavior_hints if behavior_hints else None
                    })

                if site_streams:
                    logger.info(f"Trovati {len(site_streams)} stream su {site_name} per {search_query}")

    if not streams:
        raise HTTPException(status_code=404)
    logger.info(f"Stream {type}/{id}: {len(streams)} stream trovati")
    return respond_with({"streams": streams})

# Endpoint per i metadati (aggiornato)
@app.get("/{config:path}/meta/{type}/{id}.json")
@limiter.limit("20/second")
async def meta(request: Request, config: str, type: str, id: str):
    if type not in MANIFEST["types"]:
        logger.error(f"Tipo non supportato: {type}")
        raise HTTPException(status_code=404, detail=f"Tipo {type} non supportato")
    
    async with AsyncSession(proxies=proxies) as client:
        try:
            metadata = await get_tmdb_metadata(id, client, type)
            if metadata["title"] == "Unknown":
                logger.warning(f"Metadati non trovati per {type}/{id}, usato fallback")
            
            meta_response = {
                "meta": {
                    "id": id,
                    "type": type,
                    "name": metadata["title"],
                    "poster": metadata["poster"],
                    "description": metadata["description"],
                    "genres": metadata["genres"]
                }
            }
            logger.info(f"Metadati restituiti per {type}/{id}: {metadata['title']}")
            return respond_with(meta_response)
        except Exception as e:
            logger.error(f"Errore nell'elaborazione dei metadati per {type}/{id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Errore server: {str(e)}")

# Gestore lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    logger.info(f"Caricati {len(config['Siti'])} siti dal config")
    yield

app.lifespan = lifespan

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
