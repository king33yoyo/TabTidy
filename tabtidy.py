import argparse
import requests
import re
import sys
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag
from tabtidy_log import TabTidyLogger
import logging


# 尝试导入lxml解析器，用于解析HTML文档
try:
    import lxml
    PARSER = 'lxml'  # 优先使用lxml解析器，因为它更快且功能更强大
except ImportError:
    PARSER = 'html.parser'  # 如果lxml不可用，则使用内置的html.parser

class LinkTidy:
    def __init__(self, timeout: int = 10, max_workers: int = 10, debug: bool = False):
        """初始化LinkTidy实例
        
        Args:
            timeout (int): URL检查的超时时间（秒）
            max_workers (int): 并发检查的最大线程数
            debug (bool): 是否启用调试日志
        """
        # 初始化基本属性
        self.timeout = timeout  # URL检查超时时间
        self.max_workers = max_workers  # 最大并发线程数
        self.deleted_bookmarks = []  # 存储已删除的书签
        self.valid_bookmarks = 0  # 有效书签计数
        self.total_bookmarks = 0  # 总书签计数
        
        # 初始化日志管理器
        log_level = logging.DEBUG if debug else logging.INFO
        self.logger = TabTidyLogger(log_level=log_level).get_logger()
        
        # 初始化请求会话，以便重用连接
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self.session.max_redirects = 5  # 限制重定向次数

    def __del__(self):
        """析构函数，确保会话被正确关闭"""
        if hasattr(self, 'session'):
            self.session.close()

    def _add_to_deleted(self, title: str, url: str, reason: str) -> None:
        """添加到已删除书签列表
        
        Args:
            title (str): 书签标题
            url (str): 书签URL
            reason (str): 删除原因
        """
        self.deleted_bookmarks.append({
            'title': title, 
            'url': url, 
            'reason': reason
        })

    def _is_unsafe_domain(self, domain: str) -> bool:
        """检查域名是否不安全（内网IP、环回地址等）
        
        Args:
            domain (str): 要检查的域名或IP
            
        Returns:
            bool: 如果不安全返回True，否则返回False
        """
        # 检查是否为环回地址
        if domain == 'localhost' or domain == '127.0.0.1' or '::1' in domain:
            return True
        
        # 检查是否为内网IP
        try:
            if domain.replace('.', '').isdigit():  # 可能是IPv4
                ip = ipaddress.ip_address(domain)
                return (
                    ip.is_private or 
                    ip.is_reserved or 
                    ip.is_loopback or 
                    ip.is_link_local
                )
        except ValueError:
            pass  # 不是有效IP，继续检查
        
        # 检查常见内网域名
        unsafe_domains = [
            'intranet', 'internal', 'private', 'corp', 'local', 
            'lan', 'home.arpa', 'localdomain', 'example.com'
        ]
        return any(unsafe in domain for unsafe in unsafe_domains)

    def check_url(self, url: str, title: str = '') -> Tuple[str, bool]:
        """检查URL是否有效
        
        Args:
            url (str): 要检查的URL
            title (str): URL对应的书签标题
            
        Returns:
            Tuple[str, bool]: 返回处理后的URL和是否有效的标志
        """
        # 记录正在检查的URL信息
        self.logger.debug(f'正在检查URL: {url} (标题: {title})')
        
        try:
            # 1. 如果URL不以http或https开头，添加https前缀
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                self.logger.debug(f'添加https前缀: {url}')
            
            # 2. 解析URL并验证基本格式
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                self.logger.warning(f'无效的URL格式: {url}')
                self._add_to_deleted(title, url, '无效的URL格式')
                return url, False
            
            # 3. 安全检查 - 阻止内网IP和环回地址
            netloc = parsed.netloc.split(':')[0]  # 移除端口号
            if self._is_unsafe_domain(netloc):
                self.logger.warning(f'不安全的目标地址: {url}')
                self._add_to_deleted(title, url, '不安全的目标地址')
                return url, False
            
            # 4. 检查URL是否包含不适当内容
            invalid_keywords = ['porn', 'xxx', 'gambling', 'warez', 'crack']
            for keyword in invalid_keywords:
                if keyword in url.lower():
                    self.logger.warning(f'URL包含不适当内容: {title} ({url})')
                    self._add_to_deleted(title, url, 'URL包含不适当内容')
                    return url, False
            
            # 5. 实际检查URL可访问性
            try:
                # 首先尝试HEAD请求
                #response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
                response = self.session.get(
                        url, 
                        timeout=self.timeout, 
                        allow_redirects=True,
                        stream=True  # 流式请求，不下载完整内容
                    )
                # 如果服务器不支持HEAD请求，尝试GET请求
                # if response.status_code in (405, 501, 403):
                #     self.logger.debug(f'服务器不支持HEAD请求，尝试GET请求: {url}')
                #     response = self.session.get(
                #         url, 
                #         timeout=self.timeout, 
                #         allow_redirects=True,
                #         stream=True  # 流式请求，不下载完整内容
                #     )
                    # 只读取一小部分内容就关闭连接
                if hasattr(response, 'raw') and response.raw:
                    response.raw.read(1024)
                response.close()
                
                # 2xx和3xx状态码表示URL有效
                is_valid = 200 <= response.status_code < 400
                
                if is_valid:
                    self.logger.debug(f'URL有效: {title} ({url}) - 状态码: {response.status_code}')
                else:
                    self.logger.warning(f'URL无效: {title} ({url}) - 状态码: {response.status_code}')
                    self._add_to_deleted(title, url, f'状态码错误: {response.status_code}')
                
                return url, is_valid
                
            except requests.exceptions.Timeout:
                self.logger.warning(f'请求超时: {title} ({url})')
                self._add_to_deleted(title, url, '请求超时')
                return url, False
            except requests.exceptions.TooManyRedirects:
                self.logger.warning(f'重定向次数过多: {title} ({url})')
                self._add_to_deleted(title, url, '重定向次数过多')
                return url, False
            except requests.exceptions.SSLError:
                self.logger.warning(f'SSL证书验证失败: {title} ({url})')
                self._add_to_deleted(title, url, 'SSL证书验证失败')
                return url, False
            except requests.exceptions.ConnectionError:
                self.logger.warning(f'连接错误: {title} ({url})')
                self._add_to_deleted(title, url, '连接错误')
                return url, False
            except requests.RequestException as e:
                # 处理其他请求异常
                self.logger.warning(f'请求失败: {title} ({url}) - {str(e)}')
                self._add_to_deleted(title, url, f'请求异常: {str(e)}')
                return url, False
                
        except Exception as e:
            # 处理其他未预期的异常
            self.logger.error(f'检查URL时出错: {title} ({url}) - {str(e)}')
            self._add_to_deleted(title, url, str(e))
            return url, False

    def process_bookmarks(self, soup: BeautifulSoup) -> BeautifulSoup:
        """处理书签文件，检查并移除无效链接
        
        Args:
            soup (BeautifulSoup): 解析后的书签文件内容
            
        Returns:
            BeautifulSoup: 处理后的书签文件内容
        """
        try:
            # 获取所有书签链接
            all_links = soup.find_all('a')
            self.total_bookmarks = len(all_links) if all_links else 0
            self.logger.info(f'文件中共包含 {self.total_bookmarks} 个书签')
            
            # 创建文件副本用于处理
            new_soup = BeautifulSoup(str(soup), PARSER)
            
            # 提取所有需要检查的URL和标题
            urls_to_check = []
            for a_tag in all_links:
                try:
                    # 验证链接标签的有效性
                    if a_tag and hasattr(a_tag, 'attrs') and isinstance(a_tag.attrs, dict) and 'href' in a_tag.attrs:
                        url = a_tag['href']
                        title = a_tag.string if a_tag.string else '无标题'
                        urls_to_check.append((url, title, a_tag))
                except Exception as e:
                    self.logger.error(f"处理链接标签时出错: {e}")
                    continue
            
            self.logger.info(f'将检查 {len(urls_to_check)} 个URL的有效性')
            
            # 处理找到的URL
            if urls_to_check:
                # 使用线程池并行检查所有URL
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    check_results = list(executor.map(lambda x: self.check_url(x[0], x[1]), 
                                               [(url, title) for url, title, _ in urls_to_check]))
                
                # 统计有效URL数量
                self.valid_bookmarks = sum(1 for _, is_valid in check_results if is_valid)
                
                # 收集有效URL
                valid_urls = {url for (url, _, _), (_, is_valid) in zip(urls_to_check, check_results) if is_valid}
                
                # 处理无效链接
                invalid_links = 0
                for a_tag in new_soup.find_all('a'):
                    try:
                        # 验证并处理每个链接
                        if a_tag and hasattr(a_tag, 'attrs') and isinstance(a_tag.attrs, dict) and 'href' in a_tag.attrs:
                            url = a_tag['href']
                            # 标准化URL格式
                            url_with_prefix = ('https://' + url) if not url.startswith(('http://', 'https://')) else url
                            
                            # 移除无效链接
                            if url not in valid_urls and url_with_prefix not in valid_urls:
                                parent_dt = a_tag.find_parent('dt')
                                if parent_dt:
                                    parent_dt.decompose()
                                    invalid_links += 1
                                    self.logger.debug(f'移除无效链接: {url}')
                    except Exception as e:
                        self.logger.error(f"处理链接标签时出错: {e}")
                        continue
                
                self.logger.info(f'已移除 {invalid_links} 个无效链接')
                
                # 清理空文件夹
                self.remove_empty_folders(new_soup)
            else:
                self.logger.warning('未找到任何需要检查的URL')
            
            return new_soup
        except Exception as e:
            self.logger.error(f"处理书签时发生异常: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return soup

    def remove_empty_folders(self, soup: BeautifulSoup) -> None:
        """移除书签中的空文件夹
        
        递归检查并删除不包含任何书签或子文件夹的空文件夹。
        为避免处理过深的嵌套，最多迭代3次。
        
        Args:
            soup (BeautifulSoup): 书签文件的BeautifulSoup对象
        """
        try:
            # 查找书签文件的根DL标签
            main_dl = soup.find('dl')
            if not main_dl:
                self.logger.error('未找到主DL标签')
                return
            
            # 初始化文件夹计数器
            folder_count = 0
            empty_folder_count = 0
            
            # 迭代处理嵌套文件夹（最多3次）
            for iteration in range(3):
                folders = []
                for dt in soup.find_all('dt'):
                    try:
                        # 检查并跳过顶级文件夹（如"收藏夹栏"）
                        parent_dl = dt.parent
                        if parent_dl and parent_dl.name == 'dl' and parent_dl.parent and parent_dl.parent.name == 'body':
                            folder_name = dt.find("h3").string if dt.find("h3") and dt.find("h3").string else "未命名文件夹"
                            self.logger.debug(f'跳过顶级文件夹: {folder_name}')
                            continue
                        
                        # 收集所有包含h3标题和dl子标签的文件夹
                        if dt and dt.find('h3') and dt.find('dl'):
                            folders.append(dt)
                    except Exception as e:
                        self.logger.error(f"处理文件夹DT标签时出错: {e}")
                        continue
                
                # 更新文件夹计数并检查是否需要继续迭代
                folder_count = len(folders)
                if folder_count == 0:
                    break
                
                self.logger.debug(f'第{iteration+1}次迭代: 发现{folder_count}个文件夹')
                
                # 处理每个文件夹
                for dt in folders:
                    try:
                        # 获取文件夹的标题和内容
                        h3 = dt.find('h3')
                        dl = dt.find('dl')
                        
                        if not dl:
                            continue
                        
                        # 获取文件夹名称
                        folder_name = h3.string if h3 and h3.string else '未命名文件夹'
                        
                        # 检查文件夹是否为空（无书签和子文件夹）
                        has_links = dl.find('a') is not None  # 检查是否包含书签
                        has_subfolders = any(  # 检查是否包含子文件夹
                            sub_dt and sub_dt.find('h3')
                            for sub_dt in dl.find_all('dt', recursive=False)
                        )
                        
                        # 如果文件夹为空，则删除
                        if not has_links and not has_subfolders:
                            self.logger.debug(f'移除空文件夹: {folder_name}')
                            dt.decompose()
                            empty_folder_count += 1
                    except Exception as e:
                        self.logger.error(f"处理文件夹时出错: {e}")
                        continue
            
            # 输出处理结果统计
            self.logger.info(f'处理完成，检查了 {folder_count} 个文件夹，移除了 {empty_folder_count} 个空文件夹')
        
        except Exception as e:
            self.logger.error(f"移除空文件夹时发生异常: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def clean_bookmarks(self, input_file: str, output_file: str) -> None:
        """清理书签文件，移除无效链接并保存结果
        
        读取指定的书签文件，检查所有链接的有效性，移除无效链接，
        并将处理后的结果保存到新文件。同时记录处理过程中的统计信息。
        
        Args:
            input_file (str): 输入书签文件的路径
            output_file (str): 输出书签文件的路径
        """
        self.logger.info(f'开始处理书签文件: {input_file}')
        
        try:
            # 读取并验证书签文件
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
                file_size = len(content)
                self.logger.info(f'读取文件成功，内容长度: {file_size} 字节')
                
                # 验证文件格式
                if '<!DOCTYPE NETSCAPE-Bookmark-file-1>' not in content:
                    self.logger.warning('文件可能不是标准的Netscape书签格式')
            
            # 使用指定解析器处理HTML内容
            self.logger.info(f'使用 {PARSER} 解析器解析HTML')
            soup = BeautifulSoup(content, PARSER)
            self.logger.info('HTML解析成功')
            
            # 输出文件结构信息
            dl_tags = soup.find_all('dl')  # 文件夹标签
            a_tags = soup.find_all('a')    # 链接标签
            self.logger.info(f'文件中包含 {len(dl_tags)} 个文件夹和 {len(a_tags)} 个链接')
            
            # 处理书签内容
            new_soup = self.process_bookmarks(soup)
            
            # 保存处理后的文件
            with open(output_file, 'w', encoding='utf-8') as f:
                output_content = str(new_soup)
                f.write(output_content)
                self.logger.info(f'写入输出文件成功: {output_file}')
            
            # 输出处理结果统计
            self.logger.info(f'书签处理完成, 共处理 {self.total_bookmarks} 个书签')
            self.logger.info(f'有效书签: {self.valid_bookmarks}')
            self.logger.info(f'无效书签: {len(self.deleted_bookmarks)}')
            
            # 显示已删除的书签详情（最多显示10个）
            if self.deleted_bookmarks and self.logger.level <= logging.INFO:
                self.logger.info('已删除的书签列表（最多显示10个）:')
                for bookmark in self.deleted_bookmarks[:10]:
                    self.logger.info(
                        f"- {bookmark['title']} ({bookmark['url']}) - 原因: {bookmark['reason']}"
                    )
                if len(self.deleted_bookmarks) > 10:
                    self.logger.info(f"... 还有 {len(self.deleted_bookmarks) - 10} 个未显示")
            
        except Exception as e:
            # 处理文件操作过程中的异常
            self.logger.error(f'处理书签文件时出错: {str(e)}')
            import traceback
            self.logger.error(traceback.format_exc())


def main():
    """主函数：解析命令行参数并执行书签清理操作
    
    支持的命令行参数：
    - input: 输入书签文件路径
    - output: 输出书签文件路径
    - --timeout: URL检查超时时间（秒）
    - --workers: 最大并发线程数
    - --debug: 启用调试日志
    """
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(
        description='检查并清理浏览器书签中的无效链接',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # 添加必需参数
    parser.add_argument('input', help='输入书签文件路径')
    parser.add_argument('output', help='输出书签文件路径')
    
    # 添加可选参数
    parser.add_argument(
        '--timeout',
        type=int,
        default=5,
        help='URL检查超时时间（秒）'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=10,
        help='最大并发线程数'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试日志'
    )
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 创建LinkTidy实例
    tidy = LinkTidy(
        timeout=args.timeout,
        max_workers=args.workers,
        debug=args.debug
    )
    
    # 执行书签清理
    tidy.clean_bookmarks(args.input, args.output)

if __name__ == '__main__':
    main()