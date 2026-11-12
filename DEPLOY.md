# Renderで公開する

この構成はPython/FastAPIのWebサービスです。静的サイトとしてではなく、Web Serviceとして作成してください。
Plotlyは同梱しており、グラフ描画に外部CDNは不要です。サンプルは架空の3店舗・180台で、実店舗に通信しません。

## デプロイ

1. この変更を含むブランチをGitHubへプッシュします。
2. [Render Dashboard](https://dashboard.render.com/) にログインし、GitHubの 70230kW/Car_item_heatmap へのアクセスを許可します。
3. **New → Blueprint** でリポジトリと公開するブランチを選び、ルートの render.yaml を読み込みます。
4. サービス名・Freeプランを確認し、デプロイを実行します。料金や利用条件はRender側の最新表示を確認してください。
5. 完了後、Renderが表示するHTTPS URLを開きます。URLはデプロイ結果から確認し、事前に固定しないでください。

Blueprintを使わない場合は **New → Web Service → Python 3** で次を設定します。

- Build Command: pip install -r requirements-deploy.txt
- Start Command: python -m uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
- Health Check Path: /healthz
- Environment: PYTHON_VERSION=3.12.14
- インスタンス: Free
- Auto Deploy: Off（更新時は手動でデプロイ）

データベースやAPIキーの設定は不要です。入力内容は利用者のブラウザに保存されます。
無料サービスは休止・リソース制限によって初回表示が遅くなることがあります。常時稼働が必要な場合は有料プランを別途検討してください。

## 公開後の確認

- /healthz がHTTP 200と {"status":"ok"} を返す。
- トップ画面の「サンプルで試す」で3店舗が表示される。
- 年式／走行距離、台数／構成比、四象限の境界値を変更できる。
- PCとスマートフォンで操作できる。
- 実際の在庫一覧URLをまず1ページで試す。対象サイトの規約・robots.txtを確認する。
- ローカル・プライベートアドレスへの取得要求が400で拒否される。

実店舗の抽出可否はサイト構造とアクセス制限に依存します。JavaScriptのみで生成される一覧には未対応です。
公開APIは認証なしで利用可能です。取得処理は1プロセスで同時2件までで、それ以上は503とRetry-Afterを返します。
これは利用者別のレート制限ではありません。大規模な一般公開には、ホスティング側の利用制限・監視を追加してください。

## ローカルの再現・検証

Python 3.12を使い、リポジトリ内で順に実行します。

    python -m venv .venv
    .venv/bin/python -m pip install -r requirements-deploy.txt
    .venv/bin/python -m pip check
    .venv/bin/python test_scraper.py
    .venv/bin/python -m unittest -v test_web
    .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000

Windowsでは .venv/bin/python を .venv/Scripts/python.exe に読み替えます。
既存の start.bat / run.py でも起動できます。static/index.html のローカルコピーは不要になりました。

## 検証の範囲

ローカル起動・HTTP配信・API入力検証・取得処理の回帰テストとサンプルUIのブラウザ確認を実施します。
Render上の実デプロイ・HTTPS URL・実店舗からの取得は、Renderアカウントを接続してから確認する必要があります。
