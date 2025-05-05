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
        elif id.startswith("tt"):
            url = f"https://api.themoviedb.org/3/find/{id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
            response = await client.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            tmdb_id = data["movie_results"][0]["id"] if data["movie_results"] else data["tv_results"][0]["id"]
        else:
            tmdb_id = id

        url = f"https://api.themoviedb.org/3/{'movie' if type == 'movie' else 'tv'}/{tmdb_id}?api_key={TMDB_API_KEY}&language=it-IT"
        response = await client.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        title = data.get("title", data.get("name", "Unknown"))
        poster = f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get("poster_path") else config["General"]["Icon"]
        description = data.get("overview", f"Stream per {title}")
        genres = [genre["name"] for genre in data.get("genres", [])]

        return {
            "title": title,
            "poster": poster,
            "description": description,
            "genres": genres
        }
    except Exception as e:
        logger.error(f"Errore TMDB per {id}: {e}")
        return {
            "title": "Unknown",
            "poster": config["General"]["Icon"],
            "description": "Contenuto non identificato",
            "genres": ["Streaming"]
        }

# Funzioni di scraping
async def scrape_streamingcommunity(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/search?q={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca StreamingCommunity: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['card', 'media', 'item', 'movie']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"StreamingCommunity trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping StreamingCommunity {url}: {e}")
        return []

async def scrape_cb01(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/search?query={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca CB01: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['film', 'card', 'movie', 'post', 'item']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"CB01 trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping CB01 {url}: {e}")
        return []

async def scrape_eurostreaming(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/search?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Eurostreaming: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['post', 'card', 'item', 'serie']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Eurostreaming trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Eurostreaming {url}: {e}")
        return []

async def scrape_filmez(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Filmez: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['movie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Filmez trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Filmez {url}: {e}")
        return []

async def scrape_altadefinizione(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Altadefinizione: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['movie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Altadefinizione trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Altadefinizione {url}: {e}")
        return []

async def scrape_guardaserie(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/search?q={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Guardaserie: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['serie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Guardaserie trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Guardaserie {url}: {e}")
        return []

async def scrape_tantifilm(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Tantifilm: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['movie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Tantifilm trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Tantifilm {url}: {e}")
        return []

async def scrape_animeworld(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/search?keyword={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Animeworld: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['anime', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Animeworld trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Animeworld {url}: {e}")
        return []

async def scrape_animeunity(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Animeunity: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['anime', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Animeunity trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Animeunity {url}: {e}")
        return []

async def scrape_toonitalia(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Toonitalia: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['anime', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Toonitalia trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Toonitalia {url}: {e}")
        return []

async def scrape_animesaturn(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/animelist?search={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Animesaturn: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['anime', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Animesaturn trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Animesaturn {url}: {e}")
        return []

async def scrape_filmpertutti(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Filmpertutti: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['movie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Filmpertutti trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Filmpertutti {url}: {e}")
        return []

async def scrape_streamingwatch(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Streamingwatch: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['movie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Streamingwatch trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Streamingwatch {url}: {e}")
        return []

async def scrape_ddlstream(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Ddlstream: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['movie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Ddlstream trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Ddlstream {url}: {e}")
        return []

async def scrape_lordchannel(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/search?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Lordchannel: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['article', 'div'], class_=['post', 'movie', 'card', 'item']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Lordchannel trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Lordchannel {url}: {e}")
        return []

async def scrape_guardahd(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/search?q={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca GuardaHD: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['video-item', 'movie', 'card', 'item']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"GuardaHD trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping GuardaHD {url}: {e}")
        return []

async def scrape_onlineserietv(url, search_query, client, use_proxy=False):
    try:
        search_url = f"{url}/?s={urllib.parse.quote(search_query)}"
        logger.info(f"Ricerca Onlineserietv: {search_url}")
        response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for item in soup.find_all(['div', 'article'], class_=['serie', 'card', 'item', 'post']):
            link = item.find('a', href=True)
            if link and ("maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "d000d.com" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
        logger.info(f"Onlineserietv trovati {len(streams)} stream per {search_query}")
        return streams
    except Exception as e:
        logger.error(f"Errore scraping Onlineserietv {url}: {e}")
        return []

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

# Endpoint per gli stream
@app.get("/{config:path}/stream/{type}/{id}.json")
@limiter.limit("5/second")
async def stream(request: Request, config: str, type: str, id: str):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    config_data = load_config()
    streams = []

    # Gestione provider
    provider_map = {
        "SC": "StreamingCommunity",
        "CB": "CB01",
        "ES": "Eurostreaming",
        "FZ": "Filmez",
        "AD": "Altadefinizione",
        "GS": "Guardaserie",
        "TF": "Tantifilm",
        "AW": "Animeworld",
        "AU": "Animeunity",
        "TI": "Toonitalia",
        "AS": "Animesaturn",
        "FP": "Filmpertutti",
        "SW": "Streamingwatch",
        "DS": "Ddlstream",
        "LC": "Lordchannel",
        "GHD": "GuardaHD",
        "OST": "Onlineserietv"
    }
    provider_maps = {name: "0" for name in provider_map.values()}
    config_providers = config.split("|") if "|" in config else config.split("%7C")
    for provider in config_providers:
        if provider in provider_map:
            provider_maps[provider_map[provider]] = "1"

    # Gestione MFP
    MFP = "0"
    if "MFP[" in config:
        mfp_data = config.split("MFP[")[1].split(")")[0]
        MFP_URL, MFP_PASSWORD = mfp_data.split(",")
        MFP_PASSWORD = MFP_PASSWORD[:-2]
        MFP = "1"

    async with AsyncSession(proxies=proxies) as client:
        # Ottieni metadati
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
                elif site_name == "CB01":
                    site_streams = await scrape_cb01(url, search_query, client, use_proxy)
                elif site_name == "Eurostreaming":
                    site_streams = await scrape_eurostreaming(url, search_query, client, use_proxy)
                elif site_name == "Filmez":
                    site_streams = await scrape_filmez(url, search_query, client, use_proxy)
                elif site_name == "Altadefinizione":
                    site_streams = await scrape_altadefinizione(url, search_query, client, use_proxy)
                elif site_name == "Guardaserie":
                    site_streams = await scrape_guardaserie(url, search_query, client, use_proxy)
                elif site_name == "Tantifilm":
                    site_streams = await scrape_tantifilm(url, search_query, client, use_proxy)
                elif site_name == "Animeworld":
                    site_streams = await scrape_animeworld(url, search_query, client, use_proxy)
                elif site_name == "Animeunity":
                    site_streams = await scrape_animeunity(url, search_query, client, use_proxy)
                elif site_name == "Toonitalia":
                    site_streams = await scrape_toonitalia(url, search_query, client, use_proxy)
                elif site_name == "Animesaturn":
                    site_streams = await scrape_animesaturn(url, search_query, client, use_proxy)
                elif site_name == "Filmpertutti":
                    site_streams = await scrape_filmpertutti(url, search_query, client, use_proxy)
                elif site_name == "Streamingwatch":
                    site_streams = await scrape_streamingwatch(url, search_query, client, use_proxy)
                elif site_name == "Ddlstream":
                    site_streams = await scrape_ddlstream(url, search_query, client, use_proxy)
                elif site_name == "Lordchannel":
                    site_streams = await scrape_lordchannel(url, search_query, client, use_proxy)
                elif site_name == "GuardaHD":
                    site_streams = await scrape_guardahd(url, search_query, client, use_proxy)
                elif site_name == "Onlineserietv":
                    site_streams = await scrape_onlineserietv(url, search_query, client, use_proxy)

                for stream in site_streams:
                    behavior_hints = {}
                    if "d000d.com" in stream:
                        behavior_hints = {
                            "notWebReady": True,
                            "proxyHeaders": {"request": {"Referer": "https://d000d.com/"}}
                        }
                    elif "mixdrop" in stream and MFP == "1":
                        stream = proxy_stream_with_mediaflow(stream, "Mixdrop")
                    elif "maxstream" in stream or "stayonline.pro/e/" in stream:
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

# Endpoint per i metadati
@app.get("/{config:path}/meta/{type}/{id}.json")
@limiter.limit("20/second")
async def meta(request: Request, config: str, type: str, id: str):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    async with AsyncSession(proxies=proxies) as client:
        metadata = await get_tmdb_metadata(id, client, type)
        meta = {
            "meta": {
                "id": id,
                "type": type,
                "name": metadata["title"],
                "poster": metadata["poster"],
                "description": metadata["description"],
                "genres": metadata["genres"]
            }
        }
        logger.info(f"Metadati {type}/{id}: {metadata['title']}")
        return respond_with(meta)

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
