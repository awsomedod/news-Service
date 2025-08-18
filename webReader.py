import requests
from bs4 import BeautifulSoup # To get text from Readability's HTML output
from readability import Document # From readability-lxml
from urllib.parse import urlparse # For completeness if URL needed by Document constructor
from flask import Flask, request, jsonify

app = Flask(__name__)

# No direct equivalent for SkipCssResourceLoader, as requests doesn't fetch CSS by default
# when just getting response.text. Readability-lxml also doesn't process external CSS.

def fetch_webpage_python(url: str) -> tuple[str | None, list[str], list[str]]:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
        }
        
        # Synchronous version with requests:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)

        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type.lower():
            # Using ValueError or a custom exception is common
            raise ValueError(f"Expected HTML content but received {content_type} from {url}")

        html = response.text

        # readability-lxml takes the HTML string and optionally the URL
        # The URL helps it resolve relative links if it were to keep them,
        # but for textContent, it's less critical.
        doc = Document(html, url=url) 

        # To get plain text content, you parse the summary HTML (article_html)
        # However, readability-lxml's Document object itself has a way to get text,
        # but it might not be as clean as Readability.js's article.textContent directly.
        # A common approach is to parse the summary:
        article_html_summary = html
        if not article_html_summary:
            print(f"Could not parse article from {url} (summary was empty)")
            return None, [], []

        # Use BeautifulSoup to extract text from the cleaned HTML
        soup = BeautifulSoup(article_html_summary, 'html.parser')
        
        # Process links and images in place before extracting text
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Convert relative URLs to absolute URLs
            if href.startswith('/'):
                from urllib.parse import urljoin
                href = urljoin(url, href)
            # Replace the link with its text + URL in brackets
            link_text = link.get_text(strip=True)
            if link_text:
                link.replace_with(f"{link_text} [{href}]")
            else:
                link.replace_with(f"[{href}]")
        
        for img in soup.find_all('img', src=True):
            src = img['src']
            # Convert relative URLs to absolute URLs
            if src.startswith('/'):
                from urllib.parse import urljoin
                src = urljoin(url, src)
            # Replace the image with its alt text + URL in brackets, or just URL if no alt text
            alt_text = img.get('alt', '').strip()
            if alt_text:
                img.replace_with(f"[Image: {alt_text}] [{src}]")
            else:
                img.replace_with(f"[Image] [{src}]")
        
        # Now extract text content with links and images included
        article_text_content = soup.get_text(separator=' ', strip=True)

        if not article_text_content.strip():
            print(f"Could not extract text content from article from {url}")
            return None
            
        return article_text_content

    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        # In a real app, re-raise or handle more gracefully
        return "Can't fetch page", [], []
    except ValueError as e: # Catch our custom content type error
        print(f"Error processing {url}: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred processing {url}: {e}")
        # In a real app, re-raise or handle more gracefully
        raise ValueError(f"An unknown error occurred while processing {url}: {e}") from e

def estimateTokenCount(text: str):
    # Method 1: Character-based estimation (1 token ≈ 4 characters)
    charBasedEstimate = len(text) / 4

    # Method 2: Word-based estimation (1 token ≈ 0.75 words)
    wordCount = len(text.split())
    wordBasedEstimate = wordCount / 0.75

    # Return the average of both methods for better accuracy
    return round((charBasedEstimate + wordBasedEstimate) / 2)

def get_readable_page(url: str):
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400

    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        if not parsed_url.scheme and parsed_url.netloc:
            url = "http://" + url
        else:
            return jsonify({"error": "Invalid URL format. Please provide a full URL (e.g., http://example.com)"}), 400
    
    content_html, links, images = fetch_webpage_python(url)

    if not content_html:
        return jsonify({"error": "Could not fetch or parse content from the URL"}), 500
    
    return jsonify({
        "url_requested": url,
        "content_html": content_html,
        "length": estimateTokenCount(content_html)
    })