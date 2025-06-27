from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

import time
import datetime
import zoneinfo

import requests
import re

from googlesearch import search

import asyncio
import aiohttp

import argparse

def pull_common_words(version):
    """
    read the most common words from the data folder
    """
    if version == 'pedantix':
        filename = 'data/most_common_wikipedia_words_fr.txt'
    elif  version == 'pedantle':
        filename = 'data/most_common_wikipedia_words_en.txt'
    else:
        raise RuntimeError("Unknown version")
    with open(filename, 'r', encoding='utf-8') as file:
        words = file.read().split()
    return words

def get_html(url):
    """
    get the html page from the pedantix page
    """
    resp = requests.get(url)
    resp.raise_for_status()
    html = resp.text

    return html

def read_game_number(html):
    """
    read the game number from the html
    """
    match = re.search(r'<[^>]*id=["\']puzzle-num["\'][^>]*>(\d+)</', html)

    if not match:
        raise RuntimeError("Couldn't find puzzle-num in the html")
    return int(match.group(1))

def read_answer_length(html):
    """
    read the length of the  answer from the html
    """
    match = re.search(r'<div[^>]*\bid=["\']wiki["\'][^>]*>(.*?)</div>',
        html, re.DOTALL | re.IGNORECASE)
    if not match:
        raise RuntimeError("Couldn't find answer length in the html")

    inner = match.group(1)
    spans = re.findall(r'<span\b', inner, re.IGNORECASE)
    return len(spans)

async def async_requests(words_position, 
                         words, 
                         game_number, 
                         url, 
                         request_url, 
                         limit=100) -> None:
    """
    perform asyncronously the post requests to the 
    pedantix server for each words of the list
    """
    request_url = f"{request_url}?n={game_number}"

    connector = aiohttp.TCPConnector(limit=limit)
    timeout   = aiohttp.ClientTimeout(total=None)
    headers   = {"Origin": url}

    async with aiohttp.ClientSession(connector=connector,
                                     timeout=timeout,
                                     headers=headers) as session:

        tasks = []
        for word in words:
            payload = {"num": game_number, "word": word,"answer": [word]}
            task = asyncio.create_task(session.post(request_url, json=payload))
            tasks.append(task)

        for task in asyncio.as_completed(tasks):
            try:
                resp = await task
                resp.raise_for_status()
                data = await resp.json()
            except Exception as e:
                print(e)
                continue

            for key, indices in data.get('x', {}).items():
                if '#' in key:
                    continue
                for index in indices:
                    words_position[index] = key

def merge_words_position(p1, p2):
    """
    DEPRECATED funcion
    merge 2 arrays with words positions
    """
    for i in range(len(p1)):
        if p1[i] == "":
            p1[i] = p2[i]
    return p1

def google_search(text, num_results=10):
    """
    read the first results of a specific google search
    """
    pages_title = search(text, num_results=num_results, advanced=True)
    return [e.title for e in pages_title]

def open_driver(url):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    close_box = driver.find_element(By.ID, "dialog-close")
    driver.execute_script("arguments[0].click();", close_box);

    driver.find_element(By.CSS_SELECTOR, "button.fc-close.fc-icon-button").click()

    return driver

ANSWERS_CACHE = {"Wikipédia", "Wikipedia", "Wiki", "-", "", "|", " " , ":", "..."}
def check_solutions(final_answer, answers, url, request_url, game_number):
    
    headers = {"Origin": url}
    request_url = f"{request_url}?n={game_number}"

    global ANSWERS_CACHE
    for answer in answers:
        clean_answer = answer.replace("'", " ").replace("-", " ")
        for word in clean_answer.split(' '):
            if word in ANSWERS_CACHE:
                continue
            payload = {"num": game_number, "word": word,"answer": [word]}
            resp = requests.post(request_url, json=payload, headers=headers)

            data = resp.json()

            for key, indices in data.get('x', {}).items():
                if '#' in key:
                    continue
                for index in indices:
                    if index < len(final_answer):
                        final_answer[index] = key

            ANSWERS_CACHE.add(word)

def write_solution(answer, driver):
    """
    write the potential answers on the pedantix page
    """
    wait = WebDriverWait(driver, 10)
    for word in answer:
            print("Try:", word)

            text_box = wait.until(EC.visibility_of_element_located((By.ID, "guess")))
            text_box.clear()
            text_box.send_keys(word)
            
            guess_btn = wait.until(EC.element_to_be_clickable((By.ID, "guess-btn")))
            guess_btn.click()
            ANSWERS_CACHE.add(word)

def wait_next_game(version, game):
    """
    wait until next game starts if game == next
    """
    if game == 'next':
        tz = zoneinfo.ZoneInfo("Europe/Paris")
        now = datetime.datetime.now(tz)

        if version == 'pedantix':
            target = datetime.datetime.combine(now.date(),
                    datetime.time(12, 0, 0, 1),tzinfo=tz) 
        if version == 'pedantle':
            target = datetime.datetime.combine(now.date(),
                    datetime.time(21, 0, 0, 1),tzinfo=tz)

        seconds_to_wait = (target - now).total_seconds()
        if seconds_to_wait > 0:
            print(f"Sleeping for {seconds_to_wait:.2f} seconds until {target.isoformat()}")
            time.sleep(seconds_to_wait)

def solve(version='pedantix', game='live'):
    """
    main entry point for pedantix solver
    """
    wait_next_game(version, game)

    url = f"https://{version}.certitudes.org"
    request_url = f"https://{version}.certitudes.org/score"

    words = pull_common_words(version)
    words_position = dict()
    
    game_html = get_html(url)

    game_number = read_game_number(game_html)
    answer_length = read_answer_length(game_html)

    print(f"Running {version} {game_number}")
    print(f"{answer_length} words to find!")

    driver = open_driver(url)
    bucket_size = 500
    buckets = [words[i:i+bucket_size] for i in range(0, len(words), bucket_size)]

    answer = [""] * answer_length

    for bucket in buckets:

        start_time = time.time()
        asyncio.run(async_requests(words_position, bucket, game_number, url, request_url, limit=200))

        text = 'Wikiedia ' + ' '.join(words_position[i] for i in sorted(words_position))
        print(f"POST request processed in {time.time() - start_time:.2f} seconds")
        answers = google_search(text, 5)
        print("Google results:", answers)
        check_solutions(answer, answers, url, request_url, game_number)
        if "" not in answer:
            write_solution(answer, driver)
            break

def main(raw_args=None):
    start_time = time.time()
    parser = argparse.ArgumentParser(description="Run the Pedantle/Pédantix solver")
    parser.add_argument("-version", "-v", choices=["pedantle", "pedantix"],
                        required=False, 
                        help="Which site to solve (pedantle or pedantix)")
    parser.add_argument("-game", "-g", choices=["live", "next"],
                        required=False, 
                        help="Which game to solve (live or next)")
    if raw_args is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(raw_args)
    solve(args.version, args.game)
    print(f"Solved {args.version} in {time.time() - start_time:.2f} seconds")
    

if __name__ == "__main__":
    #main()
    main(["-v", "pedantle", "-g", "live"])