import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'KomoroEventBot/1.0 (Aggregating public event info; +https://github.com/keitata/komoro-api)',
    'Accept-Language': 'ja,en;q=0.9',
}

resp = requests.get('https://www.komoro-tour.jp/blog/category/event/', headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')

articles = soup.find_all('article')
for i, article in enumerate(articles[:3]):
    print(f'\n=== article {i+1} ===')
    print(article.prettify()[:800])