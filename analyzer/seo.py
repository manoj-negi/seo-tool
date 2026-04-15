import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import time

MAX_PAGES = 10 # limit crawling

def get_page_data(url, headers):
   

    try:
        start = time.time()
        response = requests.get(url, headers=headers, timeout=10)
        load_time = time.time() - start

        soup = BeautifulSoup(response.text, "lxml")

        title = soup.title.string.strip() if soup.title else ""
        meta = soup.find("meta", attrs={"name": "description"})
        meta_desc = meta["content"] if meta else ""

        h1 = len(soup.find_all("h1"))
        h2 = len(soup.find_all("h2"))
        h3 = len(soup.find_all("h3"))

        images = soup.find_all("img")
        missing_alt = len([img for img in images if not img.get("alt")])

        text = soup.get_text()
        word_count = len(text.split())

        links = soup.find_all("a", href=True)

        return {
            "title": title,
            "title_length": len(title),
            "meta_description": meta_desc,
            "h1": h1,
            "h2": h2,
            "h3": h3,
            "images": len(images),
            "missing_alt": missing_alt,
            "word_count": word_count,
            "load_time": load_time,
            "links": links
        }

    except:
        return None


def analyze_seo(url):
    try:
        if not url.startswith("http"):
            url = "https://" + url

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        parsed = urlparse(url)
        base_domain = parsed.netloc
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        visited = set()
        to_visit = [url]

        # --- aggregated data ---
        total_title_length = 0
        total_meta = ""
        total_h1 = total_h2 = total_h3 = 0
        total_images = total_missing_alt = 0
        total_words = 0
        total_load_time = 0

        internal_links = 0
        external_links = 0

        pages_crawled = 0

        # --- CRAWLING LOOP ---
        while to_visit and pages_crawled < MAX_PAGES:
            current_url = to_visit.pop(0)

            if current_url in visited:
                continue

            visited.add(current_url)

            page_data = get_page_data(current_url, headers)

            if not page_data:
                continue

            pages_crawled += 1

            # --- aggregate ---
            total_title_length += page_data["title_length"]
            total_meta = page_data["meta_description"] or total_meta
            total_h1 += page_data["h1"]
            total_h2 += page_data["h2"]
            total_h3 += page_data["h3"]
            total_images += page_data["images"]
            total_missing_alt += page_data["missing_alt"]
            total_words += page_data["word_count"]
            total_load_time += page_data["load_time"]

            # --- process links ---
            for link in page_data["links"]:
                href = link.get("href")
                full_url = urljoin(current_url, href)
                parsed_link = urlparse(full_url)

                if parsed_link.netloc == base_domain:
                    internal_links += 1
                    if full_url not in visited and len(to_visit) < MAX_PAGES:
                        to_visit.append(full_url)
                else:
                    external_links += 1

        # --- average load time ---
        avg_load_time = round(total_load_time / pages_crawled, 2) if pages_crawled else 0

        # --- SITEMAP ---
        sitemap_found = False
        sitemap_url = ""
        total_urls = 0

        for path in ["/sitemap.xml", "/sitemap_index.xml"]:
            try:
                test_url = base_url + path
                res = requests.get(test_url, headers=headers, timeout=10)

                if res.status_code == 200:
                    soup = BeautifulSoup(res.content, "xml")

                    urls = soup.find_all("loc")
                    sitemaps = soup.find_all("sitemap")

                    if sitemaps:
                        for sm in sitemaps:
                            loc = sm.find("loc").text
                            sub = requests.get(loc, headers=headers, timeout=10)
                            sub_soup = BeautifulSoup(sub.content, "xml")
                            total_urls += len(sub_soup.find_all("loc"))
                    else:
                        total_urls = len(urls)

                    sitemap_found = True
                    sitemap_url = test_url
                    break
            except:
                continue

        # --- RETURN ---
        return {
            "title": "Multiple Pages Analyzed",
            "title_length": total_title_length,
            "meta_description": total_meta,
            "h1_count": total_h1,
            "h2_count": total_h2,
            "h3_count": total_h3,
            "total_images": total_images,
            "images_missing_alt": total_missing_alt,
            "internal_links": internal_links,
            "external_links": external_links,
            "word_count": total_words,
            "load_time": avg_load_time,
            "sitemap_found": sitemap_found,
            "sitemap_url": sitemap_url,
            "sitemap_total_urls": total_urls,
        }

    except Exception as e:
        return {"error": str(e)}