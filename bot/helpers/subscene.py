import asyncio
import cloudscraper
from bs4 import BeautifulSoup

def down_page_sync(url):
    scraper = cloudscraper.create_scraper()
    resp = scraper.get(url).text
    soup = BeautifulSoup(resp, "lxml")
    
    try:
        maindiv = soup.body.find("div", class_="subtitle").find("div", class_="top left")
        title = maindiv.find("div", class_="header").h1.span.text.strip()
    except AttributeError:
        return None

    try:
        imdb = maindiv.find("div", class_="header").h1.a["href"]
    except (TypeError, AttributeError):
        imdb = ""
    try:
        poster = maindiv.find("div", class_="poster").a["href"]
    except (AttributeError, TypeError):
        poster = ""
    try:
        author_element = maindiv.find("div", class_="header").ul.find("li", class_="author")
        author_name = author_element.a.text.strip()
        author_link = f"https://subscene.com{author_element.a['href']}"
    except (AttributeError, TypeError):
        author_link = ""
        author_name = "Anonymous"

    try:
        download_div = maindiv.find("div", class_="header").ul.find("li", class_="clearfix").find("div", class_="download")
        download_url = f"https://subscene.com{download_div.a['href']}"
    except (AttributeError, TypeError):
        download_url = ""

    try:
        comments = (
            maindiv.find("div", class_="header")
            .ul.find("li", class_="comment-wrapper")
            .find("div", class_="comment")
            .text.strip()
        )
    except (AttributeError, TypeError):
        comments = ""
        
    try:
        release_li = maindiv.find("div", class_="header").ul.find("li", class_="release")
        release_divs = release_li.find_all("div")
        releases = "\n".join([r.text.strip() for r in release_divs])
    except (AttributeError, TypeError):
        releases = ""

    return {
        "title": title,
        "imdb": imdb,
        "poster": poster,
        "author_name": author_name,
        "author_url": author_link,
        "download_url": download_url,
        "comments": comments,
        "releases": releases,
    }

async def down_page(url):
    return await asyncio.to_thread(down_page_sync, url)

def search_sub_sync(query):
    scraper = cloudscraper.create_scraper()
    param = {"query": query}
    try:
        r = scraper.post("https://subscene.com/subtitles/searchbytitle", data=param).text
        soup = BeautifulSoup(r, "lxml")
        lists = soup.find("div", class_="search-result")
        if not lists:
            return []
        entry = lists.find_all("div", class_="title")
        results = []
        for sub in entry:
            try:
                title = sub.find("a").text.strip()
                link = f"https://subscene.com{sub.find('a').get('href')}"
                results.append({"title": title, "link": link})
            except:
                continue
        return results
    except Exception:
        return []

async def search_sub(query):
    return await asyncio.to_thread(search_sub_sync, query)

def get_sub_options_sync(link):
    scraper = cloudscraper.create_scraper()
    # Filter for English (13), Malay (50), Indonesian (44)
    cookies = {"LanguageFilter": "13,44,50"} 
    try:
        r = scraper.get(link, cookies=cookies).text
        soup = BeautifulSoup(r, "lxml")
        results = []
        for i in soup.findAll(class_="a1"):
            try:
                lang = i.find("a").findAll("span")[0].text.strip()
                title = i.find("a").findAll("span")[1].text.strip()
                
                rate_class = i.find("td", class_="a1").find("span", class_="l r")
                if "neutral-icon" in rate_class.get("class", []):
                    rate = "😐"
                elif "positive-icon" in rate_class.get("class", []):
                    rate = "🥰"
                elif "bad-icon" in rate_class.get("class", []):
                    rate = "☹️"
                else:
                    rate = "❓"
                    
                dllink = f"https://subscene.com{i.find('a').get('href')}"
                results.append({"title": title, "lang": lang, "rate": rate, "link": dllink})
            except:
                continue
        return results
    except:
        return []

async def get_sub_options(link):
    return await asyncio.to_thread(get_sub_options_sync, link)

def download_file_sync(url, filename):
    scraper = cloudscraper.create_scraper()
    r = scraper.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename

async def download_file(url, filename):
    return await asyncio.to_thread(download_file_sync, url, filename)
