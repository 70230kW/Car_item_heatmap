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
- トップ画面の「サンプルデータを表示」で3店舗が表示される。
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

## 複数店舗の取得と混雑時の挙動

画面からの取得は同時2店舗までで、3店舗目以降は「順番待ち」と表示します。
サーバーが503または429を返したときはRetry-Afterに従って自動再試行します。
1店舗あたりの混雑待ちは最大約3分・再試行24回までです（通信そのものにかかった時間は別）。
URL不正などの400系エラーは429を除き自動再試行しません。
サンプル表示へ切り替えた場合は、残りの店舗の取得・再試行を中止します。

UIの回帰テストはPlaywrightを導入した開発環境で、アプリを起動してから実行します。

    node test_ui_queue.cjs

Playwrightの既定のChromiumを使用します。独自のブラウザを使う場合はCHROMIUM_EXECUTABLE_PATH、
別の起動先を使う場合はBASE_URLで指定できます。テスト中の在庫APIは模擬応答で、実店舗には通信しません。

## カーセンサー形式と最大500ページ

- カーセンサー形式の車両カード（cassetteMain）、本体価格・支払総額、年式・走行距離、車両IDに対応しています。
- 検索結果のPNクエリ、index2.htmlなどのページ送りに対応します。
- 最大ページ数で100・200・300・500も選択できます。既定値は5ページのままです。
- 11ページ以上では /api/analyze-page を使って1ページずつ取得し、ページ間は1秒待機します。同時取得は2店舗までです。
- 取得済みデータは開いているブラウザのメモリで保持し、10ページごとに集計表示を更新します。後続ページで失敗した場合も、取得済みの結果と警告を表示します。
- 画面を閉じたり再読み込みしたりすると取得結果は失われます。500ページはページ間の待機だけで約8分以上かかります。
- 同じページや新規車両のないページを検出すると終了します。カーセンサーの車両IDが同じ場合は重複集計しません。
- APIを直接呼ぶ場合もmax_pagesは500まで指定できますが、長時間の単一リクエストはホスト側のタイムアウトを受ける可能性があります。大量取得には画面からの段階取得を使ってください。

カーセンサー実サイトへの接続は開発環境のネットワーク制限で拒否されたため、現時点の検証は合成HTMLと模擬APIによるものです。
実際のURLごとのHTML差異、取得拒否、利用規約・robots.txtによる制約には、実サイトでの追加確認が必要です。アクセス制限を回避する機能はありません。

追加した抽出テスト:

    python -m unittest -v test_carsensor test_web

ブラウザ回帰テストには、500ページ分の模擬取得と、途中失敗時の部分結果保持も含まれます。


年式ラベルの重なりとドット／ぼかし切替のブラウザ回帰テスト:

    node test_ui_charts.cjs

1990〜2026年の広い年式範囲で、PC・スマートフォンの目盛りと各表示方法を確認します。Playwrightの準備と起動先の指定はtest_ui_queue.cjsと同じです。

横スクロール・自社固定・取得完了時のメニュー自動収納のブラウザ回帰テスト:

    node test_ui_layout.cjs

全店舗の取得終了まで自動収納せず、グラフを表示できた場合にだけ収納します。入力欄はレールのボタンから再び開けます。
画面幅600px以下では、自社パネルが他社を覆わないよう固定を解除して横スクロール表示します。


重ね合わせ比較のブラウザ回帰テスト:

    node test_ui_overlay.cjs

会社ごとの色・形・ホバー情報、会社リストでのON/OFF、年式／走行距離、スマートフォン表示と店舗別表示への復帰を確認します。

登録店舗のブラウザ回帰テスト:

    node test_ui_saved_stores.cjs

登録・重複防止・再読み込み後の保持・自社と他社への呼び出し・削除・URL検証・保存容量エラーを確認します。
サーバーやデータベースへの追加設定は不要です。

## 非公開Googleスプレッドシート

Google接続を利用する場合は、[GOOGLE_SHEETS.md](GOOGLE_SHEETS.md)のOAuth設定を行い、RenderのEnvironmentにGOOGLE_CLIENT_ID・GOOGLE_CLIENT_SECRET・GOOGLE_REDIRECT_URIを設定してください。設定しなくても、既存のスクレイピング・サンプル表示は利用できます。OAuthトークンはメモリ内で管理するため、ワーカーは1のままにします。実シート接続は設定後の確認が必要です。
