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

def get_game_number(url):
    """
    read the game number of the pedantix
    """
    resp = requests.get(url)
    resp.raise_for_status()
    html = resp.text
    
    match = re.search(r'<[^>]*id=["\']puzzle-num["\'][^>]*>(\d+)</', html)
    if not match:
        raise RuntimeError("Couldn't find puzzle-num in page source")
    return int(match.group(1))

async def async_requests(words, game_number, url, request_url, limit=100):
    """
    perform asyncronously the post requests to the 
    pedantix server for each words of the list
    """
    positions = [''] * 5000
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
                    if index < 5000:
                        positions[index] = key

    
    return 'Wikipedia ' + ' '.join(filter(None, positions))

def google_search(text, num_results=10):
    """
    read the first results of a specific google search
    """
    pages_title = search(text, num_results=num_results, advanced=True)
    return [e.title for e in pages_title]

def write_solution(answers, url):
    """
    write the potential answers on the pedantix page
    """
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    wait = WebDriverWait(driver, 10)

    close_box = driver.find_element(By.ID, "dialog-close")
    driver.execute_script("arguments[0].click();", close_box);

    driver.find_element(By.CSS_SELECTOR, "button.fc-close.fc-icon-button").click()

    for answer in answers:
        clean_answer = answer.replace("'", " ").replace("-", " ")
        for word in clean_answer.split(' '):
            if word in ["Wikipédia", "Wikipedia", "-", "", "|", " " , ":", "..."]:
                continue
            print("Try:", word)

            text_box = wait.until(EC.visibility_of_element_located((By.ID, "guess")))
            text_box.clear()
            text_box.send_keys(word)
            
            guess_btn = wait.until(EC.element_to_be_clickable((By.ID, "guess-btn")))
            guess_btn.click()

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
    version = 'pedantix'
    game = 'live'

    wait_next_game(version, game)

    url = f"https://{version}.certitudes.org"
    request_url = f"https://{version}.certitudes.org/score"

    words = pull_common_words(version)[:2000]
    
    game_number = get_game_number(url)
    print(f"Running {version} {game_number}")
    start_time = time.time()
    text = asyncio.run(async_requests(words, game_number, url, request_url, limit=200))
    #print(text)
    print(f"POST request processed in {time.time() - start_time:.2f} seconds")

    answers = google_search(text, 10)
    print("Google results:", answers)
    write_solution(answers, url)

def main():
    parser = argparse.ArgumentParser(
        description="Run the Pedantle/Pédantix solver"
    )
    parser.add_argument(
        "-version", "-v",
        choices=["pedantle", "pedantix"],
        required=False,
        help="Which site to solve (pedantle or pedantix)"
    )
    parser.add_argument(
        "-game", "-g",
        choices=["live", "next"],
        required=False,
        help="Which game to solve (live or next)"
    )
    args = parser.parse_args()
    solve(args.version)

if __name__ == "__main__":
    main()