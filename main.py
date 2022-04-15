from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup as bs
import json
from typing import Union
import argparse


BASE_WIKI_URL = 'https://en.wikipedia.org/'
WIKIPEDIA = 'wikipedia'
GOOGLE = 'google'


def parse_arguments():
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


def get_source(url) -> requests.Response:
    """Return the source code for the provided URL.

    Args:
        url (string): URL of the page to scrape.

    Returns:
        response (object): HTTP response object from requests_html.
    """

    try:
        session = requests.session()
        response = session.get(url)
        return response

    except requests.exceptions.RequestException as e:
        print(e)


def scrape_google(query):

    query = quote_plus(query)
    response = get_source(f"https://www.google.com/search?q={query}")

    soup = bs(response.text, "html.parser")
    heading_object = soup.find_all('a')

    # Iterate through the object
    # and print it as a string.
    for info in heading_object:
        print(info.getText())
        print("------")


def get_row_value(row, key) -> Union[float, str, list]:
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
                if isinstance(values, list):
                    if values[0] == '':
                        values.pop(0)
                    numeric_value = values[0]
                else:
                    numeric_value = values

                if numeric_value == '¥' or numeric_value == '₹' or numeric_value == '₽':
                    numeric_value = values[1]

                if '–' in numeric_value:
                    val_range = numeric_value.split("–")
                    numeric_value = (float(val_range[0]) + float(val_range[1])) / 2 # take the avg
                elif '-' in numeric_value and not numeric_value[0] == '-':
                    val_range = numeric_value.split("-")
                    numeric_value = (float(val_range[0]) + float(val_range[1])) / 2 # take the avg
                elif '—' in numeric_value:
                    val_range = numeric_value.split("—")
                    numeric_value = (float(val_range[0]) + float(val_range[1])) / 2 # take the avg
                elif 'U' in numeric_value:
                    numeric_value = float(numeric_value.replace("U", "")) * 0.71
                elif '₹' in numeric_value:
                    numeric_value = float(numeric_value.replace("₹", "")) * 0.013
                elif values[0] == '¥':
                    values.pop(0)
                    numeric_value = float(numeric_value)*0.0087
                elif values[0] == '₹' or values[0] == '₽':
                    values.pop(0)
                    numeric_value = float(numeric_value)*0.013

                value = float(numeric_value)
                if isinstance(values, list) and len(values) > 1:
                    if values[1].lower() == 'million':
                        value *= 1000000
                    elif values[1].lower() == 'billion':
                        value *= 1000000000000
        return value


def save_json_data(file_name: str, data: dict):
    with open(file_name, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_json_data(file_name: str) -> dict:
    with open(file_name, "r") as file:
        return json.load(file)


def get_wiki_info_box(url: str) -> dict:
    result = {}

    response = get_source(url)

    soup = bs(response.content)

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
                    result[key] = get_row_value(value, key)

    return result


def get_tables_info(url: str) -> list:
    result = []

    response = get_source(url)
    soup = bs(response.content)
    tables = soup.select(".wikitable.sortable i")
    for table in tables:
        if not table.find("a"):
            result.append({'title': table.get_text()})
        else:
            link = table.a['href']
            print(table.prettify())
            result.append(get_wiki_info_box(f"{BASE_WIKI_URL}/{link}"))

    return result


def scrape_wiki(page_id: str) -> tuple:

    info_box_data = get_wiki_info_box(f"{BASE_WIKI_URL}/wiki/{page_id}")
    tables_data = get_tables_info(f"{BASE_WIKI_URL}/wiki/{page_id}")

    return info_box_data, tables_data


if __name__ == '__main__':
    parse = parse_arguments()
    if parse.website == WIKIPEDIA:
        result: tuple = scrape_wiki(parse.page_title)
        save_json_data(f'{parse.page_title}.json', result[1])
        save_json_data(f'{parse.page_title}_info_box.json', result[0])
    elif parse.website == GOOGLE:
        # print(scrape_google("data science blogs"))
        pass
    print("Finished scrapping data")
