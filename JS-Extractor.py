import os
import re
import urllib2
from burp import IBurpExtender
from burp import IContextMenuFactory
from javax.swing import JMenuItem, JFileChooser
from java.io import File
import urlparse

class BurpExtender(IBurpExtender, IContextMenuFactory):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._callbacks.setExtensionName("JS URL Extractor")
        self._callbacks.registerContextMenuFactory(self)
        self.downloader = Downloader()  # Create an instance of Downloader

    def createMenuItems(self, invocation):
        self.context = invocation
        menu_list = []
        menu_list.append(JMenuItem("Extract JS URLs to File", actionPerformed=lambda x, inv=invocation: self.start_extraction(inv)))
        return menu_list

    def start_extraction(self, invocation):
        folder_path = self.get_folder_path()
        if folder_path:
            js_urls = self.extract_js_urls(invocation)
            if js_urls:
                self.write_urls_to_file(folder_path, js_urls)
                self.downloader.download_js_files(folder_path)
            else:
                print("No JavaScript URLs found.")
        else:
            print("No folder selected. Extraction cancelled.")

    def get_folder_path(self):
        chooser = JFileChooser()
        chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY)
        chooser.setDialogTitle("Select Folder to Save JS URLs")
        if chooser.showOpenDialog(None) == JFileChooser.APPROVE_OPTION:
            return chooser.getSelectedFile().getAbsolutePath()
        return None

    def extract_js_urls(self, invocation):
        print("Starting JS URL extraction...")
        js_urls = set()
        selected_messages = invocation.getSelectedMessages()
        if not selected_messages:
            print("No messages selected. Please select a request in the site map.")
            return js_urls

        base_url = self._helpers.analyzeRequest(selected_messages[0]).getUrl()
        print("Base URL:", str(base_url))

        sitemap = self._callbacks.getSiteMap(None)
        print("Total sitemap entries:", len(sitemap))

        for item in sitemap:
            url = self._helpers.analyzeRequest(item).getUrl()
            url_string = str(url)
            
            if not url_string.startswith(str(base_url)):
                continue
            
            print("Examining URL:", url_string)
            
            # Check if the URL contains .js (case-insensitive)
            if '.js' in url_string.lower():
                print("Found JS URL:", url_string)
                js_urls.add(url_string)
                continue

            # If not a .js file, check the content type
            response = item.getResponse()
            if response:
                response_info = self._helpers.analyzeResponse(response)
                headers = response_info.getHeaders()
                
                content_type = next((header.split(':', 1)[1].strip().lower() for header in headers if header.lower().startswith('content-type:')), '')
                print("Content-Type:", content_type)
                
                if 'javascript' in content_type:
                    print("Found JS content:", url_string)
                    js_urls.add(url_string)
                elif 'text/html' in content_type:
                    body = response[response_info.getBodyOffset():].tostring()
                    script_srcs = re.findall(r'<script[^>]+src=["\'](.*?)["\']', body, re.IGNORECASE)
                    for src in script_srcs:
                        if '.js' in src.split('?')[0]:  # Check if it's a JS file
                            if src.startswith('http'):
                                print("Found JS in HTML (absolute):", src)
                                js_urls.add(src)
                            else:
                                full_url = self.build_absolute_url(url_string, src)
                                print("Found JS in HTML (relative):", full_url)
                                js_urls.add(full_url)

        print("\nTotal JS URLs found:", len(js_urls))
        print("JavaScript URLs:")
        for js_url in sorted(js_urls):
            print(js_url)

        return js_urls

    def build_absolute_url(self, base_url, relative_url):
        return urlparse.urljoin(base_url, relative_url)

    def write_urls_to_file(self, folder_path, urls):
        filename = "js_urls.txt"
        file_path = os.path.join(folder_path, filename)
        try:
            with open(file_path, 'w') as f:
                for url in urls:
                    f.write(url + '\n')
            print("JavaScript URLs written successfully to: %s" % file_path)
        except IOError as e:
            print("Error writing to file: %s" % str(e))


class Downloader:
    def download_js_files(self, folder_path):
        filename = "js_urls.txt"
        file_path = os.path.join(folder_path, filename)
        urls = self.read_urls(file_path)
        for url in urls:
            content = self.download_javascript(url)
            if content is not None:
                safe_filename = self.create_safe_filename(url)
                full_path = os.path.join(folder_path, safe_filename)
                self.save_javascript(content, full_path)
                print("Saved {0} as {1}".format(url, safe_filename))

    def read_urls(self, file_path):
        with open(file_path, 'r') as file:
            return [line.strip() for line in file if line.strip()]

    def download_javascript(self, url):
        try:
            response = urllib2.urlopen(url)
            if response.getcode() == 200:
                return response.read()
            else:
                print("Error downloading {0}: HTTP {1}".format(url, response.getcode()))
                return None
        except urllib2.URLError as e:
            print("Error downloading {0}: {1}".format(url, str(e)))
            return None

    def create_safe_filename(self, url):
        parsed_url = urlparse.urlparse(url)
        path = parsed_url.path
        filename = os.path.basename(path)
        if not filename:
            filename = parsed_url.netloc
        filename = os.path.splitext(filename)[0]
        safe_filename = re.sub(r'[^a-zA-Z0-9]', '_', filename)
        if not safe_filename or safe_filename[0].isdigit():
            safe_filename = 'js_' + safe_filename
        return safe_filename + '.js'

    def save_javascript(self, content, filename):
        with open(filename, 'wb') as file:
            file.write(content)
