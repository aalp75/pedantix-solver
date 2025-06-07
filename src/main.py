from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

import time

import requests
import re

from googlesearch import search

import nest_asyncio, asyncio
import aiohttp

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

async def async_score(words, game_number, request_url, limit):
    """
    perform asyncronously the post request to pedantix for each words of the list
    """
    positions = [''] * 5000
    #request_url = f"{request_url}?n={game_number}"
    #request_url = f"https://pedantle.certitudes.org/score?n={game_number}"
    request_url = f"{request_url}?n={game_number}"

    connector = aiohttp.TCPConnector(limit=limit)
    timeout   = aiohttp.ClientTimeout(total=None)
    headers   = {"Origin": "https://pedantle.certitudes.org"}

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

    text = 'Wikipedia ' + ' '.join(filter(None, positions))
    return text

def pull_common_words():
    """
    read the most common words from the data folder
    """
    with open('data/most_common_wikipedia_words_en.txt', 'r', encoding='utf-8') as file:
        words = file.read().split()
    return words

def google_search(text):
    """
    read the 10 first results of a specific google search
    """
    pages_title = search(text, num_results=10, advanced=True)
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
        for word in answer.split(' '):
            if word in ("Wikipedia", "-", ""):
                continue
                
            text_box = wait.until(EC.visibility_of_element_located((By.ID, "guess")))
            text_box.clear()
            text_box.send_keys(word)
            
            guess_btn = wait.until(EC.element_to_be_clickable((By.ID, "guess-btn")))
            guess_btn.click()

def solve(version='pedantix'):
    """
    main entry point for pedantix solver
    """

    url = "https://pedantle.certitudes.org/"
    request_url = "https://pedantle.certitudes.org/score"

    words = pull_common_words()[:2000]
    game_number = get_game_number(url)
    print(f"Running {version} {game_number}")
    start_time = time.time()
    text = asyncio.run(async_score(words, game_number, request_url, 100))
    print(f"POST request ran in {time.time() - start_time:.2f} seconds")

    answers =  google_search(text)
    write_solution(answers, url)

if __name__ == "__main__":
    solve()