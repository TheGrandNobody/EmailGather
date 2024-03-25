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
import re

URL = 'https://scholenopdekaart.nl/zoeken/basisscholen?zoektermen=Groningen&weergave=Lijst'
TARGET_PUBLIC = "basisscholen/groningen"
TARGET_INTERNATIONAL = "/in/"

COUNTRY = 'Netherlands'

def init_driver(proxy=False) -> webdriver.Firefox:
    """ Initialize a Selenium webdriver for Firefox.

    Returns:
        webdriver.Firefox: The Selenium webdriver object.
    """
    options = FirefoxOptions()
    if proxy:
        options.set_preference("network.proxy.type", 1)
        options.set_preference("network.proxy.socks", sys.argv[3])
        options.set_preference("network.proxy.socks_port", int(sys.argv[4]))
        options.set_preference("network.proxy.socks_version", 5)
    options.add_argument("--headless")  # This line enables headless mode
    service = FirefoxService(executable_path=GeckoDriverManager().install())
    driver = webdriver.Firefox(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver

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
        wait = WebDriverWait(driver, 2)  # Wait up to 2 seconds
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
                searching = False
    page_source = driver.page_source
    if not source:
        time.sleep(3)
    return page_source

def get_links(soup: BeautifulSoup, target: str, newurl: str, international=False) -> list:
    school_links = []
    # Ensure we always have an iterable of elements, adjusting based on `international`
    links = soup if international else soup.find_all('a')
    
    for link in links:
        if international:
            link = link.find('a')
        href = link.get('href')
        if href and target in href:
            school_links.append(href if international else newurl.replace("href", href))
    return school_links

def get_school_links(url: str, target: str, newurl: str, source=None, international=False) -> list[str]:
    """ Get the links to the school pages from the main page.

    Args:
        url (str): The URL to fetch the content from.
        target (str): The target string to match in the href attribute.
        link (str): The link to append to the base URL.
        source (str, optional): The page source. Defaults to None.

    Returns:
        list[str]: A list of the school page links.
    """
    if source is None:
        source, _ = fetch_url_static(url)
    soup = BeautifulSoup(source, 'html.parser')
    # If the page is for international schools, find the div with the cities and schools
    if international:
        soup = soup.find('div', id='cities-schools').find_all('h3', class_='mb20')
        
    return get_links(soup, target, newurl, international)

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
    # Check if the page is to be fetched using Selenium or pycurl
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} (True | False) (-i | -p) optional: (both required) ip port")
        sys.exit(1)
    # Check if the user wants to use a proxy
    proxy = len(sys.argv) > 3
    # Initialize variables
    curl, driver, page_source, all_emails = None, None, None, set()

    # Fetch emails for native public schools
    if sys.argv[2].lower() == '-p':
        print("Fetching links")
        # Get the links to the school pages
        if sys.argv[1].lower() == 'true':
            driver = init_driver(proxy)
            page_source = fetch_url_dynamic(URL, driver, True)
        school_links = get_school_links(URL, TARGET_PUBLIC, "https://scholenopdekaart.nlhrefcontact", page_source)
        print("Fetching emails")
        # Extract emails from the school pages
        for school_url in school_links:
            emails, curl = extract_emails_from_school_page(school_url, curl if all_emails else None, driver=driver)
            if emails:
                all_emails.update(emails)
    # Otherwise fetch emails for international schools
    else:
        print("Fetching lists")
        failed, city_links, page_links, school_links = set(), set(), set(), []
        # Initialize a Mozilla Firefox webdriver
        driver = init_driver(proxy)
        school_links = {'https://www.isrlo.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.internationalschoolwassenaar.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.uwcmaastricht.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.internationalwaldorfschool.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.riversarnhem.org/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.britams.nl/?utm_campaign=premium+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.elckerlyc-international.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.nordangliaeducation.com/nais-rotterdam?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.esbergen.eu/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.optimist-international-school.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.g-s-v.nl/en/international-primary-school?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://isgroningen.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.amityschool.nl/?utm_campaign=premium+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.ash.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.internationalschoolhaarlem.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.harbourinternational.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.florencius.nl/bilingual-school/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.winford.nl/en/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.tisaschool.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://internationalschooltwente.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.ishthehague.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://gmischool.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.winford.nl/en/schools/winford-dutch-schools/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.europeanschoolthehague.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://internationalschoolbreda.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://sekolah-indonesia.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com#', 'https://hsvid.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'http://www.jsa.nl/11ELNL/English.html?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.britishschool.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://riss.wolfert.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://ipshilversum.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://isleiden.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.ishilversum.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://disdh.nl/de/home/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://lfvvg.com/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://alasca.espritscholen.nl/home?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.amersfoortinternationalschool.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://lighthousese.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://lfvvg.com/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.isutrecht.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://salto-internationalschool.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://internationalschoolalmere.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://internationalschooldelft.com/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.islaren.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.isa.nl/?utm_campaign=premium+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.internationalfrenchschool.com/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://aics.espritscholen.nl/home/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://eerde.com/?utm_campaign=premium+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.isecampus.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://amstelland-international-school.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://denise.espritscholen.nl/en/home?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com', 'https://www.sondervickinternational.nl/?utm_campaign=free+listing&utm_medium=referral&utm_source=international-schools-database.com'}
        # # Fetch the page source
        # page_source = fetch_url_dynamic(f"https://www.international-schools-database.com/country/{COUNTRY.lower()}", driver, True)
        # # Get the links to the city pages
        # city_links.update(get_school_links("", TARGET_INTERNATIONAL, "href", page_source, True))
        # print("Fetching Pages")
        # # Get the links to the school pages
        # for city_url in city_links:
        #     city_source = fetch_url_dynamic(city_url, driver, True)
        #     soup = BeautifulSoup(city_source, 'html.parser')
        #     # Function to check if an element has a 'data-id' attribute
        #     def has_data_id(tag):
        #         return tag.has_attr('data-id')
        #     # Find all elements that have a 'data-id' attribute
        #     elements = soup.find_all(has_data_id)
        #     for element in elements:
        #         page_links.add(element.get('href'))
        # print("Fetching links")
        # # Get the links to the school websites
        # for link in page_links:
        #     soup = BeautifulSoup(fetch_url_dynamic(link, driver), 'html.parser')
        #     a_tag = soup.find('a', title="School's webpage")
        #     if a_tag:
        #         href_value = a_tag['href']
        #         school_links.append(href_value)
        print("Fetching emails")
        # Extract emails from the school pages
        for url in school_links:
            contact_url, failed_contact = None, False
            # Try to find a contacts page
            soup = BeautifulSoup(fetch_url_dynamic(url, driver), 'html.parser')
            for link in soup.find_all('a'):
                href = link.get('href')
                if href and 'contact' in href:
                    contact_url = href if 'http' in href else url + href
                    # Extract emails from the contact page
                    soup2 = BeautifulSoup(fetch_url_dynamic(contact_url, driver), 'html.parser')
                    # Define a function to use as a filter for info emails
                    def has_at_in_href(tag):
                        return tag.name == 'a' and tag.has_attr('href') and any(i in tag['href'] for i in ['info', 'contact', 'dir', 'administration']) and all(g not in tag['href'] for g in ['recru', 'www', 'office'])
                    emails = soup2.find_all(has_at_in_href)
                    for email in emails:
                        if email and re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email['href'].replace('mailto:', '')):
                            all_emails.add(email['href'].replace('mailto:', ''))
                            failed_contact = False
                            break
                        else:
                            failed_contact = True
                    if not failed_contact:
                        break
            # If there is no contact page, try extracting emails from the main page
            if not contact_url or failed_contact:
                # Define a function to use as a filter
                def has_at_in_href(tag):
                    return tag.name == 'a' and tag.has_attr('href') and '@' in tag['href'] and all(g not in tag['href'] for g in ['recru', 'www'])
                a_tags = soup.find_all(has_at_in_href)
                for a_tag in a_tags:
                    email = a_tag['href'].replace('mailto:', '')
                    if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                        all_emails.add(email)
                        failed_contact = False
                if failed_contact:
                    failed.add(url)
        # Write the failed URLs to a file
        with open('failed.txt', 'w') as file:
            for url in sorted(failed):
                file.write(f"{url}\n")

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