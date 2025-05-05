from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import requests
from bs4 import BeautifulSoup
import json
from requests.auth import HTTPProxyAuth

app = FastAPI()
app.state.streams = []

# Carica config.json
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

# Funzione di scraping personalizzata per ogni sito
def scrape_site(site_config, search_query=None):
    url = site_config["domain"]
    proxy_type = site_config["proxy"]
    use_mediaflow = site_config["use_mediaflow"]
    config = load_config()
    proxies = {}
    headers = {'User-Agent': 'Mozilla/5.0'}

    # Configura il proxy in base al tipo
    if proxy_type == "webshare":
        proxies = {"http": config["Proxy_Settings"]["webshare"], "https": config["Proxy_Settings"]["webshare"]}
    elif proxy_type == "mediaflow" and use_mediaflow:
        mediaflow_url = config["Proxy_Settings"]["mediaflow"]
        mediaflow_password = config["Proxy_Settings"]["mediaflow_password"]
        proxy_url = f"{mediaflow_url}/proxy?url={requests.utils.quote(url)}"
        headers["Authorization"] = f"Bearer {mediaflow_password}"

    try:
        # Esegui la richiesta con il proxy appropriato
        if use_mediaflow and proxy_type == "mediaflow":
            response = requests.get(proxy_url, headers=headers, timeout=10)
        elif proxies:
            response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Logica di scraping personalizzata (adatta per ogni sito)
        streams = []
        if "streamingcommunity.spa" in url:
            for link in soup.find_all('a', href=True):
                if link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])
            if search_query:
                search_form = soup.find('form', {'action': True})
                if search_form:
                    search_url = url + "/search?q=" + search_query
                    search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
                    search_soup = BeautifulSoup(search_response.text, 'html.parser')
                    for link in search_soup.find_all('a', href=True):
                        if link['href'].endswith(('.m3u8', '.mp4')):
                            streams.append(link['href'])

        elif "cb01.meme" in url or "cb01net.uno" in url:
            for link in soup.find_all('a', class_='film-link'):
                if link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])
            if search_query:
                search_url = f"{url}/search?query={search_query}"
                search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                for link in search_soup.find_all('a', class_='film-link'):
                    if link['href'].endswith(('.m3u8', '.mp4')):
                        streams.append(link['href'])

        elif "eurostreaming.my" in url or "eurostreaming.esq" in url:
            for link in soup.find_all('a', class_='streaming-link'):
                if link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])
            if search_query:
                search_url = f"{url}/search?q={search_query}"
                search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                for link in search_soup.find_all('a', class_='streaming-link'):
                    if link['href'].endswith(('.m3u8', '.mp4')):
                        streams.append(link['href'])

        elif "filmez.org" in url:
            for link in soup.find_all('a', href=True):
                if "video" in link['href'] and link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])

        elif "altadefinizionegratis.sbs" in url:
            for link in soup.find_all('a', class_='hd-link'):
                if link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])
            if search_query:
                search_url = f"{url}/search?film={search_query}"
                search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                for link in search_soup.find_all('a', class_='hd-link'):
                    if link['href'].endswith(('.m3u8', '.mp4')):
                        streams.append(link['href'])

        elif "guardaserietv.top" in url:
            for link in soup.find_all('a', class_='serie-link'):
                if link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])

        elif "tanti.bond" in url:
            for link in soup.find_all('a', href=True):
                if "stream" in link['href'] and link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])

        elif "animeworld.ac" in url or "animeunity.so" in url or "toonitalia.green" in url or "animesaturn.cx" in url:
            for link in soup.find_all('a', class_='anime-link'):
                if link['href'].endswith(('.m3u8', '.mp4')):
                    streams.append(link['href'])
            if search_query:
                search_url = f"{url}/search?anime={search_query}"
                search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                for link in search_soup.find_all('a', class_='anime-link'):
                    if link['href'].endswith(('.m3u8', '.mp4')):
                        streams.append(link['href'])

        elif "ilcorsaronero.link" in url or "1337x.to" in url or "rargb.to" in url:
            # Questi sono siti di torrent, quindi non cercano stream diretti
            pass

        return streams
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return []

# Endpoint per la homepage
@app.get("/", response_class=FileResponse)
async def homepage():
    return FileResponse("static/index.html")

# Endpoint per il catalogo Stremio
@app.get("/catalog")
async def catalog(search: str = None):
    config = load_config()
    streams = []

    # Scraping per ogni sito abilitato
    for site in config["domains"]:
        if site["enabled"]:
            site_streams = scrape_site(site, search)
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
    uvicorn.run(app, host="0.0.0.0", port=8080)
