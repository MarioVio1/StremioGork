from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import requests
from bs4 import BeautifulSoup
import json
import urllib.parse

app = FastAPI()
app.state.streams = []

# Carica config.json
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

# Funzione per proxyare con MediaFlow
def proxy_with_mediaflow(url, config):
    mediaflow_url = config["Proxy_Settings"]["mediaflow"]
    mediaflow_password = config["Proxy_Settings"]["mediaflow_password"]
    proxy_url = f"{mediaflow_url}/proxy?url={urllib.parse.quote(url)}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
               'Authorization': f"Bearer {mediaflow_password}"}
    try:
        response = requests.get(proxy_url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Errore con MediaFlow Proxy per {url}: {e}")
        return None

# Funzione di scraping personalizzata
def scrape_site(site_config, search_query=None):
    url = site_config["domain"]
    use_webshare = site_config.get("use_webshare", False)
    config = load_config()
    proxies = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/'
    }

    if use_webshare:
        proxies = {"http": config["Proxy_Settings"]["webshare"], "https": config["Proxy_Settings"]["webshare"]}

    try:
        # Esegui richiesta diretta o con Webshare Proxy
        response = requests.get(url, headers=headers, proxies=proxies, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        titles = []

        # Logica di scraping basata sui documenti
        if "cb01.meme" in url or "cb01net.uno" in url:
            for item in soup.find_all('div', class_='film'):
                title = item.find('h3').text if item.find('h3') else "Unknown"
                link = item.find('a', href=True)
                if link and (link['href'].endswith(('.m3u8', '.mp4')) or "streaming" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
            if search_query:
                search_url = f"{url}/search?query={urllib.parse.quote(search_query)}"
                search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=15, verify=False)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                for item in search_soup.find_all('div', class_='film'):
                    title = item.find('h3').text if item.find('h3') else "Unknown"
                    link = item.find('a', href=True)
                    if link and (link['href'].endswith(('.m3u8', '.mp4')) or "streaming" in link['href']):
                        streams.append(link['href'])
                        titles.append(title)

        elif "altadefinizionegratis.sbs" in url:
            for item in soup.find_all('div', class_='movie-item'):
                title = item.find('h2').text if item.find('h2') else "Unknown"
                link = item.find('a', href=True)
                if link and (link['href'].endswith(('.m3u8', '.mp4')) or "streaming" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
            if search_query:
                search_url = f"{url}/search?film={urllib.parse.quote(search_query)}"
                search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=15, verify=False)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                for item in search_soup.find_all('div', class_='movie-item'):
                    title = item.find('h2').text if item.find('h2') else "Unknown"
                    link = item.find('a', href=True)
                    if link and (link['href'].endswith(('.m3u8', '.mp4')) or "streaming" in link['href']):
                        streams.append(link['href'])
                        titles.append(title)

        elif "animeworld.ac" in url or "animesaturn.cx" in url:
            for item in soup.find_all('div', class_='anime-card'):
                title = item.find('h3').text if item.find('h3') else "Unknown"
                link = item.find('a', href=True)
                if link and (link['href'].endswith(('.m3u8', '.mp4')) or "streaming" in link['href']):
                    streams.append(link['href'])
                    titles.append(title)
            if search_query:
                search_url = f"{url}/search?anime={urllib.parse.quote(search_query)}"
                search_response = requests.get(search_url, headers=headers, proxies=proxies, timeout=15, verify=False)
                search_soup = BeautifulSoup(search_response.text, 'html.parser')
                for item in search_soup.find_all('div', class_='anime-card'):
                    title = item.find('h3').text if item.find('h3') else "Unknown"
                    link = item.find('a', href=True)
                    if link and (link['href'].endswith(('.m3u8', '.mp4')) or "streaming" in link['href']):
                        streams.append(link['href'])
                        titles.append(title)

        return streams, titles
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return [], []

# Endpoint per la homepage
@app.get("/", response_class=FileResponse)
async def homepage():
    return FileResponse("static/index.html")

# Endpoint per il catalogo Stremio
@app.get("/catalog")
async def catalog(search: str = None):
    config = load_config()
    all_streams = []
    all_titles = []

    for site in config["domains"]:
        if site["enabled"]:
            url = site["domain"]
            if site["proxy_for_manifest"]:
                # Usa MediaFlow Proxy
                proxied_content = proxy_with_mediaflow(url, config)
                if proxied_content:
                    soup = BeautifulSoup(proxied_content, 'html.parser')
                    streams = []
                    titles = []
                    # Estrai stream e titoli
                    for link in soup.find_all('a', href=True):
                        if link['href'].endswith(('.m3u8', '.mp4')):
                            # Proxya lo stream con MediaFlow
                            proxied_stream = f"{config['Proxy_Settings']['mediaflow']}/proxy?url={urllib.parse.quote(link['href'])}"
                            streams.append(proxied_stream)
                            titles.append(link.get('title', 'Unknown'))
                    if search:
                        search_url = f"{url}/search?q={urllib.parse.quote(search)}"
                        proxied_search_content = proxy_with_mediaflow(search_url, config)
                        if proxied_search_content:
                            search_soup = BeautifulSoup(proxied_search_content, 'html.parser')
                            for link in search_soup.find_all('a', href=True):
                                if link['href'].endswith(('.m3u8', '.mp4')):
                                    proxied_stream = f"{config['Proxy_Settings']['mediaflow']}/proxy?url={urllib.parse.quote(link['href'])}"
                                    streams.append(proxied_stream)
                                    titles.append(link.get('title', 'Unknown'))
                    all_streams.extend(streams)
                    all_titles.extend(titles)
                else:
                    # Fallback a scraping diretto
                    streams, titles = scrape_site(site, search)
                    all_streams.extend(streams)
                    all_titles.extend(titles)
            else:
                # Scraping diretto
                streams, titles = scrape_site(site, search)
                all_streams.extend(streams)
                all_titles.extend(titles)

    # Formato JSON per Stremio
    catalog = {
        "manifest": {
            "id": "com.mariovio01.stremio",
            "version": "1.0.0",
            "name": "Mario's Stremio Addon",
            "description": "Addon con siti predefiniti",
            "resources": ["catalog", "stream"],
            "types": ["movie", "series", "anime"],
            "catalogs": [
                {"type": "movie", "id": "movies"},
                {"type": "series", "id": "series"},
                {"type": "anime", "id": "anime"}
            ]
        },
        "metas": [
            {
                "id": f"addon_{i}",
                "type": "movie" if "film" in title.lower() else "series" if "serie" in title.lower() else "anime",
                "name": title,
                "poster": config["Icon"],
                "streams": [{"url": stream}]
            }
            for i, (stream, title) in enumerate(zip(all_streams, all_titles))
            if stream and title
        ]
    }
    return JSONResponse(content=catalog)

# Endpoint per gli stream
@app.get("/stream/{type}/{id}")
async def stream(type: str, id: str):
    config = load_config()
    streams = []
    for site in config["domains"]:
        if site["enabled"]:
            site_streams, _ = scrape_site(site, id.replace("addon_", ""))
            if site["proxy_for_manifest"]:
                streams.extend([
                    {"url": f"{config['Proxy_Settings']['mediaflow']}/proxy?url={urllib.parse.quote(stream)}"}
                    for stream in site_streams
                ])
            else:
                streams.extend([{"url": stream} for stream in site_streams])
    return JSONResponse(content={"streams": streams})

# Caricamento all'avvio
@app.on_event("startup")
async def startup_event():
    config = load_config()
    print(f"Caricati {len(config['domains'])} siti dal config")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
