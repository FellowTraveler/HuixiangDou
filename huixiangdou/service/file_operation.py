# Copyright (c) OpenMMLab. All rights reserved.
import os

import textract
from langchain_community.document_loaders import (CSVLoader, UnstructuredExcelLoader)
from loguru import logger
import fitz
import pandas as pd
import multiprocessing

class FileName:
    """Record file original name, copy to page and state"""
    def __init__(self, root: str, filename: str, _type:str):
        self.root = root
        self.basename = os.path.basename(filename)
        self.origin = os.path.join(root, filename)
        self.copypath = ''
        self._type = _type
        self.state = True
        self.reason = ''

    def __str__(self):
        return '{},{},{},{}\n'.format(self.basename, self.copypath, self.state, self.reason)

class FileOperation:
    """Encapsulate all file reading operations."""
    def __init__(self):
        self.image_suffix = ['.jpg', '.jpeg', '.png', '.bmp']
        self.md_suffix = '.md'
        self.text_suffix = ['.txt', '.text']
        self.excel_suffix = ['.xlsx', '.xls', '.csv']
        self.pdf_suffix = '.pdf'
        self.word_suffix = ['.docx', '.doc']
        self.normal_suffix = [self.md_suffix
                              ] + self.text_suffix + self.excel_suffix + [
                                  self.pdf_suffix
                              ] + self.word_suffix

    def get_type(self, filepath: str):
        if filepath.endswith(self.pdf_suffix):
            return 'pdf'

        if filepath.endswith(self.md_suffix):
            return 'md'

        for suffix in self.image_suffix:
            if filepath.endswith(suffix):
                return 'image'

        for suffix in self.text_suffix:
            if filepath.endswith(suffix):
                return 'text'

        for suffix in self.word_suffix:
            if filepath.endswith(suffix):
                return 'word'

        for suffix in self.excel_suffix:
            if filepath.endswith(suffix):
                return 'excel'
        return None

    def summarize(self, files: list):
        success = 0
        skip = 0
        failed = 0

        for file in files:
            if file.state:
                success += 1
            elif file.reason == 'skip':
                skip += 1
            else:
                failed +=1
            
            logger.info('{} {}'.format(file.reason, file.copypath))
        logger.info('累计{}文件，成功{}个，跳过{}个，异常{}个'.format(len(files), success, skip, failed))

    def scan_dir(self, repo_dir: str):
        files = []
        for root, _, filenames in os.walk(repo_dir):
            for filename in filenames:
                _type = self.get_type(filename)
                if _type is not None:
                    files.append(FileName(root=root, filename=filename, _type=_type))
        return files
    
    def read_pdf(self, filepath: str):
        # load pdf and serialize table


        def read_single_page(pdf_path, start_page, end_page, output_queue):
            with fitz.open(filepath) as all_pages:
                page = all_pages[page_id]
                pages = all_pages[start_page-1:end_page]

                text = ''
                for page in pages:
                    text += page.get_text()
                    tables = page.find_tables()
                    for table in tables:
                        tablename = '_'.join(filter(lambda x: x is not None and 'Col' not in x, table.header.names))
                        pan = table.to_pandas()
                        json_text = pan.dropna(axis=1).to_json(force_ascii=False)
                        text += tablename
                        text += '\n'
                        text += json_text
                        text += '\n'
                return text

        all_text = ''
        page_len = 0
        with fitz.open(filepath) as pdf:
            page_len = len(pdf)

        num_processes = 4
        result_queue = multiprocessing.Queue()
        
        pages_per_process = page_len // num_processes
        page_ranges = []
        pool = multiprocessing.Pool(processes=num_processes)

        for i in range(num_processes):
            start_page = i * pages_per_process + 1
            end_page = (i + 1) * pages_per_process if i < num_processes - 1 else page_len
            page_ranges.append((start_page, end_page))
        
        # 使用进程池执行任务
        pool.starmap(read_single_page, [(filepath,) + prange for prange in page_ranges], result_queue)
        pool.close()
        pool.join()

        while not result_queue.empty():
            page_text = result_queue.get()
            print(page_text)
            all_text += page_text

        return all_text

    def read_excel(self, filepath: str):
        table = None
        if filepath.endswith('.csv'):
            table = pd.read_csv(filepath)
        else:
            table = pd.read_excel(filepath)
        if table is None:
            return ''
        json_text = table.dropna(axis=1).to_json(force_ascii=False)
        return json_text

    def read(self, filepath: str):
        file_type = self.get_type(filepath)

        text = ''
        if file_type == 'md' or file_type == 'text':
            with open(filepath) as f:
                text = f.read()

        elif file_type == 'pdf':
            text += self.read_pdf(filepath)

        elif file_type == 'excel':
            text += self.read_excel(filepath)

        elif file_type == 'word':
            # https://stackoverflow.com/questions/36001482/read-doc-file-with-python
            # https://textract.readthedocs.io/en/latest/installation.html
            try:
                text = textract.process(filepath).decode('utf8')
            except Exception as e:
                logger.error((filepath, str(e)))
                return '', e
            # print(len(text))

        text = text.replace('\n\n', '\n')
        text = text.replace('\n\n', '\n')
        text = text.replace('\n\n', '\n')
        text = text.replace('  ', ' ')
        text = text.replace('  ', ' ')
        text = text.replace('  ', ' ')
        return text, None


if __name__ == '__main__':
    opr = FileOperation()
    text, error = opr.read('/data2/khj/test-data/test-table.pdf')
    print(text)
    # text, error = opr.read('/data2/khj/test-data/工作簿1.csv')
    # print(text)
    # text, error = opr.read('/data2/khj/test-data/模型上传表.xlsx')
    # print(text)
