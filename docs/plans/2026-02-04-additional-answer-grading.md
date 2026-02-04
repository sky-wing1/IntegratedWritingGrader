# 追加答案モード専用採点機能 実装計画

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 追加答案モードで採点ボタンを押したら、追加答案のみを採点し、通常答案と混在しないようにする

**Architecture:** `GradingWorker`に画像ファイルリストを外部から指定可能にし、`MainWindow`で追加答案モード判定を行い適切な画像パスを渡す

**Tech Stack:** Python, PyQt6, Claude Code CLI

---

## Task 1: GradingWorkerに画像リスト指定機能を追加

**Files:**
- Modify: `app/workers/grading_worker.py:102-166`

**Step 1: GradingWorker.__init__に画像リストパラメータを追加**

`app/workers/grading_worker.py`の`__init__`メソッドを修正:

```python
class GradingWorker(QThread):
    """Claude Code CLIで採点を行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    result_ready = pyqtSignal(int, dict)  # page_number, result
    finished = pyqtSignal(list)  # all results
    error = pyqtSignal(str)

    def __init__(self, pdf_path: str, image_files: list[Path] | None = None, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._image_files = image_files  # 外部から指定された画像リスト
        self._is_cancelled = False
        self._results: list[dict] = []
        self._criteria: GradingCriteria = _default_criteria()
```

**Step 2: GradingWorker.runで画像リストを優先使用**

`run`メソッドの画像取得部分を修正（137-145行目付近）:

```python
    def run(self):
        """採点実行（一括処理）"""
        try:
            # プロンプト読み込み
            current = Config.get_current_week()
            if not current:
                raise RuntimeError("週が選択されていません")

            week_path = Config.get_week_path(current["term"], current["week"])
            prompt_file = week_path / "prompt.txt"

            if not prompt_file.exists():
                raise RuntimeError(f"プロンプトファイルが見つかりません: {prompt_file}")

            with open(prompt_file, "r", encoding="utf-8") as f:
                base_prompt = f.read()

            # 採点基準をパース
            self._criteria = parse_criteria_from_prompt(prompt_file)

            # 画像ファイルを取得（外部指定があればそれを使用）
            if self._image_files is not None:
                image_files = self._image_files
            else:
                # 従来の動作: cropped ディレクトリから取得
                cropped_dir = Config.get_work_dir()
                if cropped_dir.exists():
                    image_files = sorted(cropped_dir.glob("*.png"))
                else:
                    image_files = []

            if not image_files:
                raise RuntimeError("採点対象の画像が見つかりません。")

            total = len(image_files)
            self.progress.emit(0, total, f"{total}件の答案を一括採点中...")

            if self._is_cancelled:
                return

            # 一括採点
            self._results = self._grade_batch_with_cli(base_prompt, image_files)

            # 結果を通知
            for i, result in enumerate(self._results):
                self.result_ready.emit(i + 1, result)

            self.progress.emit(total, total, "完了")

            if not self._is_cancelled:
                self.finished.emit(self._results)

        except Exception as e:
            self.error.emit(str(e))
```

**Step 3: 変更を確認**

```bash
cd /Users/Tsubasa/Developer/IntegratedWritingGrader
python -c "from app.workers.grading_worker import GradingWorker; print('Import OK')"
```

Expected: `Import OK`

**Step 4: コミット**

```bash
git add app/workers/grading_worker.py
git commit -m "feat: GradingWorkerに画像リスト指定機能を追加"
```

---

## Task 2: MainWindowで追加答案モード判定と画像パス指定

**Files:**
- Modify: `app/main_window.py:342-356`

**Step 1: _on_grading_startedで追加答案モード判定を追加**

```python
    def _on_grading_started(self, method: str):
        """採点開始（パネルから）"""
        if method == "cli":
            # 追加答案モードの場合
            if self.integrated_panel.is_additional_mode():
                additional_dir = self.integrated_panel.get_additional_dir()
                if not additional_dir or not additional_dir.exists():
                    QMessageBox.warning(self, "採点", "追加答案フォルダが見つかりません")
                    self.integrated_panel.progress_panel.stop_grading()
                    return

                # 追加答案の画像ファイルを取得
                image_files = sorted(additional_dir.glob("*.png"))
                if not image_files:
                    QMessageBox.warning(self, "採点", "追加答案の画像が見つかりません")
                    self.integrated_panel.progress_panel.stop_grading()
                    return

                # 追加答案専用のワーカーを開始
                self._grading_worker = GradingWorker(
                    pdf_path="",  # 追加答案モードではPDFパス不要
                    image_files=image_files
                )
            else:
                # 通常モード
                if not self._current_pdf_path:
                    QMessageBox.warning(self, "採点", "まずPDFを読み込んでください")
                    self.integrated_panel.progress_panel.stop_grading()
                    return

                self._grading_worker = GradingWorker(self._current_pdf_path)

            # 共通のシグナル接続
            self._grading_worker.progress.connect(self._on_grading_progress)
            self._grading_worker.result_ready.connect(self._on_result_ready)
            self._grading_worker.finished.connect(self._on_grading_finished)
            self._grading_worker.error.connect(self._on_grading_error)
            self._grading_worker.start()
```

**Step 2: 変更を確認**

```bash
cd /Users/Tsubasa/Developer/IntegratedWritingGrader
python -c "from app.main_window import MainWindow; print('Import OK')"
```

Expected: `Import OK`

**Step 3: コミット**

```bash
git add app/main_window.py
git commit -m "feat: 追加答案モード時は追加答案のみを採点"
```

---

## Task 3: 追加答案の採点結果保存対応

**Files:**
- Modify: `app/main_window.py:450-467`

**Step 1: _on_save_requestedで追加答案モード対応**

```python
    def _on_save_requested(self):
        """採点結果の保存リクエスト"""
        results = self.integrated_panel.get_results()
        if not results:
            self.statusbar.showMessage("保存する採点結果がありません")
            return

        current = Config.get_current_week()
        if not current:
            self.statusbar.showMessage("週が選択されていません")
            return

        try:
            # 追加答案モードの場合は additional_results.json に保存
            if self.integrated_panel.is_additional_mode():
                additional_dir = self.integrated_panel.get_additional_dir()
                if additional_dir:
                    import json
                    saved_path = additional_dir / "additional_results.json"
                    with open(saved_path, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    self.integrated_panel.progress_panel.set_saved(str(saved_path))
                    self.statusbar.showMessage(f"追加答案の採点結果を保存: {saved_path}")
                else:
                    self.statusbar.showMessage("追加答案フォルダが見つかりません")
            else:
                # 通常モード
                saved_path = Config.save_results(results)
                self.integrated_panel.progress_panel.set_saved(str(saved_path))
                self.statusbar.showMessage(f"保存完了: {saved_path}")
        except Exception as e:
            self.statusbar.showMessage(f"保存エラー: {e}")
```

**Step 2: 変更を確認**

```bash
cd /Users/Tsubasa/Developer/IntegratedWritingGrader
python -c "from app.main_window import MainWindow; print('Import OK')"
```

Expected: `Import OK`

**Step 3: コミット**

```bash
git add app/main_window.py
git commit -m "feat: 追加答案の採点結果をadditional_results.jsonに保存"
```

---

## Task 4: 動作確認

**Step 1: アプリケーション起動確認**

```bash
cd /Users/Tsubasa/Developer/IntegratedWritingGrader
python -m app.main
```

Expected: アプリケーションが正常に起動する

**Step 2: 手動テスト**

1. 通常のPDFを読み込み、採点ボタンを押す → 通常通り動作することを確認
2. 追加答案モードに入り、採点ボタンを押す → 追加答案のみが採点されることを確認
3. 追加答案の採点結果を保存 → `additional_results.json`に保存されることを確認

**Step 3: 最終コミット**

```bash
git add -A
git commit -m "feat: 追加答案モード専用採点機能を実装

- GradingWorkerに画像リスト指定機能を追加
- 追加答案モード時は追加答案のみを採点
- 採点結果をadditional_results.jsonに保存"
```

---

## 完了チェックリスト

- [ ] GradingWorkerが外部から画像リストを受け取れる
- [ ] 追加答案モードで採点ボタンを押すと追加答案のみ採点される
- [ ] 通常モードは既存動作を維持
- [ ] 追加答案の採点結果は`additional_results.json`に保存される
- [ ] アプリケーションが正常に起動・動作する
