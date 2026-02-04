"""メインウィンドウ"""

from __future__ import annotations
import json
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QListWidget, QListWidgetItem,
    QLabel, QStatusBar, QMessageBox,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction

from app.widgets.pdf_loader_panel import PdfLoaderPanel
from app.widgets.integrated_grading_panel import IntegratedGradingPanel
from app.widgets.export_panel import ExportPanel
from app.widgets.roster_panel import RosterPanel
from app.widgets.worksheet_panel import WorksheetPanel
from app.widgets.week_manager_panel import WeekManagerPanel
from app.widgets.stamp_panel import StampPanel
from app.widgets.batch_panel import BatchPanel
from app.workers.pipeline_worker import PipelineWorker
from app.workers.grading_worker import GradingWorker, load_results_from_json
from app.utils.config import Config
from app.utils.criteria_parser import parse_criteria_from_prompt, GradingCriteria, _default_criteria
from app.utils.additional_answer_manager import AdditionalAnswerItem
from app import __version__


class MainWindow(QMainWindow):
    """メインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IntegratedWritingGrader")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # 設定初期化
        Config.ensure_dirs()

        # ワーカー
        self._pipeline_worker: PipelineWorker | None = None
        self._grading_worker: GradingWorker | None = None
        self._current_pdf_path: str | None = None
        self._current_criteria: GradingCriteria = _default_criteria()
        self._detected_info: dict = {}

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

    def _setup_ui(self):
        """UIセットアップ"""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # サイドバー
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar)

        # メインコンテンツ
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack, 1)

        # 各ページ追加
        self._add_pages()

    def _create_sidebar(self) -> QWidget:
        """サイドバー作成"""
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #f7f6f3;
                border-right: 1px solid #e0e0e0;
            }
            QListWidget {
                background-color: transparent;
                border: none;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 12px 16px;
                border-radius: 6px;
                margin: 2px 8px;
            }
            QListWidget::item:selected {
                background-color: #e8e7e4;
                color: #37352f;
            }
            QListWidget::item:hover:!selected {
                background-color: #eeeeec;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)

        # タイトル
        title = QLabel("英作文採点")
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #37352f;
            padding: 8px 16px;
        """)
        layout.addWidget(title)

        # ナビゲーション
        self.nav_list = QListWidget()
        self.nav_list.setIconSize(QSize(20, 20))

        nav_items = [
            ("PDF読み込み", "QRコードから自動判定"),
            ("採点・編集", "AI採点の実行と編集"),
            ("出力", "PDF出力"),
            ("一括処理", "複数PDFをまとめて処理"),
            ("名簿管理", "クラス名簿の管理"),
            ("添削用紙", "添削用紙の生成"),
            ("週管理", "週の追加と編集"),
            ("スタンプ", "評価スタンプの管理"),
        ]

        for name, tooltip in nav_items:
            item = QListWidgetItem(name)
            item.setToolTip(tooltip)
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        layout.addWidget(self.nav_list)
        layout.addStretch()

        # バージョン
        version = QLabel(f"v{__version__}")
        version.setStyleSheet("color: #9b9a97; font-size: 11px; padding: 8px 16px;")
        layout.addWidget(version)

        return sidebar

    def _add_pages(self):
        """ページ追加"""
        # PDF読み込みページ（QRコードから自動判定）
        self.pdf_loader = PdfLoaderPanel()
        self.pdf_loader.pdf_loaded.connect(self._on_pdf_loaded_with_info)
        self.pdf_loader.additional_grading_requested.connect(self._on_additional_grading_requested)
        self.content_stack.addWidget(self.pdf_loader)

        # 採点・編集ページ（統合パネル）
        self.integrated_panel = IntegratedGradingPanel()
        self.integrated_panel.result_updated.connect(self._on_result_updated)
        self.integrated_panel.progress_panel.grading_started.connect(self._on_grading_started)
        self.integrated_panel.progress_panel.grading_stopped.connect(self._on_grading_stopped)
        self.integrated_panel.progress_panel.json_imported.connect(self._on_json_imported)
        self.integrated_panel.progress_panel.save_requested.connect(self._on_save_requested)
        self.integrated_panel.progress_panel.load_saved_requested.connect(self._on_load_saved_requested)
        self.content_stack.addWidget(self.integrated_panel)

        # 出力ページ
        self.export_panel = ExportPanel()
        self.export_panel.export_complete.connect(self._on_export_complete)
        self.content_stack.addWidget(self.export_panel)

        # 一括処理ページ
        self.batch_panel = BatchPanel()
        self.batch_panel.batch_finished.connect(self._on_batch_finished)
        self.content_stack.addWidget(self.batch_panel)

        # 名簿管理ページ
        self.roster_panel = RosterPanel()
        self.roster_panel.roster_loaded.connect(self._on_roster_loaded)
        self.content_stack.addWidget(self.roster_panel)

        # 添削用紙生成ページ
        self.worksheet_panel = WorksheetPanel()
        self.content_stack.addWidget(self.worksheet_panel)

        # 週管理ページ
        self.week_manager_panel = WeekManagerPanel()
        self.week_manager_panel.week_updated.connect(self._on_week_updated)
        self.content_stack.addWidget(self.week_manager_panel)

        # スタンプ管理ページ
        self.stamp_panel = StampPanel()
        self.content_stack.addWidget(self.stamp_panel)

    def _on_roster_loaded(self, roster):
        """名簿読み込み完了"""
        self.worksheet_panel.set_roster(roster)
        self.statusbar.showMessage(
            f"名簿読み込み完了: {roster.year} {roster.class_name} ({len(roster.students)}名)"
        )

    def _on_week_updated(self):
        """週が更新された"""
        self.statusbar.showMessage("週を更新しました")

    def _on_batch_finished(self, all_results: list):
        """一括処理完了"""
        self.statusbar.showMessage(f"一括処理完了: {len(all_results)} ファイル")

    def _setup_menu(self):
        """メニューバー設定"""
        menubar = self.menuBar()

        # ファイルメニュー
        file_menu = menubar.addMenu("ファイル")

        open_action = QAction("PDFを開く...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_pdf)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_action = QAction("採点済みPDFを出力...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        # 採点メニュー
        grade_menu = menubar.addMenu("採点")

        run_action = QAction("AI採点を実行", self)
        run_action.setShortcut("Ctrl+R")
        run_action.triggered.connect(self._on_run_grading)
        grade_menu.addAction(run_action)

    def _setup_statusbar(self):
        """ステータスバー設定"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("準備完了")

    def _on_nav_changed(self, index: int):
        """ナビゲーション変更"""
        self.content_stack.setCurrentIndex(index)

    def _on_pdf_loaded_with_info(self, pdf_path: str, detected_info: dict):
        """PDF読み込み完了（QRコード情報付き）"""
        self._current_pdf_path = pdf_path
        self._detected_info = detected_info

        # 検出された情報をステータスバーに表示
        year = detected_info.get("year", "?")
        term = detected_info.get("term", "?")
        week = detected_info.get("week", "?")
        class_name = detected_info.get("class_name", "?")
        self.statusbar.showMessage(
            f"PDF読み込み完了: {year}年度 高2英語{class_name} {term} 第{week}週"
        )

        # 採点基準を読み込み
        self._load_criteria()

        # パネルに反映（cropped画像を読み込み）
        try:
            cropped_dir = Config.get_cropped_dir()
            self.integrated_panel.load_cropped_images(cropped_dir)
        except RuntimeError:
            # フォールバック: PDFを直接読み込み
            self.integrated_panel.load_pdf(pdf_path)
        self.integrated_panel.set_criteria(self._current_criteria)
        self.export_panel.set_criteria(self._current_criteria)

        # 既存の採点結果があれば読み込む
        self._load_existing_results()

        # 採点・編集ページに移動
        self.nav_list.setCurrentRow(1)

    def _on_pdf_loaded(self, pdf_path: str):
        """PDF読み込み完了（後方互換性用）"""
        self._on_pdf_loaded_with_info(pdf_path, {})

    def _load_existing_results(self):
        """既存の採点結果を読み込み"""
        if Config.has_saved_results():
            results = Config.load_results()
            if results:
                self.integrated_panel.set_results(results)
                self.integrated_panel.progress_panel.set_complete()
                self.integrated_panel.progress_panel.save_btn.setEnabled(True)

                # 出力パネルにもデータをセット
                if self._current_pdf_path:
                    self.export_panel.set_data(self._current_pdf_path, results)

                self.statusbar.showMessage(f"保存済みの採点結果を読み込みました: {len(results)} 件")

    def _load_criteria(self):
        """採点基準を読み込み"""
        current = Config.get_current_week()
        if not current:
            self._current_criteria = _default_criteria()
            return

        week_path = Config.get_week_path(current["term"], current["week"])
        prompt_file = week_path / "prompt.txt"

        if prompt_file.exists():
            self._current_criteria = parse_criteria_from_prompt(prompt_file)
            self.statusbar.showMessage(
                f"採点基準読み込み: {len(self._current_criteria.criteria)}項目"
            )
        else:
            self._current_criteria = _default_criteria()

    def _on_open_pdf(self):
        """PDFを開く"""
        self.nav_list.setCurrentRow(0)
        self.pdf_loader.open_pdf_dialog()

    def _on_export(self):
        """PDF出力"""
        results = self.integrated_panel.get_results()
        if not results:
            QMessageBox.warning(self, "出力", "採点結果がありません")
            return

        # 出力パネルにデータをセット
        if self._current_pdf_path:
            self.export_panel.set_data(self._current_pdf_path, results)

        self.nav_list.setCurrentRow(2)  # 出力タブ（index 2）

    def _on_run_grading(self):
        """AI採点実行（メニューから）"""
        if not self._current_pdf_path:
            QMessageBox.warning(self, "採点", "まずPDFを読み込んでください")
            return

        self.nav_list.setCurrentRow(1)
        self.integrated_panel.progress_panel.start_grading()

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

    def _on_grading_stopped(self):
        """採点停止"""
        if self._grading_worker and self._grading_worker.isRunning():
            self._grading_worker.cancel()
            self.statusbar.showMessage("採点を停止しました")

    def _on_json_imported(self, json_path: str):
        """JSONインポート"""
        try:
            results = load_results_from_json(json_path)
            self.integrated_panel.set_results(results)
            self.integrated_panel.progress_panel.set_complete()

            # 出力パネルにもデータをセット
            if self._current_pdf_path:
                self.export_panel.set_data(self._current_pdf_path, results)

            self.statusbar.showMessage(f"JSONインポート完了: {len(results)} 件")
        except Exception as e:
            self.integrated_panel.progress_panel.set_error(str(e))
            QMessageBox.critical(self, "インポートエラー", str(e))

    def _on_grading_progress(self, current: int, total: int, message: str):
        """採点進捗"""
        self.integrated_panel.progress_panel.update_progress(current, total, message)
        self.statusbar.showMessage(message)

    def _on_result_ready(self, page_num: int, result: dict):
        """採点結果準備完了"""
        self.statusbar.showMessage(f"ページ {page_num} の採点完了")

    def _on_grading_finished(self, results: list):
        """採点完了"""
        # エラー結果をチェック
        error_results = [r for r in results if r.get("error")]
        total_count = len(results)
        error_count = len(error_results)

        if error_count == total_count and total_count > 0:
            # すべてエラーの場合
            first_error = error_results[0].get("error", "不明なエラー")
            self.integrated_panel.progress_panel.set_error(first_error)
            self.statusbar.showMessage(f"採点失敗: {first_error}")
            QMessageBox.critical(self, "採点エラー", f"採点に失敗しました:\n{first_error}")
            return

        # 結果をセット（部分的成功でも表示）
        self.integrated_panel.set_results(results)

        # 出力パネルにもデータをセット
        if self._current_pdf_path:
            self.export_panel.set_data(self._current_pdf_path, results)

        if error_count > 0:
            # 一部エラーの場合は警告付きで完了
            self.integrated_panel.progress_panel.set_complete()
            self.statusbar.showMessage(f"採点完了（{error_count}件エラー）: {total_count} ページ")
            QMessageBox.warning(
                self, "一部エラー",
                f"{total_count}件中{error_count}件の採点でエラーが発生しました。\n"
                "詳細は各ページの結果を確認してください。"
            )
        else:
            # すべて成功
            self.integrated_panel.progress_panel.set_complete()
            self.statusbar.showMessage(f"採点完了: {total_count} ページ")
        # 既に統合パネルにいるのでページ遷移は不要

    def _on_grading_error(self, error: str):
        """採点エラー"""
        self.integrated_panel.progress_panel.set_error(error)
        self.statusbar.showMessage(f"エラー: {error}")
        QMessageBox.critical(self, "採点エラー", error)

    def _on_result_updated(self, page_num: int, data: dict):
        """採点結果更新（フィードバック編集後）"""
        # 出力パネルのデータも更新
        results = self.integrated_panel.get_results()
        if self._current_pdf_path and results:
            self.export_panel.set_data(self._current_pdf_path, results)

    def _on_export_complete(self, file_path: str):
        """PDF出力完了"""
        self.statusbar.showMessage(f"PDF出力完了: {file_path}")
        QMessageBox.information(self, "出力完了", f"PDFを出力しました:\n{file_path}")

        # Finderで保存フォルダを開く（ファイルを選択状態で）
        try:
            subprocess.run(["open", "-R", file_path], check=False)
        except Exception:
            pass  # 開けなくても無視

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

    def _on_load_saved_requested(self):
        """保存済み結果の読み込みリクエスト"""
        saved_weeks = Config.list_saved_weeks()
        if not saved_weeks:
            self.statusbar.showMessage("保存済みの採点結果がありません")
            return

        # 選択ダイアログを表示
        dialog = QDialog(self)
        dialog.setWindowTitle("保存済み結果を読み込み")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        label = QLabel("読み込む採点結果を選択してください:")
        layout.addWidget(label)

        list_widget = QListWidget()
        list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e8f4fc;
                color: #37352f;
            }
        """)

        for saved in saved_weeks:
            year = saved.get("year") or "----"
            term = saved.get("term") or ""
            week = saved.get("week") or 0
            class_name = saved.get("class_name") or ""

            if class_name:
                text = f"{year}年度 高2英語{class_name} {term} 第{week}週"
            else:
                text = f"{year}年度 {term} 第{week}週"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, saved)
            list_widget.addItem(item)

        list_widget.setCurrentRow(0)
        layout.addWidget(list_widget)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_item = list_widget.currentItem()
            if selected_item:
                saved = selected_item.data(Qt.ItemDataRole.UserRole)
                self._load_saved_results_from_week(saved)

    def _load_saved_results_from_week(self, saved: dict):
        """指定された週の保存済み結果を読み込み"""
        year = saved.get("year")
        term = saved.get("term")
        week = saved.get("week")
        class_name = saved.get("class_name")

        # 現在の週を設定
        Config.set_current_week(year, term, week, class_name)

        # 採点基準を読み込み
        self._load_criteria()

        # 採点結果を読み込み
        results = Config.load_results(year, term, week, class_name)
        if results:
            self.integrated_panel.set_results(results)
            self.integrated_panel.set_criteria(self._current_criteria)
            self.integrated_panel.progress_panel.set_complete()
            self.integrated_panel.progress_panel.save_btn.setEnabled(True)

            # 出力パネルにもデータをセット
            if self._current_pdf_path:
                self.export_panel.set_data(self._current_pdf_path, results)

            if class_name:
                self.statusbar.showMessage(
                    f"読み込み完了: {year}年度 高2英語{class_name} {term} 第{week}週 ({len(results)}件)"
                )
            else:
                self.statusbar.showMessage(
                    f"読み込み完了: {year}年度 {term} 第{week}週 ({len(results)}件)"
                )
        else:
            self.statusbar.showMessage("採点結果の読み込みに失敗しました")

    def _on_additional_grading_requested(self, items: list):
        """追加答案の採点リクエスト"""
        if not items:
            return

        # 最初のアイテムの週情報を使用
        first_item = items[0]

        # 現在の週情報を取得
        current = Config.get_current_week()
        if not current:
            QMessageBox.warning(self, "追加答案", "週が選択されていません")
            return

        year = current.get("year")
        target_dir = Config.get_data_dir(
            year=year,
            term=first_item.target_term,
            week=first_item.target_week,
            class_name=first_item.class_name
        )

        additional_dir = target_dir / "additional"

        if not additional_dir.exists():
            QMessageBox.warning(
                self, "追加答案",
                f"追加答案フォルダが見つかりません:\n{additional_dir}"
            )
            return

        # 週を一時的に切り替え
        Config.set_current_week(
            year=year,
            term=first_item.target_term,
            week=first_item.target_week,
            class_name=first_item.class_name
        )

        # 採点基準を読み込み
        self._load_criteria()

        # 追加答案モードで採点・編集パネルに遷移
        self.integrated_panel.set_criteria(self._current_criteria)
        self.integrated_panel.load_additional_answers(additional_dir, items)

        # ステータスバー更新
        self.statusbar.showMessage(
            f"追加答案モード: 第{first_item.target_week}週 ({len(items)}件)"
        )

        # 採点・編集ページに移動
        self.nav_list.setCurrentRow(1)
