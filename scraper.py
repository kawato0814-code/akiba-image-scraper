#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
アキバBlog画像自動ダウンロードスクリプト
指定したウェブサイトから画像を取得し、Dropboxへアップロードします。
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import dropbox
from dropbox.exceptions import ApiError

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scraper.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 設定
TARGET_URL = "https://akibablog.blog.jp/"
MIN_IMAGE_SIZE = 10  # 最小画像サイズ（px）
SLEEP_TIME = 1  # 画像取得間の待機時間（秒）
DROPBOX_FOLDER = "/akiba-images"  # Dropbox保存先フォルダ
VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

# 除外するURLパターン（アイコン、バナー等）
EXCLUDE_PATTERNS = [
    'counter',
    'banner',
    'bunner',
    'icon',
    'button',
    'small_parts'
]


class ImageScraper:
    """画像スクレイピングクラス"""
    
    def __init__(self, target_url, dropbox_token):
        self.target_url = target_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Dropboxクライアント初期化
        if dropbox_token:
            self.dbx = dropbox.Dropbox(dropbox_token)
            try:
                self.dbx.users_get_current_account()
                logger.info("Dropbox認証成功")
            except ApiError as e:
                logger.error(f"Dropbox認証失敗: {e}")
                self.dbx = None
        else:
            logger.warning("DropboxトークンがないためローカルPCに保存します")
            self.dbx = None
        
        self.downloaded_count = 0
        self.skipped_count = 0
        self.error_count = 0
    
    def fetch_page(self):
        """ページを取得"""
        try:
            logger.info(f"ページ取得開始: {self.target_url}")
            response = self.session.get(self.target_url, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            logger.info("ページ取得成功")
            return response.text
        except Exception as e:
            logger.error(f"ページ取得エラー: {e}")
            return None
    
    def extract_image_urls(self, html):
        """HTMLから画像URLを抽出"""
        soup = BeautifulSoup(html, 'html.parser')
        image_urls = []
        
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue
            
            # 絶対URLに変換
            absolute_url = urljoin(self.target_url, src)
            
            # 除外パターンチェック
            if any(pattern in absolute_url.lower() for pattern in EXCLUDE_PATTERNS):
                logger.debug(f"除外: {absolute_url}")
                continue
            
            # 拡張子チェック
            parsed = urlparse(absolute_url)
            path = parsed.path.lower()
            if not any(path.endswith(ext) for ext in VALID_EXTENSIONS):
                logger.debug(f"拡張子不一致: {absolute_url}")
                continue
            
            image_urls.append(absolute_url)
        
        # 重複除去
        image_urls = list(dict.fromkeys(image_urls))
        logger.info(f"画像URL抽出完了: {len(image_urls)}件")
        return image_urls
    
    def download_image(self, url):
        """画像をダウンロード"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"画像ダウンロードエラー ({url}): {e}")
            return None
    
    def check_image_size(self, image_data):
        """画像サイズをチェック"""
        try:
            img = Image.open(BytesIO(image_data))
            width, height = img.size
            
            if width < MIN_IMAGE_SIZE or height < MIN_IMAGE_SIZE:
                logger.debug(f"画像サイズが小さすぎる: {width}x{height}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"画像サイズチェックエラー: {e}")
            return False
    
    def generate_filename(self, url):
        """ファイル名を生成（日付プレフィックス付き）"""
        today = datetime.now().strftime("%Y%m%d")
        parsed = urlparse(url)
        original_filename = os.path.basename(parsed.path)
        
        # ファイル名が空の場合はURLからハッシュを生成
        if not original_filename:
            original_filename = f"image_{hash(url) % 10000}.jpg"
        
        return f"{today}_{original_filename}"
    
    def upload_to_dropbox(self, image_data, filename):
        """Dropboxにアップロード"""
        if not self.dbx:
            # Dropbox未設定の場合はローカル保存
            local_dir = Path("downloaded_images")
            local_dir.mkdir(exist_ok=True)
            local_path = local_dir / filename
            
            with open(local_path, 'wb') as f:
                f.write(image_data)
            logger.info(f"ローカル保存: {local_path}")
            return True
        
        try:
            dropbox_path = f"{DROPBOX_FOLDER}/{filename}"
            
            # 同名ファイルが存在する場合は上書き
            self.dbx.files_upload(
                image_data,
                dropbox_path,
                mode=dropbox.files.WriteMode.overwrite,
                mute=True
            )
            logger.info(f"Dropboxアップロード成功: {dropbox_path}")
            return True
            
        except ApiError as e:
            logger.error(f"Dropboxアップロードエラー ({filename}): {e}")
            return False
    
    def run(self):
        """メイン処理"""
        logger.info("=" * 60)
        logger.info("画像スクレイピング開始")
        logger.info("=" * 60)
        
        # ページ取得
        html = self.fetch_page()
        if not html:
            logger.error("ページ取得に失敗したため終了します")
            return
        
        # 画像URL抽出
        image_urls = self.extract_image_urls(html)
        if not image_urls:
            logger.warning("画像が見つかりませんでした")
            return
        
        # 画像ダウンロード・アップロード
        for i, url in enumerate(image_urls, 1):
            logger.info(f"処理中 ({i}/{len(image_urls)}): {url}")
            
            # ダウンロード
            image_data = self.download_image(url)
            if not image_data:
                self.error_count += 1
                continue
            
            # サイズチェック
            if not self.check_image_size(image_data):
                logger.info(f"スキップ（サイズ不足）: {url}")
                self.skipped_count += 1
                continue
            
            # ファイル名生成
            filename = self.generate_filename(url)
            
            # アップロード
            if self.upload_to_dropbox(image_data, filename):
                self.downloaded_count += 1
            else:
                self.error_count += 1
            
            # 待機（サーバー負荷軽減）
            if i < len(image_urls):
                time.sleep(SLEEP_TIME)
        
        # 結果サマリー
        logger.info("=" * 60)
        logger.info("処理完了")
        logger.info(f"ダウンロード成功: {self.downloaded_count}件")
        logger.info(f"スキップ: {self.skipped_count}件")
        logger.info(f"エラー: {self.error_count}件")
        logger.info("=" * 60)


def main():
    """エントリーポイント"""
    # 環境変数からDropboxトークンを取得
    dropbox_token = os.environ.get('DROPBOX_ACCESS_TOKEN')
    
    if not dropbox_token:
        logger.warning("環境変数 DROPBOX_ACCESS_TOKEN が設定されていません")
        logger.warning("画像はローカルの downloaded_images フォルダに保存されます")
    
    # スクレイパー実行
    scraper = ImageScraper(TARGET_URL, dropbox_token)
    scraper.run()


if __name__ == "__main__":
    main()
