from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
from curl_cffi.requests import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

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

# Funzione per proxyare con MediaFlow
async def proxy_with_mediaflow(url, client):
    proxy_url = f"{MFP_URL}/proxy?url={urllib.parse.quote(url)}"
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {MFP_PASSWORD}"
    try:
        response = await client.get(proxy_url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Errore con MediaFlow Proxy per {url}: {e}")
        return None

# Funzioni di scraping per siti specifici
async def scrape_cb01(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_='film'):
            title = item.find('h3').text if item.find('h3') else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'] or link['href'].endswith(('.m3u8', '.mp4'))):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?query={urllib.parse.quote(search_query)}"
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_='film'):
                title = item.find('h3').text if item.find('h3') else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'] or link['href'].endswith(('.m3u8', '.mp4'))):
                    streams.append(link['href'])
                    titles.append(title)
        return streams, titles
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return [], []

async def scrape_animeworld(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('div', class_='anime-card'):
            title = item.find('h3').text if item.find('h3') else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'] or link['href'].endswith(('.m3u8', '.mp4'))):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?anime={urllib.parse.quote(search_query)}"
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('div', class_='anime-card'):
                title = item.find('h3').text if item.find('h3') else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'] or link['href'].endswith(('.m3u8', '.mp4'))):
                    streams.append(link['href'])
                    titles.append(title)
        return streams, titles
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return [], []

async def scrape_lordchannel(url, search_query=None, client=None, use_proxy=False):
    try:
        response = await client.get(url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []
        for item in soup.find_all('article'):
            title = item.find('h2').text if item.find('h2') else "Unknown"
            link = item.find('a', href=True)
            if link and ("streaming" in link['href'] or link['href'].endswith(('.m3u8', '.mp4'))):
                streams.append(link['href'])
                titles.append(title)
        if search_query:
            search_url = f"{url}/search?s={urllib.parse.quote(search_query)}"
            search_response = await client.get(search_url, headers=HEADERS, proxies=proxies if use_proxy else {}, timeout=15, verify=False)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for item in search_soup.find_all('article'):
                title = item.find('h2').text if item.find('h2') else "Unknown"
                link = item.find('a', href=True)
                if link and ("streaming" in link['href'] or link['href'].endswith(('.m3u8', '.mp4'))):
                    streams.append(link['href'])
                    titles.append(title)
        return streams, titles
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return [], []

# Altri siti (es. Guardaserie, StreamingWatch) seguono una logica simile

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

# Endpoint per il catalogo
@app.get("/catalog/{type}/{id}.json")
@limiter.limit("5/second")
async def catalog(type: str, id: str, search: str = None):
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
                use_mediaflow = site.get("use_mediaflow", 0) == 1

                if use_mediaflow:
                    proxied_content = await proxy_with_mediaflow(url, client)
                    if proxied_content:
                        soup = BeautifulSoup(proxied_content, 'html.parser')
                        streams = []
                        titles = []
                        for link in soup.find_all('a', href=True):
                            if link['href'].endswith(('.m3u8', '.mp4')):
                                proxied_stream = f"{MFP_URL}/proxy?url={urllib.parse.quote(link['href'])}"
                                streams.append(proxied_stream)
                                titles.append(link.get('title', 'Unknown'))
                        if search:
                            search_url = f"{url}/search?q={urllib.parse.quote(search)}"
                            proxied_search_content = await proxy_with_mediaflow(search_url, client)
                            if proxied_search_content:
                                search_soup = BeautifulSoup(proxied_search_content, 'html.parser')
                                for link in search_soup.find_all('a', href=True):
                                    if link['href'].endswith(('.m3u8', '.mp4')):
                                        proxied_stream = f"{MFP_URL}/proxy?url={urllib.parse.quote(link['href'])}"
                                        streams.append(proxied_stream)
                                        titles.append(link.get('title', 'Unknown'))
                        all_streams.extend(streams)
                        all_titles.extend(titles)
                    else:
                        # Fallback a scraping diretto
                        if site_name == "CB01":
                            streams, titles = await scrape_cb01(url, search, client, use_proxy)
                        elif site_name in ["AnimeWorld", "AnimeSaturn"]:
                            streams, titles = await scrape_animeworld(url, search, client, use_proxy)
                        elif site_name == "LordChannel":
                            streams, titles = await scrape_lordchannel(url, search, client, use_proxy)
                        else:
                            continue
                        all_streams.extend(streams)
                        all_titles.extend(titles)
                else:
                    if site_name == "CB01":
                        streams, titles = await scrape_cb01(url, search, client, use_proxy)
                    elif site_name in ["AnimeWorld", "AnimeSaturn"]:
                        streams, titles = await scrape_animeworld(url, search, client, use_proxy)
                    elif site_name == "LordChannel":
                        streams, titles = await scrape_lordchannel(url, search, client, use_proxy)
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
                "streams": [{"url": stream}]
            }
            for i, (stream, title) in enumerate(zip(all_streams, all_titles))
            if stream and title
        ]
    }
    return respond_with(catalog)

# Endpoint per gli stream
@app.get("/stream/{type}/{id}.json")
@limiter.limit("5/second")
async def stream(type: str, id: str):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    config = load_config()
    streams = []

    async with AsyncSession(proxies=proxies) as client:
        for site_name, site in config["Siti"].items():
            if site["enabled"]:
                url = site["url"]
                use_proxy = site.get(f"{site_name[:2]}_PROXY", 0) == 1
                use_mediaflow = site.get("use_mediaflow", 0) == 1
                search_query = id.replace("addon_", "")

                if site_name == "CB01":
                    site_streams, _ = await scrape_cb01(url, search_query, client, use_proxy)
                elif site_name in ["AnimeWorld", "AnimeSaturn"]:
                    site_streams, _ = await scrape_animeworld(url, search_query, client, use_proxy)
                elif site_name == "LordChannel":
                    site_streams, _ = await scrape_lordchannel(url, search_query, client, use_proxy)
                else:
                    continue

                if use_mediaflow:
                    streams.extend([
                        {"url": f"{MFP_URL}/proxy?url={urllib.parse.quote(stream)}", "title": f"{config['General']['Icon']}{site_name}"}
                        for stream in site_streams
                    ])
                else:
                    streams.extend([
                        {"url": stream, "title": f"{config['General']['Icon']}{site_name}"}
                        for stream in site_streams
                    ])

    return respond_with({"streams": streams})

# Endpoint per i metadati
@app.get("/meta/{type}/{id}.json")
@limiter.limit("20/second")
async def meta(type: str, id: str):
    if type not in MANIFEST["types"]:
        raise HTTPException(status_code=404)
    config = load_config()
    title = id.replace("addon_", "")
    meta = {
        "meta": {
            "id": id,
            "type": type,
            "name": title,
            "poster": config["General"]["Icon"],
            "description": f"Stream per {title}",
            "genres": ["Streaming"]
        }
    }
    return respond_with(meta)

# Caricamento all'avvio
@app.on_event("startup")
async def startup_event():
    config = load_config()
    print(f"Caricati {len(config['Siti'])} siti dal config")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
