# TabTidy

一个用于检测和清理浏览器收藏夹中无效链接的Python工具。TabTidy可以帮助你维护整洁的书签列表，自动检查并移除已失效的网站链接。

## 功能特点

- 支持批量检查网址有效性
- 多线程并发处理，提高检查效率
- 保留文件夹结构，仅清理无效链接
- 可配置的超时时间和并发数
- 支持UTF-8编码的书签文件
- **新增：支持 HTML 格式书签文件 (例如 Netscape Bookmark File Format)**

## 安装依赖

```bash
pip install requests beautifulsoup4
```

## 使用方法

```bash
python tabtidy.py input_file output_file [--timeout 5] [--workers 10]
```

### 参数说明

- `input_file`: 输入的书签文件路径 (支持 JSON 和 HTML 格式)
- `output_file`: 处理后的书签文件保存路径 (JSON 格式)
- `--timeout`: URL检查超时时间（秒），默认为5秒
- `--workers`: 最大并发线程数，默认为10

### 书签文件格式

支持以下书签文件格式：
1.  **JSON 格式**: 结构示例：
    ```json
    {
      "children": [
        {
          "name": "文件夹1",
          "children": [
            {
              "name": "示例网站",
              "url": "https://example.com"
            }
          ]
        }
      ]
    }
    ```
2.  **HTML 格式**: (例如 Netscape Bookmark File Format) 常见的浏览器导出格式。

## 开发计划

- [x] 支持 HTML 格式书签文件
- [ ] 支持更多浏览器的书签格式 (除通用JSON和HTML外)
- [ ] 添加进度显示
- [ ] 生成清理报告
- [ ] 支持自定义URL验证规则

## 许可证

本项目采用MIT许可证。详见 [LICENSE](LICENSE) 文件。
