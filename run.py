from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import requests
from bs4 import BeautifulSoup
import json

app = FastAPI()
app.state.streams = []

# Carica config.json
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

# Funzione di scraping semplificata (solo base, senza proxy)
def scrape_site(url, search_query=None):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        for link in soup.find_all('a', href=True):
            if link['href'].endswith(('.m3u8', '.mp4')):
                streams.append(link['href'])
        if search_query:
            search_url = f"{url}/search?q={search_query}"
            search_response = requests.get(search_url, headers=headers, timeout=10)
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            for link in search_soup.find_all('a', href=True):
                if link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])
        return streams
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return []

# Funzione per proxyare con MediaFlow
def proxy_with_mediaflow(url, config):
    mediaflow_url = config["Proxy_Settings"]["mediaflow"]
    mediaflow_password = config["Proxy_Settings"]["mediaflow_password"]
    proxy_url = f"{mediaflow_url}/proxy?url={requests.utils.quote(url)}"
    headers = {'User-Agent': 'Mozilla/5.0', 'Authorization': f"Bearer {mediaflow_password}"}
    try:
        response = requests.get(proxy_url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Errore con MediaFlow Proxy per {url}: {e}")
        return None

# Endpoint per la homepage
@app.get("/", response_class=FileResponse)
async def homepage():
    return FileResponse("static/index.html")

# Endpoint per il catalogo Stremio
@app.get("/catalog")
async def catalog(search: str = None):
    config = load_config()
    streams = []

    for site in config["domains"]:
        if site["enabled"]:
            url = site["domain"]
            if site["proxy_for_manifest"]:
                # Usa MediaFlow Proxy per ottenere il contenuto
                proxied_content = proxy_with_mediaflow(url, config)
                if proxied_content:
                    soup = BeautifulSoup(proxied_content, 'html.parser')
                    for link in soup.find_all('a', href=True):
                        if link['href'].endswith(('.m3u8', '.mp4')):
                            streams.append(link['href'])
                    if search:
                        search_url = f"{url}/search?q={search}"
                        proxied_search_content = proxy_with_mediaflow(search_url, config)
                        if proxied_search_content:
                            search_soup = BeautifulSoup(proxied_search_content, 'html.parser')
                            for link in search_soup.find_all('a', href=True):
                                if link['href'].endswith(('.m3u8', '.mp4')):
                                    streams.append(link['href'])
                else:
                    # Fallback senza proxy se MediaFlow fallisce
                    site_streams = scrape_site(url, search)
                    streams.extend(site_streams)
            else:
                # Nessun proxy, scraping diretto
                site_streams = scrape_site(url, search)
                streams.extend(site_streams)

    # Formato JSON per Stremio
    catalog = {
        "manifest": {
            "id": "com.mariovio01.stremio",
            "version": "1.0.0",
            "name": "Mario's Stremio Addon",
            "description": "Addon con siti predefiniti",
            "resources": ["catalog"],
            "types": ["movie", "series", "anime"],
            "catalogs": []
        },
        "metas": [
            {
                "id": f"addon_{i}",
                "type": "movie" if i % 3 == 0 else "series" if i % 3 == 1 else "anime",
                "name": f"Stream {i}",
                "streams": [{"url": stream}] if stream else []
            }
            for i, stream in enumerate(streams)
        ]
    }
    return JSONResponse(content=catalog)

# Caricamento all'avvio
@app.on_event("startup")
async def startup_event():
    config = load_config()
    print(f"Caricati {len(config['domains'])} siti dal config")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
