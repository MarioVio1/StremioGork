document.getElementById('addSite').addEventListener('click', () => {
    const siteEntry = document.createElement('div');
    siteEntry.className = 'site-entry';
    siteEntry.innerHTML = `
        <input type="text" class="domain" placeholder="URL del sito (es. https://example.com)" required>
        <select class="types" multiple>
            <option value="movie" selected>Film</option>
            <option value="series" selected>Serie</option>
            <option value="anime">Anime</option>
            <option value="channel">Live TV</option>
        </select>
        <button type="button" class="remove-site">Rimuovi</button>
    `;
    document.getElementById('sitesList').appendChild(siteEntry);
});

document.getElementById('sitesList').addEventListener('click', (e) => {
    if (e.target.classList.contains('remove-site')) {
        e.target.parentElement.remove();
    }
});

document.getElementById('generateManifest').addEventListener('click', async () => {
    const sites = Array.from(document.querySelectorAll('.site-entry')).map(entry => ({
        domain: entry.querySelector('.domain').value,
        types: Array.from(entry.querySelector('.types').selectedOptions).map(option => option.value)
    }));

    try {
        const response = await fetch('/configure', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sites })
        });
        const data = await response.json();
        if (data.addonUrl) {
            document.getElementById('addonUrl').value = data.addonUrl;
            alert('Manifest generato con successo!');
        } else {
            alert('Errore: ' + data.error);
        }
    } catch (error) {
        alert('Errore nella configurazione: ' + error.message);
    }
});

function copyUrl() {
    const urlInput = document.getElementById('addonUrl');
    urlInput.select();
    document.execCommand('copy');
    alert('URL copiato negli appunti!');
}

function installAddon() {
    const url = document.getElementById('addonUrl').value;
    if (url) window.open(`stremio://install/${url}`, '_blank');
    else alert('Genera prima il manifest!');
}
