# GitHub Actionsを用いたWeb画像自動ダウンロードツール

## 1. 概要

このツールは、指定したウェブサイト（デフォルトでは `https://akibablog.blog.jp/`）に定期的にアクセスし、ページ内に掲載されている画像を自動でダウンロードしてDropboxにアップロードするものです。GitHub Actionsを利用して毎日自動実行されるため、サーバーレスで運用コストを抑えることができます。

## 2. 機能

- **自動スクレイピング**: 指定したURLのHTMLを解析し、画像URLを抽出します。
- **画像フィルタリング**: アイコンやバナーなどの小さな画像や、意図しない画像を除外するロジックを備えています。
- **ファイル名のリネーム**: ダウンロードした画像は `YYYYMMDD_元のファイル名` の形式にリネームされ、日付ごとに整理しやすくなっています。
- **Dropboxへの自動アップロード**: 取得した画像を指定したDropboxフォルダへ自動でアップロードします。
- **定期実行**: GitHub Actionsのスケジュール機能により、毎日指定した時刻（デフォルトでは日本時間午前3時）に自動で実行されます。
- **手動実行**: GitHub Actionsの画面からいつでも手動で実行することも可能です。

## 3. 技術要件

- **実行環境**: GitHub Actions (ubuntu-latest)
- **開発言語**: Python 3.11
- **主要ライブラリ**:
    - `requests`: HTTP通信
    - `BeautifulSoup4`: HTML解析
    - `Pillow`: 画像サイズの検証
    - `dropbox`: Dropbox API連携

## 4. セットアップ手順

### ステップ1: Dropboxアプリケーションの作成とアクセストークンの取得

1.  **Dropbox App Consoleにアクセス**: [Dropbox App Console](https://www.dropbox.com/developers/apps)にログインします。
2.  **新しいアプリを作成**: `Create app` ボタンをクリックします。
3.  **APIの選択**: `Scoped access` を選択します。
4.  **アクセスタイプの選択**: `App folder` を選択し、アプリに固有のフォルダへのアクセス権を与えます。
5.  **アプリ名の設定**: 任意のアプリ名（例: `My Image Scraper`）を入力し、`Create app` をクリックします。
6.  **権限の設定**: 作成されたアプリの `Permissions` タブに移動し、以下の権限にチェックを入れます。
    - `files.content.write`
    - `files.content.read`
7.  **アクセストークンの生成**: `Settings` タブに戻り、`Generated access token` のセクションで `Generate` ボタンをクリックしてアクセストークンを生成します。**このトークンは一度しか表示されないため、必ず安全な場所にコピーしてください。**

### ステップ2: GitHubリポジトリの準備

1.  このリポジトリを自身のGitHubアカウントにフォークするか、コードをダウンロードして新しいリポジトリを作成・プッシュします。

### ステップ3: GitHubリポジトリにSecretsを設定

1.  作成したGitHubリポジトリの `Settings` > `Secrets and variables` > `Actions` に移動します。
2.  `New repository secret` ボタンをクリックします。
3.  **Name**に `DROPBOX_ACCESS_TOKEN` と入力します。
4.  **Secret**に、ステップ1で取得したDropboxのアクセストークンを貼り付け、`Add secret` をクリックします。

### ステップ4: GitHub Actionsの有効化と実行

1.  リポジトリの `Actions` タブに移動します。
2.  `I understand my workflows, go ahead and enable them` というボタンが表示されている場合は、クリックしてワークフローを有効化します。
3.  左側のサイドバーから `Daily Image Scraper` ワークフローを選択します。
4.  `Run workflow` ドロップダウンをクリックし、`Run workflow` ボタンを押すことで、手動でスクリプトを実行できます。

    - 初回実行時は、この手動実行で正しく動作するか確認することをお勧めします。
    - 実行後、指定したDropboxのアプリフォルダ（`アプリ名` フォルダ）内に `akiba-images` というフォルダが作成され、その中に画像が保存されていれば成功です。

## 5. ファイル構成

```
.
├── .github/workflows/
│   └── daily-scraper.yml   # GitHub Actions ワークフロー定義ファイル
├── .gitignore              # Gitの追跡対象外ファイルを指定
├── README.md               # このファイル
├── requirements.txt        # Pythonの依存ライブラリリスト
└── scraper.py              # メインの画像ダウンロードスクリプト
```

## 6. カスタマイズ

### 実行スケジュールの変更

- `.github/workflows/daily-scraper.yml` ファイル内の `cron` の値を変更します。
- デフォルトは `0 18 * * *`（UTCの18時、日本時間の午前3時）です。cronの書式に従って変更してください。

### 対象URLの変更

- `scraper.py` ファイル内の `TARGET_URL` の値を変更します。

### Dropboxの保存先フォルダ名の変更

- `scraper.py` ファイル内の `DROPBOX_FOLDER` の値を変更します。

## 7. 注意事項

- **サイトへの負荷**: 対象サイトへ過度な負荷をかけないよう、スクリプト内には1秒の待機時間（`SLEEP_TIME`）を設けていますが、実行頻度や対象サイトの利用規約には十分注意してください。
- **法的責任**: このツールを使用して発生したいかなる問題についても、開発者は責任を負いません。自己責任でご利用ください。
- **エラーハンドリング**: 一部の画像のダウンロードに失敗しても処理は継続され、エラー内容はログファイル（`scraper.log`）に記録されます。ワークフロー実行後にアーティファクトとして保存されるため、Actionsの実行結果ページからダウンロードして確認できます。
