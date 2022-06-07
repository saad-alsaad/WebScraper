from collections import defaultdict
import requests
from bs4 import BeautifulSoup as bs
import json
from typing import Union
import argparse


BASE_WIKI_URL = 'https://en.wikipedia.org/'
BASE_GOOGLE_URL = 'https://www.google.com/'
WIKIPEDIA = 'wikipedia'
GOOGLE = 'google'


def parse_arguments():
    """
    This function parse the options passed to the script.
    :return: parsed arguments
    """

    parser = argparse.ArgumentParser(description='Scraper Options.', prog='SCRIPT')
    parser.add_argument('--version', action='version', version='%(prog)s 1.0')
    parser.add_argument('--website', type=str, nargs=1, choices=[WIKIPEDIA, GOOGLE], metavar='<Website Name>',
                        help='The name of the website you want to scrap. options: wikipedia or google', required=True)
    parser.add_argument('--page_title', type=str, nargs=1, metavar='<Page Title>',
                        help='The page title (can be grabbed from the URL)', required=True)

    args = parser.parse_args()

    args.website = args.website[0]
    args.page_title = args.page_title[0]
    return args


class ScrapingBase:
    def __init__(self, base_url: str):
        self.session = requests.session()
        self.base_url = base_url

    def get_source(self, url: str) -> requests.Response:
        """
        Return the source code for the provided URL.
        :param url: URL is a string of the page to scrape.
        :return (object): HTTP response object from requests_html.
        """

        try:
            response = self.session.get(url)
            return response

        except requests.exceptions.RequestException as e:
            print(e)

    def get_content(self, url: str) -> bs:
        response = self.get_source(url)
        return bs(response.content)

    def _save_json_data(self, file_name: str, data: dict):
        """
        This method save the passed data to JSON file.
        :param file_name: the name of the JSON file
        :param data: the data (dictionary) that should be stored in the JSON file
        :return: None
        """
        with open(f"{file_name}.json", 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def close_session(self):
        self.session.close()


class WikiScraping(ScrapingBase):
    def __init__(self, base_url: str, page_title: str):
        super().__init__(base_url)
        self.tables_data = None
        self.info_box_data = None
        self.page_title = page_title

    def _get_numeric_value(self, values: str) -> float:
        """
        This method get the number of the values string, the string could be currency, budget, or Box Office.
        :param values: parsed string that contain numeric value
        :return: a float number for the parsed string
        """

        if isinstance(values, list):
            if values[0] == '':
                values.pop(0)
            numeric_value = values[0]
        else:
            numeric_value = values

        if numeric_value == '¥' or numeric_value == '₹' or numeric_value == '₽':
            numeric_value = values[1]

        numeric_value = numeric_value.replace("~", "") if '~' in numeric_value else numeric_value

        if '–' in numeric_value:
            val_range = numeric_value.split("–")
            numeric_value = (float(val_range[0]) + float(val_range[1])) / 2  # take the avg
        elif '-' in numeric_value and not numeric_value[0] == '-':
            val_range = numeric_value.split("-")
            numeric_value = (float(val_range[0]) + float(val_range[1])) / 2  # take the avg
        elif '—' in numeric_value:
            val_range = numeric_value.split("—")
            numeric_value = (float(val_range[0]) + float(val_range[1])) / 2  # take the avg
        elif 'U' in numeric_value:
            numeric_value = float(numeric_value.replace("U", "")) * 0.71
        elif '₹' in numeric_value:
            numeric_value = numeric_value.replace("₹", "")
            numeric_value = ''.join([num for num in numeric_value if num.isdigit() or num == '.'])
            print(numeric_value)
            numeric_value = float(numeric_value) * 0.013
        elif values[0] == '¥':
            values.pop(0)
            numeric_value = float(numeric_value) * 0.0087
        elif values[0] == '₹' or values[0] == '₽':
            values.pop(0)
            numeric_value = float(numeric_value) * 0.013

        return float(numeric_value)

    def get_row_value(self, row: 'Tag', key: str) -> Union[float, str, list]:
        if row.find("li"):
            return [li.get_text(" ", strip=True).replace("\xa0", " ") for li in row.find_all("li")]
        elif row.find("br"):
            return [text for text in row.stripped_strings]
        else:
            value = row.get_text(" ", strip=True).replace("\xa0", " ")
            if not value:
                value = row.find("span").get_text(" ", strip=True).replace("\xa0", " ")
            if key.lower() == 'running time' or key.lower() == 'budget' or key.lower() == 'box office':
                if isinstance(value, list):
                    value = value[0]
                if value == 'unknown' or value == 'Unknown':
                    value = None
                else:
                    value = value.replace("$", "") # need to pick money in usd currency
                    value = value.replace(",", "")
                    value = value.replace(">", "")
                    value = value.replace("under ", "")
                    value = value.replace("est. ", "")
                    value = value.replace("A", "")
                    value = value.replace("US", "")
                    values = value.split(' ')

                    value = self._get_numeric_value(values)

                    if isinstance(values, list) and len(values) > 1:
                        if values[1].lower() == 'million':
                            value *= 1000000
                        elif values[1].lower() == 'billion':
                            value *= 1000000000000
            return value

    def get_wiki_info_box(self, url: str) -> dict:
        result = defaultdict()

        print(url)
        soup = self.get_content(url)

        info_box = soup.find(class_="infobox vevent")
        if info_box:
            rows: list = info_box.find_all("tr")
            for ref_tag in soup.find_all("sup"):
                ref_tag.decompose()

            title = rows[0].find(class_="infobox-above summary")
            if title:
                result['title'] = title.get_text()
                rows = rows[1:]

            image = rows[0].find(class_="infobox-image")
            if image:
                result['image'] = image.find("a")['href']
                rows = rows[1:]

            for row in rows:
                key = row.find(class_="infobox-label")
                if key:
                    key = key.get_text(" ", strip=True).replace("\xa0", " ")
                    if key:
                        value = row.find(class_="infobox-data")
                        result[key] = self.get_row_value(value, key)

        return result

    def get_tables_info(self, url: str) -> list:
        result = []

        soup = self.get_content(url)
        tables = soup.select(".wikitable.sortable i")
        for table in tables:
            if not table.find("a"):
                result.append({'title': table.get_text()})
            else:
                link = table.a['href']
                result.append(self.get_wiki_info_box(f"{self.base_url}/{link}"))

        return result

    def start_scraping(self):
        """
        This method can be called to start scrapping data from Wikipedia based on self.page_title and self.base_url.
        It gets the data from the page and info box of the page.
        :return: None
        """
        self.info_box_data = self.get_wiki_info_box(f"{self.base_url}/wiki/{self.page_title}")
        self.tables_data = self.get_tables_info(f"{self.base_url}/wiki/{self.page_title}")

    def save_json_data(self):
        """
        This method save the scraped data into two Json files. the first file is for the page and the second is for info box data.
        :return: None
        """
        super()._save_json_data(self.page_title, self.tables_data)
        super()._save_json_data(f"{self.page_title}_info_box", self.info_box_data)


class GoogleScraping(ScrapingBase):
    def __init__(self, base_url: str, keyword: str):
        super().__init__(base_url)
        self.keyword = keyword

    def start_scraping(self):
        """
        This method can be called to start scrapping data from Google based on self.page_title and self.base_url.
        :return: None
        """
        soup = self.get_content(f"{self.base_url}/search?q={self.keyword}")
        heading_object = soup.find_all('a')

        for info in heading_object:
            print(info.getText())
            print("------")


if __name__ == '__main__':
    parse = parse_arguments()
    if parse.website == WIKIPEDIA:
        wiki_scarper = WikiScraping(BASE_WIKI_URL, parse.page_title)
        wiki_scarper.start_scraping()
        wiki_scarper.save_json_data()
        wiki_scarper.close_session()
    elif parse.website == GOOGLE:   # not supported yet
        google_scraper = GoogleScraping(BASE_GOOGLE_URL, parse.page_title)
        google_scraper.start_scraping()
        google_scraper.close_session()
    print("Finished scrapping data")
