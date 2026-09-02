# Fusion4AI

AI-driven CAD modeling MCP server for Autodesk Fusion.

## 造形作業のルール

### 人間との共同作業を前提にする
- AIだけで完結しようとしない。人間の目と判断を積極的に活用する
- 操作の節目でスクリーンショットを撮り、ユーザーに確認を求める
- 形状が期待と異なる場合、新規デザインでやり直す前に必ずユーザーに見せる
- ユーザーが「やり直して」と言うまでは、undoと修正で対応を試みる
- 迷ったら `get_selection` でユーザーに「どこを指していますか？」と聞く

### 操作の検証
- 各操作後に volume_delta と face_count を確認する
- delta=0 の場合は操作が効いていないので、原因を調べてからやり直す
- 複数の操作をバッチ実行する場合も、各ステップの結果を検証する

### デザインスクリプトのセルフレビュー
- YAMLを書いたら、実行前に自分で読み返して設計根拠を確認する
- 各寸法にコメントで計算根拠を書く（例: `size: [9.26, 49]  # 54-5=49`）
- 位置参照（top, bottom等）が意図通りか確認する
- パターン（corners等）の間隔が図面と一致するか確認する
- 不安な寸法があればユーザーに確認してから実行する

### CSGアプローチ
- 複雑な形状は単純な形状の足し算（union）と引き算（subtract）で構築する
- 穴あけは `create_cylinder(boolean="subtract", target="...")` の1ステップで行う
- 角の面取りは `add_fillet(edges="vertical")` で垂直エッジだけを対象にする
- 斜面のカットは `cut_by_plane(point, normal)` を使う

### 意図コンテキストの埋め込み（空間＝コンテキスト）
- デザインドキュメント自体が世界モデル。意図はFusion Attributes（グループ `fusion4ai`）として実体に埋め込まれ、セッションを跨いで永続する
- 理由は三つに分けて記録する。別々に欠落するし、別々の問いに答えるため
  - `intent` — なぜ**存在する**のか
  - `placement` — なぜ**そこにある**のか（関係と、動かしたら壊れるものを書く）
  - `dimensions` — なぜ**その寸法**なのか（`49 = 54 - 5` の計算根拠。コメントではなく属性に入れれば残る）
- 書けたかどうかのテスト: **その部品が動いたとき、あなたの文は「何かが壊れた」と明かすか？** 明かさないならラベルであって知覚ではない
- 位置や寸法が他のボディに依存する場合は `depends_on` も渡す

### 約束は機械に見張らせる（散文は腐る、検査されるルールは腐らない）
- 「Coverと3mm空ける」と散文で書いても、次の移動で嘘になり誰も気づかない。不変量は `constraints` に**文法で**書く
  - `clearance >= 3mm to Cover` / `inside Housing` / `flush Base top`
  - `aligned Bracket x` / `symmetric_to Leg_L about YZ` / `concentric_with Shaft z`
- 文法外の文（「工具なしで外せること」など）は保存され `unchecked` として報告される。**「違反ゼロ」が「何も見ていない」を意味しないため**。表現できない不変量は散文で残してよい
- `move_body` / `rotate_body` の応答には `constraint_review` が自動で付く。動かした本人の制約と、**そのボディを参照している他の制約**の両方が再検査される
- パーツを完成とする前に `review_geometry` を回す。Fusionはモデルが妥当かは見るが、設計者の約束が守られているかは見ない
- 既存デザインで作業を再開したら、まず `get_design_context` で過去の意図を回収する
- 自分が作っていないオブジェクトを変更・削除する前に、必ず `get_intent` で意図と依存を確認する
- 削除や大きな変更の前は `find_dependents` で影響範囲を確認する（`safe_to_modify` を見る）
- ユーザーがGUIで編集した形跡があれば `check_context_integrity` で参照切れと孤児意図を検出し、`set_intent` で修復する
- フィレットやブーリアンは面・エッジを消費するが、そこに付けた意図は消えず「孤児」として残る（Fusionの仕様上、属性は自動削除されない）。`orphaned_intent` に出たら、生きている実体へ `set_intent` で貼り直すか、不要なら `purge_orphans=True` で消す
- 全造形操作の履歴（provenance）は自動記録される。手動で書くのは「意図」だけでよい

### 部位（モジュール）— どのボディが一つの部品か
- タイムラインは「いつ作ったか」、モジュールは「どれが一つの部品か」。別の軸なので両方要る。`set_checkpoint("before Leg_R")` を打っても、**Leg_R を構成するボディがどれかは記録されない**
- 部品に取りかかる前に `set_module(name, bodies=[...], intent=...)` で束ねる
- 可能なら `area`（占有してよい直方体）も与える。**箱を動かすのは無料、30個のボディを動かすのは高い**ので、作る前に区画を引く
- `review_modules` で区画からはみ出した部品を検出する。区画のない部品は「合格」ではなく `unbudgeted`（何も検査していない）として報告される
- 部位ごと動かすのは `move_module`（剛体移動。内部の配置が崩れない。区画も一緒に動く）
- `list_modules` の `unassigned_bodies` は、どの部品にも属さないボディ

### 記録の抜けを見る
- `what_is_not_recorded` は**不在だけ**を名前で返す。他のツールは「記録されている中身」を運ぶので、記録の無いボディを探すには全体を読む羽目になる。これはその逆
- 部品を完成とする前に一度、記録を書き終えたと思ったらもう一度回す

### チェックポイントとパーツ単位のやり直し
- 新しいパーツ（部位）に取りかかる前に `set_checkpoint` を打つ（例: `before Leg_R`）
- タイムラインは構造化された作業ログ。「どこまで作ったか」はスクリーンショットではなく `get_timeline` で把握する（各項目にラベルと意図が付く）
- パーツが失敗したら、新しいパーツを作り直すのではなく `rollback_to_checkpoint` でそのパーツだけを巻き戻す
- `rollback_to_checkpoint` は破壊的（タイムライン項目を完全削除）。このセッションで作っていないものを消す場合はユーザーに確認する
- `session/undo` はタイムラインマーカーのロールバック（一時的）、`rollback_to_checkpoint` は削除（恒久的）。用途を混同しない

### 寸法の扱い
- AIが「知っている」寸法でも、精度に自信がない場合はユーザーに確認する
- 図面やデータシートが提供されている場合は、そこから正確な値を読み取る
- 単位はすべてmm

## 開発ルール

### アーキテクチャ
- MCP Server (TypeScript, stdio) <-> Fusion Add-in (Python, localhost:7432)
- ツール追加: src/tools/xxx.ts + fusion_addin/handlers/xxx.py
- Python側の変更は `fusion_reload` で反映（Fusion4AI.py自体の変更はAdd-in再起動が必要）

### Python側の注意
- Fusion APIはメインスレッド専用。全ハンドラはCustomEvent経由で実行される
- FeatureOperations enum の JoinFeatureOperation は値が0（falsy）。`op is None` で判定すること
- 各API呼び出しのタイムラインエントリは自動的にグループ化される
