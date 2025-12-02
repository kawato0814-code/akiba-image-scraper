#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
アキバBlog画像自動ダウンロードスクリプト（Playwright版）
iframe内の広告画像と左右サイドバーの画像を取得します。
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import asyncio
from playwright.async_api import async_playwright
import requests
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
MIN_IMAGE_HEIGHT = 250  # 最小画像高さ（px）- サムネイルを除外
DROPBOX_FOLDER = "/akiba-images"  # Dropbox保存先フォルダ
VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

# 取得対象ドメイン
TARGET_DOMAINS = [
    'livedoor.blogimg.jp',  # 左右サイドバー画像
    'reajyu.net'  # iframe内広告画像
]


class ImageScraper:
    """画像スクレイピングクラス"""
    
    def __init__(self, target_url, app_key, app_secret, refresh_token):
        self.target_url = target_url
        
        # Dropboxクライアント初期化（リフレッシュトークン対応）
        if app_key and app_secret and refresh_token:
            self.dbx = dropbox.Dropbox(
                app_key=app_key,
                app_secret=app_secret,
                oauth2_refresh_token=refresh_token
            )
            try:
                self.dbx.users_get_current_account()
                logger.info("Dropbox認証成功")
            except ApiError as e:
                logger.error(f"Dropbox認証失敗: {e}")
                self.dbx = None
        else:
            logger.warning("Dropbox認証情報がないためローカルPCに保存します")
            self.dbx = None
        
        self.downloaded_count = 0
        self.skipped_count = 0
        self.error_count = 0
    
    async def extract_image_urls(self):
        """Playwrightを使用して画像URLを抽出"""
        image_urls = []
        
        async with async_playwright() as p:
            logger.info("ブラウザを起動中...")
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                logger.info(f"ページにアクセス: {self.target_url}")
                await page.goto(self.target_url, wait_until='networkidle', timeout=60000)
                
                # ページが完全に読み込まれるまで少し待機
                await page.wait_for_timeout(3000)
                
                # メインページの画像を取得
                main_images = await page.evaluate('''() => {
                    const images = Array.from(document.querySelectorAll('img'));
                    return images.map(img => ({
                        src: img.src,
                        width: img.naturalWidth,
                        height: img.naturalHeight
                    }));
                }''')
                
                logger.info(f"メインページから {len(main_images)} 件の画像を検出")
                
                for img in main_images:
                    if img['src'] and img['height'] >= MIN_IMAGE_HEIGHT:
                        # 対象ドメインの画像のみ
                        if any(domain in img['src'] for domain in TARGET_DOMAINS):
                            image_urls.append(img['src'])
                            logger.info(f"対象画像: {img['src']} ({img['width']}x{img['height']})")
                
                # iframe内の画像を取得
                frames = page.frames
                logger.info(f"{len(frames)} 個のフレームを検出")
                
                for frame in frames:
                    try:
                        frame_url = frame.url
                        if not frame_url or frame_url == 'about:blank':
                            continue
                        
                        logger.info(f"フレームを調査: {frame_url}")
                        
                        # フレーム内の画像を取得
                        frame_images = await frame.evaluate('''() => {
                            const images = Array.from(document.querySelectorAll('img'));
                            return images.map(img => ({
                                src: img.src,
                                width: img.naturalWidth || img.width,
                                height: img.naturalHeight || img.height
                            }));
                        }''')
                        
                        for img in frame_images:
                            if img['src']:
                                # reajyu.netドメインの画像は全て取得
                                if 'reajyu.net' in img['src']:
                                    image_urls.append(img['src'])
                                    logger.info(f"iframe内画像: {img['src']} ({img['width']}x{img['height']})")
                    
                    except Exception as e:
                        logger.debug(f"フレーム処理エラー: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"ページ取得エラー: {e}")
            
            finally:
                await browser.close()
        
        # 重複除去
        image_urls = list(dict.fromkeys(image_urls))
        logger.info(f"画像URL抽出完了: {len(image_urls)}件")
        return image_urls
    
    def download_image(self, url):
        """画像をダウンロード"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"画像ダウンロードエラー ({url}): {e}")
            return None
    
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
    
    async def run(self):
        """メイン処理"""
        logger.info("=" * 60)
        logger.info("画像スクレイピング開始")
        logger.info("=" * 60)
        
        # 画像URL抽出
        image_urls = await self.extract_image_urls()
        
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
            
            # ファイル名生成
            filename = self.generate_filename(url)
            
            # アップロード
            if self.upload_to_dropbox(image_data, filename):
                self.downloaded_count += 1
            else:
                self.error_count += 1
            
            # 待機（サーバー負荷軽減）
            if i < len(image_urls):
                time.sleep(1)
        
        # 結果サマリー
        logger.info("=" * 60)
        logger.info("処理完了")
        logger.info(f"ダウンロード成功: {self.downloaded_count}件")
        logger.info(f"スキップ: {self.skipped_count}件")
        logger.info(f"エラー: {self.error_count}件")
        logger.info("=" * 60)


def main():
    """エントリーポイント"""
    # 環境変数からDropbox認証情報を取得
    app_key = os.environ.get('DROPBOX_APP_KEY')
    app_secret = os.environ.get('DROPBOX_APP_SECRET')
    refresh_token = os.environ.get('DROPBOX_REFRESH_TOKEN')
    
    if not (app_key and app_secret and refresh_token):
        logger.warning("環境変数 DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN が設定されていません")
        logger.warning("画像はローカルの downloaded_images フォルダに保存されます")
    
    # スクレイパー実行
    scraper = ImageScraper(TARGET_URL, app_key, app_secret, refresh_token)
    asyncio.run(scraper.run())

if __name__ == "__main__":
    main()
