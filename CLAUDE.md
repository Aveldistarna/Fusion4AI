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
