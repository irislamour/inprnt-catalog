"""Run in a GitHub repository; output catalog.csv. Public pages only."""
import csv
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE = 'https://www.inprnt.com'
GALLERY = BASE + '/gallery/flowercannibal/'
COLLECTIONS = {
    'Brobert Comics': '/collections/flowercannibal/brobert-comics/',
    'Brobert Paintings': '/collections/flowercannibal/brobert-paintings/',
    'Floofle Comics': '/collections/flowercannibal/floofle-comics/',
    'Floofle Paintings': '/collections/flowercannibal/floofle-paintings/',
    'SWS': '/collections/flowercannibal/sws/',
}
session = requests.Session()
session.headers['User-Agent'] = 'FlowerCannibal owned-artwork catalog sync'

def pages(url):
    visited = set()
    while url:
        if url in visited or len(visited) >= 100:
            raise RuntimeError('Pagination loop or limit: ' + url)
        if urlparse(url).netloc != 'www.inprnt.com':
            raise RuntimeError('Unexpected pagination host')
        visited.add(url)
        response = session.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        if not soup.select('.product-thumb'):
            raise RuntimeError('No artwork cards; refusing to replace catalog: ' + url)
        yield soup
        more = soup.select_one('a.endless_more[href]')
        url = urljoin(BASE, more['href']) if more else None
        time.sleep(1)

def product_link(href):
    url = urljoin(BASE, href)
    path = urlparse(url).path
    prefix = '/gallery/flowercannibal/'
    if not path.startswith(prefix) or len(path[len(prefix):].strip('/').split('/')) != 1 or not path[len(prefix):].strip('/'):
        return None
    return BASE + path.rstrip('/') + '/'

def gallery():
    result = {}
    for soup in pages(GALLERY):
        for card in soup.select('.product-thumb'):
            anchor = card.select_one('a.product_image[href]')
            image = anchor.find('img') if anchor else None
            heading = card.find('h5')
            if not anchor or not image or not heading:
                raise RuntimeError('Artwork markup changed')
            link = product_link(anchor['href'])
            if not link:
                raise RuntimeError('Unexpected artwork URL')
            title = heading.get_text(' ', strip=True)
            source = image.get('src', '')
            for candidate in image.get('srcset', '').split(','):
                parts = candidate.strip().split()
                if len(parts) == 2 and parts[1] == '2x':
                    source = parts[0]
                    break
            source = urljoin(BASE, source)
            if not title or urlparse(source).netloc != 'cdn.inprnt.com':
                raise RuntimeError('Missing title or unexpected image host')
            result[link] = [title, source, link]
    return result

items = gallery()
output = Path('catalog.csv')
previous_count = 0
if output.exists():
    with output.open(encoding='utf-8-sig', newline='') as handle:
        previous_count = sum(1 for _ in csv.DictReader(handle))
# Halt on any shrinkage for review, rather than publishing a partial scrape.
if len(items) < max(150, previous_count):
    raise RuntimeError(f'Catalog shrank to {len(items)}; previous {previous_count}. Review before publishing.')

memberships = {link: [] for link in items}
for name, path in COLLECTIONS.items():
    members = set()
    for soup in pages(BASE + path):
        for card in soup.select('.product-thumb'):
            for anchor in card.select('a[href]'):
                link = product_link(anchor['href'])
                if link:
                    members.add(link)
    if not members:
        raise RuntimeError('Empty collection; review before publishing: ' + name)
    unknown = members.difference(items)
    if unknown:
        raise RuntimeError('Collection artwork missing from gallery; retry later')
    for link in members:
        memberships[link].append(name)

candidate = Path('catalog.csv.tmp')
with candidate.open('w', encoding='utf-8', newline='') as handle:
    writer = csv.writer(handle)
    writer.writerow(['Title', 'Image URL', 'INPRNT URL', 'Collections'])
    for link, row in items.items():
        writer.writerow(row + ['|'.join(memberships[link])])
os.replace(candidate, output)
print(f'Published candidate catalog: {len(items)} artworks, {len(COLLECTIONS)} collections')
