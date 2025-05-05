from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
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
app.state.streams = []
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

# Funzione per proxyare stream con MediaFlow
def proxy_stream_with_mediaflow(url):
    return f"{MFP_URL}/proxy?url={urllib.parse.quote(url)}&api_password={MFP_PASSWORD}"

# Funzione per ottenere metadati (mock minimo, pronto per API)
async def get_imdb_metadata(imdb_id, client):
    try:
        # Mock minimo per test, sostituibile con API OMDB/TMDB
        title = "Unknown"
        if imdb_id == "tt8999762":
            title = "Mufasa: The Lion King"
        elif imdb_id == "tt8714904":
            title = "Narcos: Mexico"
        elif imdb_id == "tt20215234":
            title = "Conclave"
        elif imdb_id == "tt13622970":
            title = "Oceania 2"
        elif imdb_id == "tmdb:1241982":
            title = "Unknown TMDB"
        elif imdb_id == "tt7661238":
            title = "Search and Destroy"
        return {
            "title": title,
            "poster": config["General"]["Icon"],
            "description": f"Stream per {title}",
            "genres": ["Streaming"]
        }
    except Exception as e:
        logger.error(f"Errore ottenendo metadati per {imdb_id}: {e}")
        return {
            "title": "Unknown",
            "poster": config["General"]["Icon"],
            "description": "Contenuto non identificato",
            "genres": ["Streaming"]
        }

# Funzioni di scraping
async def scrape_cb01(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_=['film', 'card', 'movie', 'post']):
            title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?query={urllib.parse.quote(search_query)}"
            logger.info(f"Ricerca CB01: {search_url}")
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_=['film', 'card', 'movie', 'post']):
                title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
        logger.info(f"CB01 trovati {len(streams)} stream per {search_query}")
        return streams, titles
    except Exception as e:
        logger.error(f"Errore scraping CB01 {url}: {e}")
        return [], []

async def scrape_streamingcommunity(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_=['card', 'media', 'item']):
            title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?q={urllib.parse.quote(search_query)}"
            logger.info(f"Ricerca StreamingCommunity: {search_url}")
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_=['card', 'media', 'item']):
                title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
        logger.info(f"StreamingCommunity trovati {len(streams)} stream per {search_query}")
        return streams, titles
    except Exception as e:
        logger.error(f"Errore scraping StreamingCommunity {url}: {e}")
        return [], []

async def scrape_animeworld(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_='anime-card'):
            title = item.find('h3').text.strip() if item.find('h3') else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4'))):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?anime={urllib.parse.quote(search_query)}"
            logger.info(f"Ricerca AnimeWorld: {search_url}")
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_='anime-card'):
                title = item.find('h3').text.strip() if item.find('h3') else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4'))):
                    streams.append(link['href'])
                    titles.append(title)
        logger.info(f"AnimeWorld trovati {len(streams)} stream per {search_query}")
        return streams, titles
    except Exception as e:
        logger.error(f"Errore scraping AnimeWorld {url}: {e}")
        return [], []

async def scrape_lordchannel(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all(['article', 'div'], class_=['post', 'movie', 'card']):
            title = item.find(['h2', 'h3', 'h1']).text.strip() if item.find(['h2', 'h3', 'h1']) else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?s={urllib.parse.quote(search_query)}"
            logger.info(f"Ricerca LordChannel: {search_url}")
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all(['article', 'div'], class_=['post', 'movie', 'card']):
                title = item.find(['h2', 'h3', 'h1']).text.strip() if item.find(['h2', 'h3', 'h1']) else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
        logger.info(f"LordChannel trovati {len(streams)} stream per {search_query}")
        return streams, titles
    except Exception as e:
        logger.error(f"Errore scraping LordChannel {url}: {e}")
        return [], []

async def scrape_stayonline(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_=['movie', 'card', 'item']):
            title = item.find(['h1', 'h2', 'h3']).text.strip() if item.find(['h1', 'h2', 'h3']) else "Unknown"
            link = item.find('a', href=True)
            if link and (link['href'].startswith('https://stayonline.pro/e/') or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower()):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"https://stayonline.pro/search?q={urllib.parse.quote(search_query)}"
            logger.info(f"Ricerca StayOnline: {search_url}")
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_=['movie', 'card', 'item']):
                title = item.find(['h1', 'h2', 'h3']).text.strip() if item.find(['h1', 'h2', 'h3']) else "Unknown"
                link = item.find('a', href=True)
                if link and (link['href'].startswith('https://stayonline.pro/e/') or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower()):
                    streams.append(link['href'])
                    titles.append(title)
        logger.info(f"StayOnline trovati {len(streams)} stream per {search_query}")
        return streams, titles
    except Exception as e:
        logger.error(f"Errore scraping StayOnline {url}: {e}")
        return [], []

async def scrape_guardahd(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_=['video-item', 'movie', 'card']):
            title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?q={urllib.parse.quote(search_query)}"
            logger.info(f"Ricerca GuardaHD: {search_url}")
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_=['video-item', 'movie', 'card']):
                title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
        logger.info(f"GuardaHD trovati {len(streams)} stream per {search_query}")
        return streams, titles
    except Exception as e:
        logger.error(f"Errore scraping GuardaHD {url}: {e}")
        return [], []

async def scrape_guardaserie(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_=['serie', 'card', 'item']):
            title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?q={urllib.parse.quote(search_query)}"
            logger.info(f"Ricerca Guardaserie: {search_url}")
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_=['serie', 'card', 'item']):
                title = item.find(['h3', 'h2', 'h1']).text.strip() if item.find(['h3', 'h2', 'h1']) else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'].lower() or link['href'].endswith(('.m3u8', '.mp4')) or "maxstream" in link['href'].lower() or "mixdrop" in link['href'].lower() or "stayonline.pro/e/" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
        logger.info(f"Guardaserie trovati {len(streams)} stream per {search_query}")
        return streams, titles
    except Exception as e:
        logger.error(f"Errore scraping Guardaserie {url}: {e}")
        return [], []

# Manifest
MANIFEST = {
    "id": "com.mariovio01.stremio",
    "version": "1.0.0",
    "name": "Mario's Stremio Addon",
    "description": "Addon con siti predefiniti per film, serie e anime",
    "resources": ["catalog", "stream", "meta"],
    "types": ["movie", "series", "anime"],
    "catalogs": [
        {"type": "movie", "id": "movies"},
        {"type": "series", "id": "series"},
        {"type": "anime", "id": "anime"}
    ],
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
@app.get("/manifest.json")
def manifest():
    return respond_with(MANIFEST)

# Endpoint per il catalogo generico
@app.get("/catalog")
@limiter.limit("5/second")
async def generic_catalog(request: Request, search: str = None):
    config = load_config()
    all_streams = []
    all_titles = []

    async with AsyncSession(proxies=proxies) as client:
        for site_name, site in config["Siti"].items():
            if site["enabled"]:
                url = site["url"]
                use_proxy = site.get(f"{site_name[:2]}_PROXY", 0) == 1
                search_query = search if search else None

                # Limita AnimeWorld e AnimeSaturn a ricerche anime
                if site_name in ["AnimeWorld", "AnimeSaturn"] and search and not any(keyword in search.lower() for keyword in ["anime", "one piece", "fire force"]):
                    continue

                if site_name == "CB01":
                    streams, titles = await scrape_cb01(url, search_query, client, use_proxy)
                elif site_name == "StreamingCommunity":
                    streams, titles = await scrape_streamingcommunity(url, search_query, client, use_proxy)
                elif site_name in ["AnimeWorld", "AnimeSaturn"]:
                    streams, titles = await scrape_animeworld(url, search_query, client, use_proxy)
                elif site_name == "LordChannel":
                    streams, titles = await scrape_lordchannel(url, search_query, client, use_proxy)
                elif site_name == "StayOnline":
                    streams, titles = await scrape_stayonline(url, search_query, client, use_proxy)
                elif site_name == "GuardaHD":
                    streams, titles = await scrape_guardahd(url, search_query, client, use_proxy)
                elif site_name == "Guardaserie":
                    streams, titles = await scrape_guardaserie(url, search_query, client, use_proxy)
                else:
                    continue

                all_streams.extend(streams)
                all_titles.extend(titles)

    catalog = {
        "metas": [
            {
                "id": f"addon_{i}",
                "type": "movie" if "film" in title.lower() else "series" if "serie" in title.lower() else "anime",
                "name": title,
                "poster": config["General"]["Icon"],
                "streams": [{"url": proxy_stream_with_mediaflow(stream)}]
            }
            for i, (stream, title) in enumerate(zip(all_streams, all_titles))
            if stream and title
        ]
    }
    logger.info(f"Catalogo generico: {len(catalog['metas'])} elementi trovati per ricerca '{search}'")
    return respond_with(catalog)

# Endpoint per il catalogo specifico
@app.get("/catalog/{type}/{id}.json")
@limiter.limit("5/second")
async def catalog(request: Request, type: str, id: str, search: str = None):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    config = load_config()
    all_streams = []
    all_titles = []

    async with AsyncSession(proxies=proxies) as client:
        for site_name, site in config["Siti"].items():
            if site["enabled"]:
                url = site["url"]
                use_proxy = site.get(f"{site_name[:2]}_PROXY", 0) == 1
                search_query = search if search else id

                # Limita AnimeWorld e AnimeSaturn a contenuti anime
                if site_name in ["AnimeWorld", "AnimeSaturn"] and type != "anime":
                    continue

                if site_name == "CB01":
                    streams, titles = await scrape_cb01(url, search_query, client, use_proxy)
                elif site_name == "StreamingCommunity":
                    streams, titles = await scrape_streamingcommunity(url, search_query, client, use_proxy)
                elif site_name in ["AnimeWorld", "AnimeSaturn"]:
                    streams, titles = await scrape_animeworld(url, search_query, client, use_proxy)
                elif site_name == "LordChannel":
                    streams, titles = await scrape_lordchannel(url, search_query, client, use_proxy)
                elif site_name == "StayOnline":
                    streams, titles = await scrape_stayonline(url, search_query, client, use_proxy)
                elif site_name == "GuardaHD":
                    streams, titles = await scrape_guardahd(url, search_query, client, use_proxy)
                elif site_name == "Guardaserie":
                    streams, titles = await scrape_guardaserie(url, search_query, client, use_proxy)
                else:
                    continue

                all_streams.extend(streams)
                all_titles.extend(titles)

    catalog = {
        "metas": [
            {
                "id": f"addon_{i}",
                "type": type,
                "name": title,
                "poster": config["General"]["Icon"],
                "streams": [{"url": proxy_stream_with_mediaflow(stream)}]
            }
            for i, (stream, title) in enumerate(zip(all_streams, all_titles))
            if stream and title
        ]
    }
    logger.info(f"Catalogo specifico {type}/{id}: {len(catalog['metas'])} elementi trovati per ricerca '{search}'")
    return respond_with(catalog)

# Endpoint per gli stream
@app.get("/stream/{type}/{id}.json")
@limiter.limit("5/second")
async def stream(request: Request, type: str, id: str):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    config = load_config()
    streams = []

    # Gestione episodi per serie
    search_query = id.replace("addon_", "")
    season = None
    episode = None
    if ":" in search_query and type == "series":
        imdb_id, season, episode = search_query.split(":")
        search_query = imdb_id
    else:
        imdb_id = search_query.replace("tt", "").replace("tmdb:", "")

    async with AsyncSession(proxies=proxies) as client:
        # Ottieni metadati per il titolo
        metadata = await get_imdb_metadata(imdb_id, client)
        title_query = metadata["title"] if metadata else search_query

        # Formatta la query per serie
        search_variants = []
        if season and episode:
            search_variants = [
                f"{title_query} S{season.zfill(2)}E{episode.zfill(2)}",
                f"{title_query} {season}x{episode.zfill(2)}",
                f"{title_query} Stagione {season} Episodio {episode}",
                f"{title_query} Season {season} Episode {episode}",
                title_query
            ]
        else:
            search_variants = [
                title_query,
                title_query.replace(" [HD]", "").replace(" (2024)", "").replace(" (2020)", ""),
                search_query
            ]

        # Varianti specifiche
        if imdb_id == "13622970":
            search_variants.extend(["Moana 2", "Oceania 2 2024"])
        elif imdb_id == "8714904":
            search_variants.extend(["Narcos Mexico", "Narcos Mexico Season 3"])

        for site_name, site in config["Siti"].items():
            if site["enabled"]:
                url = site["url"]
                use_proxy = site.get(f"{site_name[:2]}_PROXY", 0) == 1

                # Limita AnimeWorld e AnimeSaturn a contenuti anime
                if site_name in ["AnimeWorld", "AnimeSaturn"] and type != "anime":
                    continue

                for variant in search_variants:
                    logger.info(f"Ricerca stream su {site_name} per {variant}")

                    if site_name == "CB01":
                        site_streams, _ = await scrape_cb01(url, variant, client, use_proxy)
                    elif site_name == "StreamingCommunity":
                        site_streams, _ = await scrape_streamingcommunity(url, variant, client, use_proxy)
                    elif site_name in ["AnimeWorld", "AnimeSaturn"]:
                        site_streams, _ = await scrape_animeworld(url, variant, client, use_proxy)
                    elif site_name == "LordChannel":
                        site_streams, _ = await scrape_lordchannel(url, variant, client, use_proxy)
                    elif site_name == "StayOnline":
                        site_streams, _ = await scrape_stayonline(url, variant, client, use_proxy)
                    elif site_name == "GuardaHD":
                        site_streams, _ = await scrape_guardahd(url, variant, client, use_proxy)
                    elif site_name == "Guardaserie":
                        site_streams, _ = await scrape_guardaserie(url, variant, client, use_proxy)
                    else:
                        continue

                    streams.extend([
                        {"url": proxy_stream_with_mediaflow(stream), "title": f"{config['General']['Icon']}{site_name}"}
                        for stream in site_streams
                    ])

                    if site_streams:
                        logger.info(f"Trovati {len(site_streams)} stream su {site_name} per {variant}")
                        break

    response = {"streams": streams}
    logger.info(f"Stream {type}/{id}: {len(streams)} stream trovati")
    return respond_with(response)

# Endpoint per i metadati
@app.get("/meta/{type}/{id}.json")
@limiter.limit("20/second")
async def meta(request: Request, type: str, id: str):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    async with AsyncSession(proxies=proxies) as client:
        metadata = await get_imdb_metadata(id, client)
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

# Gestore lifespan per startup
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
