import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from collections import deque
from PIL import Image
from io import BytesIO
import os
import time   

# ---------------- CONFIG ---------------- #
MAX_PAGES = 50
MAX_DEPTH = 2
TIMEOUT = 5
CONCURRENT_REQUESTS = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# ---------------- PAGE SIZE STATUS ---------------- #
def get_size_status(size):
    if size < 300:
        return "Excellent"
    elif size < 800:
        return "Good"
    elif size < 1500:
        return "Heavy"
    else:
        return "Very Heavy"

# ---------------- WORD STATUS (NEW) ---------------- #
def get_word_status(word_count):
    if word_count < 300:
        return "Thin content"
    elif word_count < 600:
        return "Needs improvement"
    elif word_count < 1200:
        return "Good content"
    else:
        return "Excellent content"

# ---------------- HELPERS ---------------- #
def clean_url(url):
    if "#" in url:
        url = url.split("#")[0]  # helps in the duplicate urls
    return url.rstrip("/")  # page/ and page treated as different

def is_internal(url, base_domain):
    return urlparse(url).netloc == base_domain

# ---------------- FETCH ---------------- #
async def fetch(session, url):
    start = time.time()   

    try:
        async with session.get(url, timeout=TIMEOUT) as response:
            load_time = time.time() - start  

            if response.status != 200:
                return None, None, load_time

            html = await response.text()
            content = await response.read()

            return html, content, load_time

    except:
        return None, None, 0
    
    # ---------------- RESOURCE ANALYZER ---------------- #
async def analyze_resource(session, base_url, resource_url):
    full_url = urljoin(base_url, resource_url)

    try:
        start = time.time()
        async with session.get(full_url, timeout=TIMEOUT) as res:
            load_time = time.time() - start

            if res.status != 200:
                return None

            content = await res.read()
            size_kb = len(content) / 1024

            return {
                "url": full_url,
                "size_kb": round(size_kb, 2),
                "load_time": round(load_time, 2)
            }
    except:
        return None


# ---------------- IMAGE ANALYSIS ---------------- #
async def analyze_image(session, base_url, img_tag):
    src = img_tag.get("src")
    if not src:
        return None

    img_url = urljoin(base_url, src)

    try:
        async with session.get(img_url, timeout=TIMEOUT) as res:
            if res.status != 200:
                return None

            content = await res.read()
            size_kb = len(content) / 1024

            width, height = None, None
            try:
                img = Image.open(BytesIO(content))
                width, height = img.size
            except:
                pass

            return {
                "url": img_url,
                "size_kb": round(size_kb, 2),
                "width": width,
                "height": height
            }
    except:
        return None

# ---------------- PAGE ANALYSIS ---------------- #
async def analyze_page(session, url):
    # html, content = await fetch(session, url)
    html, content, page_load_time = await fetch(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style"]):
        tag.decompose()

    # META
    title = soup.title.string.strip() if soup.title else ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ""
    meta_length = len(meta_desc)

    canonical_tag = soup.find("link", rel="canonical")
    canonical = canonical_tag["href"] if canonical_tag else None

    # HEADINGS
    h1 = len(soup.find_all("h1"))
    h2 = len(soup.find_all("h2"))
    h3 = len(soup.find_all("h3"))

   # ---------------- CSS & JS EXTRACTION  ---------------- #
    css_files = [link.get("href") for link in soup.find_all("link", rel="stylesheet") if link.get("href")]
    js_files = [script.get("src") for script in soup.find_all("script") if script.get("src")]

    # IMAGES ANALYSIS
    images = soup.find_all("img")
    missing_alt = len([img for img in images if not img.get("alt")])

    image_tasks = [analyze_image(session, url, img) for img in images[:5]]
    image_results = await asyncio.gather(*image_tasks)

    large_images = 0
    large_image_urls = []
    total_img_size = 0
    resolutions = []

    for img in image_results:
        if not img:
            continue

        total_img_size += img["size_kb"]

        if img["size_kb"] > 200:
            large_images += 1
            # large_image_urls.append(img["url"])
            large_image_urls.append({
                "url":img["url"],
                "size_kb":img["size_kb"]
            })

        if img["width"] and img["height"]:
            filename = os.path.basename(img["url"])

            if img["width"] <= 800:
                msg = "Good"
            elif img["width"] <= 1500:
                msg = "Medium"
            else:
                msg = "Too Large (Resize Recommended)"

            resolutions.append(
                f"{filename} → {img['width']}x{img['height']} ({msg})"
            )

    # ---------------- RESOURCE ANALYSIS ---------------- #
    css_tasks = [analyze_resource(session, url, css) for css in css_files[:5]]
    js_tasks = [analyze_resource(session, url, js) for js in js_files[:5]]

    css_results = await asyncio.gather(*css_tasks)
    js_results = await asyncio.gather(*js_tasks)

    css_results = [r for r in css_results if r]
    js_results = [r for r in js_results if r]

    total_resource_size = sum(r["size_kb"] for r in css_results + js_results)

    performance_summary = {
        "page_load_time": round(page_load_time, 2),
        "total_css": len(css_results),
        "total_js": len(js_results),
        "total_resource_size_kb": round(total_resource_size, 2)
    }
    # TEXT
    text = soup.get_text(separator=" ")
    word_count = len(text.split())

    # WORD STATUS
    word_status = get_word_status(word_count)

    # LINKS
    links = [a.get("href") for a in soup.find_all("a", href=True)]

    internal_links = 0
    external_links = 0
    base_domain = urlparse(url).netloc

    for link in links:
        full = urljoin(url, link)

        if any(x in full for x in ["mailto:", "tel:", "javascript:"]):
            continue

        if urlparse(full).netloc == base_domain:
            internal_links += 1
        else:
            external_links += 1
            page_size_kb = round(len(content) / 1024, 2)

    # BROKEN LINKS
    broken_links = []
    redirect_links = []

    for link in links[:20]:
        full_url = urljoin(url, link)

        if any(x in full_url for x in ["mailto:", "tel:", "javascript:"]):
            continue

        try:
            async with session.get(full_url, timeout=TIMEOUT, allow_redirects=False) as res:
                if res.status == 404:
                    broken_links.append(full_url)
                elif res.status in [301, 302]:
                    redirect_links.append(full_url)
        except:
            broken_links.append(full_url)

    page_size_kb = round(len(content) / 1024, 2)

    return {
        "url": url,
        "title": title,
        "title_length": len(title),
        "meta_description": meta_desc,
        "meta_length": meta_length,
        "canonical": canonical,
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "images": len(images),
        "missing_alt": missing_alt,
        "large_images": large_images,
        "large_image_urls": large_image_urls,
        "size_status": get_size_status(page_size_kb),
        "avg_image_size_kb": round(total_img_size / len(image_results), 2) if image_results else 0,
        "image_resolutions": resolutions[:3],
        "internal_links": internal_links,
        "external_links": external_links,
        "page_size_kb": page_size_kb,
        "word_count": word_count,
        "word_status": word_status,  
        "links": links,
        "broken_links": broken_links,
        "redirect_links": redirect_links,
               # PERFORMANCE DATA
        "page_load_time": round(page_load_time, 2),
        "css_files": css_results,
        "js_files": js_results,
        "performance_summary": performance_summary,
        
    }

# ---------------- ISSUE DETECTION ---------------- #
def detect_issues(page):
    issues = []

    if page["h1"] == 0:
        issues.append("Missing H1")
    elif page["h1"] > 1:
        issues.append("Multiple H1")

    if page["title_length"] == 0:
        issues.append("Missing Title")
    elif page["title_length"] > 60:
        issues.append("Title too long")
    elif page["title_length"] < 30:
        issues.append("Title too short")

    if page["meta_length"] == 0:
        issues.append("Missing meta description")
    elif page["meta_length"] < 50:
        issues.append("Meta too short")
    elif page["meta_length"] > 160:
        issues.append("Meta too long")

    if page["missing_alt"] > 0:
        issues.append("Images missing ALT")

    if page["large_images"] > 0:
        issues.append("Large images found")

    if page["word_count"] < 300:
        issues.append("Thin content")

    if page["page_size_kb"] > 800:
        issues.append("Heavy page")

    return issues

# ---------------- MAIN ANALYZER ---------------- #
async def analyze_seo(start_url):
    if not start_url.startswith("http"):
        start_url = "https://" + start_url

    parsed = urlparse(start_url)
    base_domain = parsed.netloc

    visited = set()
    queue = deque([(start_url, 0)])
    results = []
    titles_seen = {}

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(headers=HEADERS) as session:

        while queue and len(visited) < MAX_PAGES:
            url, depth = queue.popleft()
            url = clean_url(url)

            if url in visited or depth > MAX_DEPTH:
                continue

            visited.add(url)

            async with semaphore:
                page = await analyze_page(session, url)

            if not page:
                continue

            page["issues"] = detect_issues(page)

            if page["title"] in titles_seen:
                page["issues"].append("Duplicate title")
            else:
                titles_seen[page["title"]] = url

            results.append(page)

            for link in page["links"][:20]:
                full_url = clean_url(urljoin(url, link))

                if is_internal(full_url, base_domain) and full_url not in visited:
                    queue.append((full_url, depth + 1))

    all_broken_links = []
    all_redirect_links = []

    for page in results:
        all_broken_links.extend(page.get("broken_links", []))
        all_redirect_links.extend(page.get("redirect_links", []))

    score = 100
    for page in results:
        score -= len(page["issues"]) * 1

    score = max(score, 0)

    return {
        "summary": {
            "pages_crawled": len(results),
            "seo_score": score
        },
        "pages": results,
        "broken_links": list(set(all_broken_links)),
        "redirect_links": list(set(all_redirect_links)),
    }
# ---------------- RUN ---------------- #
if __name__ == "__main__":
    url = input("Enter URL: ")
    result = asyncio.run(analyze_seo(url))

    from pprint import pprint
    pprint(result)