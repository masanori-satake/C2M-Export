# タスク: キャッシュディレクトリの git 管理対象外化

## タスク一覧

- [x] 1. 現在の git 追跡状態を確認し、コミット済みキャッシュファイルがないことを確認する
- [x] 2. `.gitignore` に `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/` を追加する
- [x] 3. `git check-ignore` で変更内容を確認し、キャッシュが ignored 扱いになっていることを検証する
