import argparse
import json
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple
from urllib.parse import urlparse

class TabTidy:
    def __init__(self, timeout: int = 5, max_workers: int = 10):
        self.timeout = timeout
        self.max_workers = max_workers

    def check_url(self, url: str) -> Tuple[str, bool]:
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return url, False

            response = requests.head(url, timeout=self.timeout, allow_redirects=True)
            return url, response.status_code == 200
        except:
            return url, False

    def process_bookmarks(self, bookmarks: Dict) -> Dict:
        def process_folder(folder: Dict) -> Dict:
            if 'children' in folder:
                valid_children = []
                urls_to_check = []
                indices = []

                for i, child in enumerate(folder['children']):
                    if 'url' in child:
                        urls_to_check.append(child['url'])
                        indices.append(i)
                    else:
                        valid_children.append(process_folder(child))

                if urls_to_check:
                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        results = list(executor.map(self.check_url, urls_to_check))

                    for i, (url, is_valid) in zip(indices, results):
                        if is_valid:
                            valid_children.append(folder['children'][i])

                folder['children'] = valid_children
            return folder

        return process_folder(bookmarks)

    def clean_bookmarks(self, input_file: str, output_file: str) -> None:
        with open(input_file, 'r', encoding='utf-8') as f:
            bookmarks = json.load(f)

        cleaned_bookmarks = self.process_bookmarks(bookmarks)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_bookmarks, f, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser(description='检查并清理浏览器书签中的无效链接')
    parser.add_argument('input', help='输入书签文件路径')
    parser.add_argument('output', help='输出书签文件路径')
    parser.add_argument('--timeout', type=int, default=5, help='URL检查超时时间（秒）')
    parser.add_argument('--workers', type=int, default=10, help='最大并发线程数')
    
    args = parser.parse_args()
    
    tidy = TabTidy(timeout=args.timeout, max_workers=args.workers)
    tidy.clean_bookmarks(args.input, args.output)

if __name__ == '__main__':
    main()