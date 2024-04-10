import random
import threading
import time
from urllib.parse import urlparse, unquote
import requests
from bs4 import BeautifulSoup
import os
import concurrent.futures
import curses

status = {}

# Class representing the data from the page source
class Data:
    def __init__(self, type, page_source):
        self.type = type
        soup = BeautifulSoup(page_source, "html.parser")
        if type == "archive":
            self.data = soup.find("table", "directory-listing-table")
        else:
            self.data = soup.find("pre")
            self.type = "pre"
            if self.data is None:
                self.data = soup.find("body")
                self.type = "body"
    
    def __iter__(self):
        if self.type == "archive":
            for i, tr in enumerate(self.data.find_all("tr")):
                if i <= 1:
                    continue
                link = tr.find("a")
                yield link.get("href")
        elif self.type == "pre" or self.type == "body":
            for i, a in enumerate(self.data.find_all("a")):
                yield a.get("href")
                

# Function to download a file from a URL and save it locally
def download_file(url, local_path, task_id):
    global status
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        total_size = int(response.headers.get("content-length", 0))
        chunk_size = 8 * 1024  # You can adjust this chunk size

        with open(local_path, "wb") as file:
            bytes_written = 0
            start_time = time.time()

            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file.write(chunk)
                    bytes_written += len(chunk)

                    # Calculate download speed and time elapsed
                    elapsed_time = time.time() - start_time
                    download_speed = bytes_written / (
                        1024 * elapsed_time + 0.000001
                    )  # Speed in KB/s

                    percent_complete = (bytes_written / total_size) * 100
                    # print(
                    #     f"Task {task_id}: Progress: {percent_complete:.2f}%  Speed: {download_speed:.2f} KB/s",
                    #     end="\r",
                    # )
                    status[task_id] = (percent_complete, download_speed, local_path)

            # print(f"Task {task_id}: Downloaded: {local_path}")
            status[task_id] = ("FIN", download_speed, local_path)


# Function to display the download status
def display_status(window):
    global status
    temp_status = status.copy()
    y, x = 0, 0
    for task_id, (percent_complete, download_speed, local_path) in temp_status.items():
        max_length = max([len(x[2]) for x in temp_status.values()])
        if percent_complete != "FIN":
            try:
                window.addstr(
                    y,
                    x,
                    f"Task {task_id}: {local_path:{max_length}} {percent_complete:.2f}% {download_speed:.2f} KB/s",
                )
                y += 1
            except curses.error:
                pass

# Separate Thread to display the download status
def display_status_thread(stdscr, interval=0.25):
    with condition:
        while not exit_flag.is_set():
            stdscr.clear()
            display_status(stdscr)
            stdscr.refresh()
    time.sleep(interval)


# Recursively download the entire directory
def download_recursive(
    base_url, current_url, base_path, executor: concurrent.futures.Executor, type="archive"
):
    futures = []
    response = requests.get(base_url + current_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"})
    page_source = response.text
    links = Data(type, page_source)
    limit = 1
    for i, href in enumerate(links):
        if  href[0] in ["?", "#"]:
            limit += 1
            continue
        if i < limit:
            continue
        if href and href[-1] == "/":
            if "blog" in href:
                continue
            futures.extend(
                download_recursive(base_url, current_url + href, base_path, executor, type)
            )
        elif href:
            local_path = os.path.join(
                base_path, unquote(urlparse(current_url + href).path.lstrip("/"))
            ).replace(" /", "/").replace("/", os.sep)

            # Remove forbidden characters for Windows filenames
            forbidden_chars = ['<', '>', ':', '"', '|', '?', '*']
            for char in forbidden_chars:
                local_path = local_path.replace(char, "")
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            download_url = base_url + "/" + current_url + "/" + href
            futures.append(
                executor.submit(
                    download_file,
                    download_url,
                    local_path,
                    random.randint(10**6, 10**7),
                )
            )
    return futures


if __name__ == "__main__":
    base_url = ""
    base_path = "./archive"
    type = ""

    user_path = input("Enter download directory [./archive]: ")
    while base_url == "":
        base_url = input("Enter URL: ")
    if user_path:
        base_path = user_path

    
    if "archive.org" in base_url:
        # remove header if present
        base_url = base_url.replace("https://archive.org/details/", "")
        base_url = base_url.replace("https://archive.org/", "")
        base_directory = base_url.split("/")[0]
        base_url = "https://archive.org/download/" + base_directory
        type = "archive"
        
    # remove tailing slash
    base_url = base_url.rstrip("/")

    # create download directory
    os.makedirs(base_path, exist_ok=True)
    stdscr = curses.initscr()
    curses.curs_set(0)
    stdscr.clear()

    exit_flag = threading.Event()
    condition = threading.Condition()
    status_thread = threading.Thread(target=display_status_thread, args=(stdscr, 0.1))
    status_thread.daemon = True

    status_thread.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = download_recursive(base_url, "/", base_path, executor, type)

    concurrent.futures.wait(futures)
    exit_flag.set()
    curses.endwin()
    print("--------------All downloads complete!--------------")
