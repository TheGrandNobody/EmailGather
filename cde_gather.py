import requests
from bs4 import BeautifulSoup
import pandas as pd
from typing import Dict, List, Tuple, Optional
import time
import re
import os
from datetime import datetime


class CDEScraper:
    def __init__(self):
        self.base_url = "https://www.cde.ca.gov/SchoolDirectory/districtschool"
        self.details_url = "https://www.cde.ca.gov/SchoolDirectory/details"
        self.session = requests.Session()

    def get_school_links(self, page: int = 0, limit: int = None) -> List[Tuple[str, str]]:
        """Get school names and their detail page links from a listing page"""
        params = {
            "simplesearch": "Y",
            "sax": "true",
            "items": "500",
            "tab": "3",
            "page": str(page)
        }

        try:
            print(f"\nFetching school links from page {page + 1}/52...")
            response = self.session.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            schools = []
            rows = soup.find_all('tr')[1:]  # Skip header row
            print(f"Found {len(rows)} school entries")

            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 4:  # Ensure row has enough columns
                    school_link = cols[3].find('a')
                    if school_link:
                        school_name = school_link.text.strip()
                        href = school_link['href']
                        cds_code = re.search(r'cdscode=(\d+)', href)
                        if cds_code:
                            schools.append((school_name, cds_code.group(1)))
                            if limit and len(schools) >= limit:
                                print(f"Reached limit of {limit} schools")
                                break

            print(f"Successfully extracted {len(schools)} school links")
            return schools
        except Exception as e:
            print(f"Error fetching school links from page {page}: {str(e)}")
            return []

    def extract_emails(self, text: str) -> List[str]:
        """Extract all email addresses from a given text."""
        return list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))

    def extract_phone_numbers(self, text: str) -> List[str]:
        """Extract all phone numbers from a given text."""
        return list(set(re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)))

    def get_administrator_info(self, cds_code: str) -> Dict[str, str]:
        """Extract administrator, school records, business official, and general email and phone information"""
        params = {"cdscode": cds_code}

        try:
            response = self.session.get(self.details_url, params=params, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            admin_names = []
            admin_titles = []
            all_emails = set()
            all_phones = set()

            for row in soup.find_all('tr'):
                cells = row.find_all(['th', 'td'])

                # Extract emails & phone numbers from "Administrator" field
                if cells and cells[0].get_text(strip=True) == "Administrator":
                    admin_cell = cells[1]
                    admin_text = admin_cell.get_text("\n").strip()
                    admin_emails = self.extract_emails(admin_text)
                    admin_phones = self.extract_phone_numbers(admin_text)
                    all_emails.update(admin_emails)
                    all_phones.update(admin_phones)

                    lines = [line.strip() for line in admin_text.split("\n") if line.strip()]
                    if lines:
                        admin_names.append(lines[0])  # First line: Name
                        if len(lines) > 1:
                            admin_titles.append(lines[1])  # Second line: Title

                # Extract emails & phone numbers from "Chief Business Official" field
                elif cells and cells[0].get_text(strip=True) == "Chief Business Official":
                    business_official_cell = cells[1]
                    business_text = business_official_cell.get_text("\n").strip()
                    business_emails = self.extract_emails(business_text)
                    business_phones = self.extract_phone_numbers(business_text)
                    all_emails.update(business_emails)
                    all_phones.update(business_phones)

                # Extract emails from "Email" field (if available)
                elif cells and cells[0].get_text(strip=True) == "Email":
                    email_cell = cells[1]
                    email_text = email_cell.get_text("\n").strip()
                    email_links = self.extract_emails(email_text)
                    all_emails.update(email_links)

                # Extract emails & phone numbers from "School Records" field
                elif cells and cells[0].get_text(strip=True) == "School Records":
                    records_cell = cells[1]
                    records_text = records_cell.get_text("\n").strip()
                    records_emails = self.extract_emails(records_text)
                    records_phones = self.extract_phone_numbers(records_text)
                    all_emails.update(records_emails)
                    all_phones.update(records_phones)

            return {
                "Administrator Names": ", ".join(admin_names) if admin_names else "",
                "Administrator Titles": ", ".join(admin_titles) if admin_titles else "",
                "All Emails": ", ".join(sorted(all_emails)) if all_emails else "",
                "All Phones": ", ".join(sorted(all_phones)) if all_phones else ""
            }

        except Exception as e:
            print(f"Error fetching administrator info for CDS code {cds_code}: {str(e)}")
            return {"Administrator Names": "", "Administrator Titles": "", "All Emails": "", "All Phones": ""}

    def scrape_schools(self, num_schools: Optional[int] = None, delay: float = 0.5) -> pd.DataFrame:
        """
        Scrape school administrator information
        If num_schools is None, scrape all schools across all pages
        """
        all_data = []
        total_pages = 52 if num_schools is None else (num_schools // 500) + 1
        schools_needed = num_schools if num_schools is not None else float('inf')

        print(f"\nStarting school directory scraper...")
        print(f"Target: {'All schools' if num_schools is None else f'{num_schools} schools'}")

        try:
            for page in range(total_pages):
                remaining = schools_needed - len(all_data)
                if remaining <= 0:
                    break

                schools = self.get_school_links(page, limit=remaining if remaining < 500 else None)
                if not schools:
                    print(f"No more schools found on page {page + 1}")
                    break

                for school_name, cds_code in schools:
                    if len(all_data) >= schools_needed:
                        break

                    print(f"\nProcessing school {len(all_data) + 1}")
                    print(f"School: {school_name}")
                    print(f"CDS Code: {cds_code}")

                    try:
                        admin_info = self.get_administrator_info(cds_code)

                        print("Emails:", admin_info["All Emails"] if admin_info["All Emails"] else "No emails found")
                        print("Phone Numbers:", admin_info["All Phones"] if admin_info["All Phones"] else "No phones found")

                        all_data.append({
                            "School Name": school_name,
                            "Administrator Names": admin_info["Administrator Names"],
                            "Administrator Titles": admin_info["Administrator Titles"],
                            "Emails": admin_info["All Emails"],
                            "Phone Numbers": admin_info["All Phones"],
                            "CDS Code": cds_code
                        })

                    except Exception as e:
                        print(f"Error processing school {school_name}: {str(e)}")

        finally:
            df = pd.DataFrame(all_data)
            filename = f"cde_administrators_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(filename, index=False)
            print(f"\nResults saved to: {filename}")

            return df


if __name__ == "__main__":
    CDEScraper().scrape_schools(None, delay=0.5)
