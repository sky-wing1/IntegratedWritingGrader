# 追加答案モード（同週対応）Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PDF読み込み時に「追加答案として読み込む」チェックボックスを追加し、同じ週の追加提出答案を既存の答案を上書きせずに追加答案として処理できるようにする。

**Architecture:** PdfLoaderPanel にチェックボックスUIを追加し、ONの場合 PipelineWorker に `additional_mode=True` を渡す。PipelineWorker は全ページを `WeekNN/additional/` に保存し、既存の AdditionalAnswerManager 基盤を利用してメタデータを管理する。採点は既存の追加答案フロー（`MainWindow._on_additional_grading_requested`）に乗せる。

**Tech Stack:** Python 3.12, PyQt6, PyMuPDF (fitz)

---

### Task 1: PipelineWorker に additional_mode パラメータを追加

**Files:**
- Modify: `app/workers/pipeline_worker.py:25-30` (コンストラクタ)
- Modify: `app/workers/pipeline_worker.py:131-243` (_crop_answers メソッド)

**Step 1: コンストラクタに additional_mode パラメータを追加**

`app/workers/pipeline_worker.py` L25-30 を修正:

```python
def __init__(self, input_pdf: str, additional_mode: bool = False, parent=None):
    super().__init__(parent)
    self.input_pdf = input_pdf
    self.additional_mode = additional_mode
    self._is_cancelled = False
    self._students: List[StudentInfo] = []
    self._additional_items: List[AdditionalAnswerItem] = []
```

**Step 2: _crop_answers に additional_mode 分岐を追加**

`_crop_answers` メソッド内、L176-181 の `is_additional` 判定ロジックを修正:

```python
# 追加答案かどうかチェック
is_additional = False
if self.additional_mode:
    # 追加答案モード: 全ページを追加答案として扱う
    is_additional = True
elif student_info and current_week and current_term:
    if student_info.week != current_week or student_info.term != current_term:
        is_additional = True
```

**Step 3: additional_mode 時の保存先を修正**

追加答案モードでは、ページの QR コードの週情報をそのままターゲット週として使う。
`_crop_answers` L191-227 の追加答案保存ブロック内、`source_key` の決定ロジックを修正:

```python
if is_additional and student_info:
    if self.additional_mode:
        # 追加答案モード: QRコードの週 = ターゲット週 = 保存先週
        target_key = (student_info.term, student_info.week)
        save_term = student_info.term
        save_week = student_info.week
    else:
        # 通常モード（異なる週検出）: 検出元週に保存
        target_key = (current_term, current_week)
        save_term = current_term
        save_week = current_week

    if target_key not in additional_managers:
        save_dir = Config.get_data_dir(
            year=student_info.year,
            term=save_term,
            week=save_week,
            class_name=student_info.class_name
        )
        manager = AdditionalAnswerManager(save_dir)
        manager.detected_from_week = save_week
        additional_managers[target_key] = manager

    manager = additional_managers[target_key]

    # 既存ファイルと衝突しないようにファイル名を生成
    existing_files = list((manager.get_additional_dir()).glob("page_*.png")) if manager.get_additional_dir().exists() else []
    existing_nums = []
    for f in existing_files:
        try:
            num = int(f.stem.split("_")[1])
            existing_nums.append(num)
        except (IndexError, ValueError):
            pass
    next_num = max(existing_nums, default=0) + 1
    filename = f"page_{next_num + page_num:03d}.png"

    # ... 以下、既存の保存処理と同じ
```

ただし、ファイル名衝突を避けるためにもう少しシンプルに：追加答案モードでは元PDFのページ番号をそのまま使うが、既存の `additional/` にファイルがある場合はオフセットを付ける。

実際の実装は以下のようにする:

```python
if is_additional and student_info:
    if self.additional_mode:
        target_key = (student_info.term, student_info.week)
        save_term = student_info.term
        save_week = student_info.week
    else:
        target_key = (current_term, current_week)
        save_term = current_term
        save_week = current_week

    if target_key not in additional_managers:
        save_dir = Config.get_data_dir(
            year=student_info.year,
            term=save_term,
            week=save_week,
            class_name=student_info.class_name
        )
        manager = AdditionalAnswerManager(save_dir)
        manager.detected_from_week = save_week
        additional_managers[target_key] = manager

    manager = additional_managers[target_key]

    # 一時ファイルに保存してからコピー
    temp_path = self._temp_dir / filename
    pix.save(str(temp_path))
    # save_image は既存ファイルを上書きするので、ユニークなファイル名を生成
    actual_filename = self._unique_additional_filename(manager.get_additional_dir(), page_num + 1)
    manager.save_image(temp_path, actual_filename)

    item = AdditionalAnswerItem(
        filename=actual_filename,
        student_name=student_info.name,
        attendance_no=student_info.attendance_no,
        class_name=student_info.class_name,
        target_week=student_info.week,
        target_term=student_info.term,
        qr_data=f"{student_info.year}_{student_info.term}_{student_info.week}_{student_info.class_name}_{student_info.attendance_no}_{student_info.name}",
        original_page=page_num + 1,
    )
    manager.add_item(item)
    self._additional_items.append(item)
```

**Step 4: ユニークファイル名生成ヘルパーを追加**

`PipelineWorker` クラスに以下のメソッドを追加:

```python
def _unique_additional_filename(self, additional_dir: Path, page_num: int) -> str:
    """追加答案ディレクトリ内でユニークなファイル名を生成"""
    additional_dir.mkdir(parents=True, exist_ok=True)
    filename = f"page_{page_num:03d}.png"
    if not (additional_dir / filename).exists():
        return filename
    # 衝突する場合はサフィックスを追加
    counter = 1
    while True:
        filename = f"page_{page_num:03d}_{counter}.png"
        if not (additional_dir / filename).exists():
            return filename
        counter += 1
```

**Step 5: additional_mode 時は通常の cropped/ には保存しない**

`_crop_answers` の else ブロック（通常答案保存、L228-231）を確認。`additional_mode=True` かつ `is_additional=True` なら全ページが追加答案として処理されるので、else ブロックには到達しない。ただし、QRコードが読めなかった（`student_info` が None の）ページが残る可能性がある。そのケースでは通常通り cropped/ に保存するのが妥当。変更不要。

**Step 6: AdditionalAnswerManager.save_metadata を追記モードに対応**

`app/utils/additional_answer_manager.py` L88-103 の `save_metadata` を修正し、既存メタデータがある場合はアイテムを追記する:

```python
def save_metadata(self) -> Path:
    """メタデータを保存（既存がある場合は追記）"""
    additional_dir = self.get_additional_dir()
    additional_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = additional_dir / "metadata.json"

    # 既存メタデータがあれば読み込んで追記
    existing_items = []
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_items = existing.get("items", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # 既存アイテムのファイル名セットを作成（重複排除）
    existing_filenames = {item.get("filename") for item in existing_items}
    new_items = [
        item.to_dict() for item in self.items
        if item.filename not in existing_filenames
    ]

    all_items = existing_items + new_items

    metadata = {
        "detected_from_week": self.detected_from_week,
        "detected_at": (self.detected_at or datetime.now()).isoformat(),
        "items": all_items,
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return metadata_path
```

**Step 7: 動作確認**

Run: アプリをビルドせずにソースから起動して、追加答案モードで1枚のPDFを読み込み、`WeekNN/additional/` にファイルが保存されることを確認。

**Step 8: Commit**

```bash
git add app/workers/pipeline_worker.py app/utils/additional_answer_manager.py
git commit -m "feat: PipelineWorker に additional_mode を追加し同週追加答案をサポート"
```

---

### Task 2: PdfLoaderPanel にチェックボックスUIを追加

**Files:**
- Modify: `app/widgets/pdf_loader_panel.py:116-139` (_setup_ui)
- Modify: `app/widgets/pdf_loader_panel.py:291-321` (_on_file_selected, _start_processing)
- Modify: `app/widgets/pdf_loader_panel.py:350-405` (_on_finished)

**Step 1: QCheckBox のインポートを追加**

`app/widgets/pdf_loader_panel.py` L5-9 のインポートに `QCheckBox` を追加:

```python
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QMessageBox, QFrame, QGridLayout,
    QListWidget, QListWidgetItem, QCheckBox
)
```

**Step 2: ドロップエリアの下にチェックボックスを追加**

`_setup_ui` メソッド内、L138 の `layout.addWidget(self.drop_area)` の直後に:

```python
# 追加答案モードチェックボックス
self.additional_mode_cb = QCheckBox("追加答案として読み込む")
self.additional_mode_cb.setToolTip(
    "既に採点済みの週に、追加提出の答案を読み込む場合にチェックしてください。\n"
    "既存の採点結果を上書きせず、追加答案として処理します。"
)
self.additional_mode_cb.setStyleSheet("""
    QCheckBox {
        font-size: 13px;
        color: #37352f;
        padding: 4px 0;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
    }
""")
layout.addWidget(self.additional_mode_cb)
```

**Step 3: _start_processing で additional_mode を PipelineWorker に渡す**

`_start_processing` メソッド（L296-321）を修正:

```python
def _start_processing(self):
    """PDF処理開始"""
    if not self._current_pdf_path:
        return

    # UI更新
    self.drop_area.setVisible(False)
    self.additional_mode_cb.setVisible(False)  # 追加
    self.info_group.setVisible(False)
    self.prompt_group.setVisible(False)
    self.start_btn.setVisible(False)
    self.additional_group.setVisible(False)
    self.progress_group.setVisible(True)
    self.progress_bar.setValue(0)
    self.status_label.setText("処理開始...")

    # 追加答案リストをクリア
    self._additional_items = []

    # ワーカー開始（追加答案モードフラグを渡す）
    is_additional = self.additional_mode_cb.isChecked()
    self._pipeline_worker = PipelineWorker(
        self._current_pdf_path,
        additional_mode=is_additional
    )
    self._pipeline_worker.progress.connect(self._on_progress)
    self._pipeline_worker.students_found.connect(self._on_students_found)
    self._pipeline_worker.additional_answers_found.connect(self._on_additional_found)
    self._pipeline_worker.finished.connect(self._on_finished)
    self._pipeline_worker.error.connect(self._on_error)
    self._pipeline_worker.start()
```

**Step 4: _on_finished で追加答案モード時の処理を分岐**

`_on_finished` メソッド（L350-405）を修正。追加答案モードの場合は通常の採点画面遷移ではなく、追加答案の採点フローに乗せる:

```python
def _on_finished(self, pdf_path: str):
    """処理完了"""
    self._current_pdf_path = pdf_path

    self.progress_group.setVisible(False)
    self.drop_area.setVisible(True)
    self.additional_mode_cb.setVisible(True)  # 追加
    self.info_group.setVisible(True)

    # 検出情報を表示
    self.info_labels["file"].setText(Path(pdf_path).name)

    if self._detected_info:
        year = self._detected_info.get("year")
        term = self._detected_info.get("term")
        week = self._detected_info.get("week")
        class_name = self._detected_info.get("class_name")
        page_count = self._detected_info.get("page_count", 0)

        self.info_labels["year"].setText(
            f"{year}年度" if year else "未検出"
        )
        self.info_labels["term"].setText(term or "未検出")
        self.info_labels["week"].setText(
            f"第{week}週" if week else "未検出"
        )
        self.info_labels["class"].setText(
            f"高2英語{class_name}" if class_name else "未検出"
        )
        self.info_labels["pages"].setText(f"{page_count}ページ")

        # プロンプト読み込み
        self._load_prompt()
        self.prompt_group.setVisible(True)

        # 追加答案モードの場合
        if self.additional_mode_cb.isChecked() and self._additional_items:
            # 「採点画面へ進む」ボタンは非表示
            self.start_btn.setVisible(False)
            # 追加答案セクションを表示（自動選択済み）
            self._update_additional_list()
            self._select_all_additional()
            # チェックボックスをリセット
            self.additional_mode_cb.setChecked(False)

            QMessageBox.information(
                self,
                "追加答案として読み込み完了",
                f"{len(self._additional_items)} 件の答案を追加答案として読み込みました。\n"
                "「選択した答案を採点」ボタンで採点を開始できます。"
            )
        else:
            self.start_btn.setVisible(True)
    else:
        # QRコードが検出できなかった場合（既存ロジックそのまま）
        for key in ["year", "term", "week", "class", "pages"]:
            self.info_labels[key].setText("未検出")

        QMessageBox.warning(
            self, "QRコード未検出",
            "QRコードが検出できませんでした。\n"
            "手動で設定するか、PDFを確認してください。"
        )

    # 通常モード時の追加答案通知（異なる週検出）
    if not self.additional_mode_cb.isChecked() and self._additional_items:
        # 追加答案モードでない場合のみ通知
        count = len(self._additional_items)
        QMessageBox.information(
            self,
            "追加答案を検出",
            f"{count} 件の追加答案（異なる週の答案）を検出しました。\n\n"
            "「追加答案」セクションから採点できます。"
        )
```

**Step 5: reset メソッドにチェックボックスのリセットを追加**

`reset` メソッド（L440-456）に追加:

```python
def reset(self):
    """リセット"""
    self._current_pdf_path = None
    self._detected_info = {}
    self._additional_items = []

    self.drop_area.setVisible(True)
    self.additional_mode_cb.setVisible(True)  # 追加
    self.additional_mode_cb.setChecked(False)  # 追加
    self.info_group.setVisible(False)
    self.prompt_group.setVisible(False)
    self.progress_group.setVisible(False)
    self.start_btn.setVisible(False)
    self.additional_group.setVisible(False)

    for label in self.info_labels.values():
        label.setText("-")

    self.additional_list.clear()
```

**Step 6: _on_error でもチェックボックスを再表示**

`_on_error` メソッド（L407-412）に追加:

```python
def _on_error(self, error: str):
    """エラー"""
    self.progress_group.setVisible(False)
    self.drop_area.setVisible(True)
    self.additional_mode_cb.setVisible(True)  # 追加
    self.status_label.setText(f"エラー: {error}")
    QMessageBox.critical(self, "処理エラー", error)
```

**Step 7: Commit**

```bash
git add app/widgets/pdf_loader_panel.py
git commit -m "feat: PDF読み込みパネルに追加答案モードチェックボックスを追加"
```

---

### Task 3: PipelineWorker の additional_mode 時に Config.set_current_week を適切に設定

**Files:**
- Modify: `app/workers/pipeline_worker.py:245-270` (_parse_qr_codes)

**Step 1: additional_mode 時の週設定ロジックを修正**

`_parse_qr_codes` メソッドで、`additional_mode=True` の場合も `Config.set_current_week()` を呼ぶ必要がある（追加答案の保存先ディレクトリを正しく解決するため）。ただし、追加答案モードでは全ページが追加答案として扱われるので、最多数の週がターゲット週になる。現在の実装で問題なし。

ただし、`_crop_answers` 内で `current_week` / `current_term` を取得した後に追加答案モード判定が行われるため、`additional_mode` では `current_week` と実際のQRコードの週が同じになる。この場合、通常の `is_additional` 判定（`student_info.week != current_week`）では False になってしまう。

**これが核心的な修正ポイント**: Task 1 の Step 2 で既に対応済み。`self.additional_mode` が True なら無条件で `is_additional = True` にしている。

追加変更は不要。Task 1 の実装で完結。

---

### Task 4: 統合テスト・動作確認

**Step 1: アプリをソースから起動して確認**

```bash
cd /Users/Tsubasa/Developer/IntegratedWritingGrader
/Users/Tsubasa/.pyenv/versions/3.12.9/bin/python -m app.main
```

**Step 2: 通常モードの動作確認**

1. チェックボックスが表示されていることを確認
2. チェックを外したまま（デフォルト）でPDFをドロップ
3. 従来通りの動作であることを確認（回帰テスト）

**Step 3: 追加答案モードの動作確認**

1. 既に採点済みの週の追加答案1枚をスキャンしたPDFを用意
2. 「追加答案として読み込む」にチェック
3. PDFをドロップ
4. 確認事項:
   - `WeekNN/additional/` にクロップ画像が保存されること
   - `WeekNN/additional/metadata.json` にアイテム情報が追記されること
   - `WeekNN/cropped/` の既存画像が上書きされないこと
   - 追加答案セクションに答案が表示されること
   - 「選択した答案を採点」ボタンが機能すること

**Step 4: Commit（最終確認後）**

ここまでの変更に問題なければ最終コミット不要（Task 1, 2 で既にコミット済み）。

---

### Task 5: ビルド・リリース

**Step 1: バージョンバンプ**

`app/__init__.py` のバージョンを更新。

**Step 2: py2app ビルド**

```bash
cd /Users/Tsubasa/Developer/IntegratedWritingGrader
/Users/Tsubasa/.pyenv/versions/3.12.9/bin/python setup.py py2app
```

**Step 3: /Applications にデプロイ**

```bash
cp -R dist/IntegratedWritingGrader.app /Applications/
```

**Step 4: スモークテスト**

ビルドしたアプリで通常モード・追加答案モードの両方をテスト。
