import pycurl
from io import BytesIO
from bs4 import BeautifulSoup
import sys
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from selenium.common.exceptions import TimeoutException
import time

URL = 'https://scholenopdekaart.nl/zoeken/middelbare-scholen?zoektermen=Rotterdam&weergave=Lijst'

def fetch_url_static(url: str, curl=None) -> tuple[str, pycurl.Curl]:
    """ Fetches the page content of a URL using pycurl. Much faster for static pages.

    Args:
        url (str): The URL to fetch the content from.
        curl (pycurl.Curl, optional): The pycurl object to use. Defaults to None.

    Returns:
        tuple[str, pycurl.Curl]: The content of the page and the pycurl object.
    """
    if curl is None:
        c = pycurl.Curl()
        c.setopt(pycurl.DNS_CACHE_TIMEOUT, 60) # Sets DNS cache timeout
        c.setopt(pycurl.TCP_KEEPALIVE, 1)
        c.setopt(pycurl.SSL_VERIFYPEER, 0)
        c.setopt(pycurl.SSL_VERIFYHOST, 0)
        c.setopt(pycurl.USERAGENT, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    else:
        c = curl
    buffer = BytesIO()
    c.setopt(pycurl.URL, url)
    c.setopt(pycurl.WRITEDATA, buffer)
    c.perform()
    return buffer.getvalue().decode('utf-8'), c

def fetch_url_dynamic(url: str, driver: webdriver.Chrome | webdriver.Firefox, source=False) -> str:
    """ Fetches the page content of a URL using  Selenium webdriver. Slower but can handle dynamic pages.

    Args:
        url (str): The URL to fetch the content from.
        driver (webdriver.Chrome | webdriver.Firefox): The Selenium webdriver object to use.
        source (bool, optional): Whether to return the page source or not. Defaults to False.

    Returns:
        str: The content of the page.
    """
    searching = True
    driver.get(url)
    if source:
        wait = WebDriverWait(driver, 2)  # Wait up to 10 seconds
        try:
            # Click the cookie consent button
            cookie_consent_button = wait.until(EC.element_to_be_clickable((By.ID, 'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')))
            cookie_consent_button.click()
        except:
            # If the button is no longer present or not clickable within the timeout, continue
            pass
        while searching:
            try:
                # Wait for the button to be clickable
                button_to_click = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'zoeken-resultaten-lijst-meer')))
                # Click the button
                button_to_click.click()
            except TimeoutException:
                # If the button is no longer present or not clickable within the timeout, break from the loop
                print("No more items to load.")
                searching = False
    page_source = driver.page_source
    if not source:
        time.sleep(3)
    return page_source

def get_school_links(url: str, source=None) -> list[str]:
    """ Get the links to the school pages from the main page.

    Args:
        url (str): The URL to fetch the content from.
        source (str, optional): The page source. Defaults to None.

    Returns:
        list[str]: A list of the school page links.
    """
    if source is None:
        source, _ = fetch_url_static(url)
    soup = BeautifulSoup(source, 'html.parser')
    school_links = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'middelbare-scholen/rotterdam' in href:  # Adjusted to match your condition
            school_links.append(f"https://scholenopdekaart.nl{href}contact")
    return school_links

def extract_emails_from_school_page(url: str, c=None, driver=None) -> tuple[set[str], pycurl.Curl | None]:
    """ Extracts emails from a school page.

    Args:
        url (str): The URL to fetch the content from.
        c (pycurl.Curl, optional): The pycurl object to use. Defaults to None.
        driver (webdriver.Chrome | webdriver.Firefox, optional): The Selenium webdriver object to use. Defaults to None.

    Returns:
        tuple[set[str], pycurl.Curl | None]: A set of emails and the pycurl object.
    """
    # Check if we are using pycurl or Selenium
    if driver:
        html = fetch_url_dynamic(url, driver)
        curl = None
    else:
        html, curl = fetch_url_static(url, c)
    soup = BeautifulSoup(html, 'html.parser')
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and '@' in href:
            # Remove 'mailto:' from the email
            email = href.replace('mailto:', '')
            return {email}, (None if driver else curl)
    
    return None, None if driver else curl

def main() -> None:
    """ Main function to run the email gathering bot.
    """
    # Initialize variables
    curl, driver = None, None

    # Check if the page is to be fetched using Selenium or pycurl
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} True | False")
        sys.exit(1)
    if sys.argv[1].lower() == 'true':
        options = FirefoxOptions()
        options.add_argument("--headless")  # This line enables headless mode
        service = FirefoxService(executable_path=GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        page_source = fetch_url_dynamic(URL, driver, True)
        school_links = get_school_links(URL, page_source)
    else:
        school_links = get_school_links(URL)
    all_emails = set()

    # Extract emails from the school pages
    for school_url in school_links:
        if not all_emails:
            emails, curl = extract_emails_from_school_page(school_url, driver=driver)
        else:
            emails, curl = extract_emails_from_school_page(school_url, curl, driver=driver)
        if emails:
            all_emails.update(emails)

    # Close the pycurl object or the Selenium webdriver
    if curl:
        curl.close()
    elif driver:
        driver.quit()

    # Save the emails to a file
    with open('emails.txt', 'w') as file:
        for email in sorted(all_emails):
            file.write(f"{email}\n")
    print(f"Emails extracted and saved to emails.txt")

if __name__ == '__main__':
    main()