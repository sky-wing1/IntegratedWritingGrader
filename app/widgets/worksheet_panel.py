"""添削用紙出力パネル"""

from __future__ import annotations
import logging
import subprocess
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton, QFileDialog,
    QComboBox, QProgressBar, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread

from app.utils.roster_manager import ClassRoster, generate_meibo_tex
from app.utils.config import Config


class LatexCompileWorker(QThread):
    """LaTeXコンパイルワーカー"""

    progress = pyqtSignal(str)  # ステータスメッセージ
    finished = pyqtSignal(str)  # 出力PDFパス
    error = pyqtSignal(str)

    def __init__(
        self,
        template_dir: Path,
        term: str,
        week: int,
        class_code: str,
        roster: ClassRoster,
        parent=None
    ):
        super().__init__(parent)
        self.template_dir = template_dir
        self.term = term
        self.week = week
        self.class_code = class_code
        self.roster = roster

    def run(self):
        """コンパイル実行"""
        try:
            import re

            # Step 1: 名簿.tex を生成
            self.progress.emit("名簿ファイルを生成中...")
            meibo_path = self.template_dir / "名簿.tex"
            generate_meibo_tex(self.roster, meibo_path)

            # Step 1.5: problem.tex を準備（なければダミーを生成）
            self.progress.emit("問題ファイルを準備中...")
            self._prepare_problem_tex()

            # Step 2: ベーステンプレートの学期・週を更新
            self.progress.emit("テンプレートを準備中...")
            base_tex = self.template_dir / "高２Integrated Writing 添削用紙.tex"

            if not base_tex.exists():
                raise FileNotFoundError(f"ベーステンプレートが見つかりません: {base_tex}")

            # 元のファイルをバックアップ
            base_tex_backup = self.template_dir / "高２Integrated Writing 添削用紙.tex.bak"
            shutil.copy(base_tex, base_tex_backup)

            try:
                # テンプレートを読み込んで学期・週を置換
                with open(base_tex, "r", encoding="utf-8") as f:
                    content = f.read()

                # \def\学期{...} と \def\週番号{...} を置換
                content = re.sub(
                    r'\\def\\学期\{[^}]*\}',
                    r'\\def\\学期{' + self.term + r'}',
                    content
                )
                content = re.sub(
                    r'\\def\\週番号\{[^}]*\}',
                    r'\\def\\週番号{' + f'{self.week:02d}' + r'}',
                    content
                )

                # 週別問題のパスを正しいパス（絶対パス）に書き換え
                # 元: \input{../週別問題/\学期/第\週番号 週/problem.tex}
                # 新: \input{/Users/.../weeks/後期/第14週/problem.tex}
                problem_path = Config.WEEKS_PATH / self.term / f"第{self.week:02d}週" / "problem.tex"
                content = re.sub(
                    r'\\input\{[^}]*problem\.tex\}',
                    r'\\input{' + str(problem_path).replace('\\', '/') + r'}',
                    content
                )

                # 編集内容を元のファイルに書き戻し
                with open(base_tex, "w", encoding="utf-8") as f:
                    f.write(content)

                # Step 3: ベーステンプレートをコンパイル（template_dirで実行）
                self.progress.emit("ベーステンプレートをコンパイル中...")
                base_pdf = self._compile_latex(base_tex, self.template_dir)

                if not base_pdf or not base_pdf.exists():
                    raise RuntimeError("ベーステンプレートのコンパイルに失敗しました")

            finally:
                # バックアップから復元
                shutil.copy(base_tex_backup, base_tex)
                base_tex_backup.unlink()

            # Step 4: 個別化テンプレートの学期・週・クラスを更新
            self.progress.emit("個別化テンプレートを準備中...")
            personal_tex = self.template_dir / "添削用紙個別化.tex"

            if not personal_tex.exists():
                raise FileNotFoundError(f"個別化テンプレートが見つかりません: {personal_tex}")

            # 元のファイルをバックアップ
            personal_tex_backup = self.template_dir / "添削用紙個別化.tex.bak"
            shutil.copy(personal_tex, personal_tex_backup)

            try:
                with open(personal_tex, "r", encoding="utf-8") as f:
                    content = f.read()

                content = re.sub(
                    r'\\def\\学期\{[^}]*\}',
                    r'\\def\\学期{' + self.term + r'}',
                    content
                )
                content = re.sub(
                    r'\\def\\週番号\{[^}]*\}',
                    r'\\def\\週番号{' + f'{self.week:02d}' + r'}',
                    content
                )
                content = re.sub(
                    r'\\def\\クラス\{[^}]*\}',
                    r'\\def\\クラス{' + self.class_code + r'}',
                    content
                )

                # 編集内容を元のファイルに書き戻し
                with open(personal_tex, "w", encoding="utf-8") as f:
                    f.write(content)

                # Step 5: 個別化テンプレートをコンパイル
                self.progress.emit("個別化テンプレートをコンパイル中...")
                output_pdf = self._compile_latex(personal_tex, self.template_dir)

                if not output_pdf or not output_pdf.exists():
                    raise RuntimeError("個別化テンプレートのコンパイルに失敗しました")

                # 出力ファイル名を整理
                final_name = f"添削用紙_{self.term}_{self.week:02d}週_{self.class_code}.pdf"
                final_path = Config.APP_DATA_DIR / "worksheets" / final_name
                final_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(output_pdf, final_path)

                self.progress.emit("完了!")
                self.finished.emit(str(final_path))

            finally:
                # バックアップから復元
                shutil.copy(personal_tex_backup, personal_tex)
                personal_tex_backup.unlink()

        except Exception as e:
            self.error.emit(str(e))

    def _prepare_problem_tex(self):
        """問題ファイルを準備（なければダミーを生成）"""
        # 週別問題のパス
        week_dir = Config.WEEKS_PATH / self.term / f"第{self.week:02d}週"
        problem_tex = week_dir / "problem.tex"

        if not problem_tex.exists():
            # ダミーのproblem.texを生成
            week_dir.mkdir(parents=True, exist_ok=True)
            dummy_content = r"""\def\週タイトル{第%d週}
\def\テーマ{Writing Practice}
\def\問題文{問題文がまだ設定されていません。週管理から設定してください。}
\def\Wordscount{50-70 words}
""" % self.week
            with open(problem_tex, "w", encoding="utf-8") as f:
                f.write(dummy_content)
            logger.info("ダミーのproblem.texを生成: %s", problem_tex)

    def _compile_latex(self, tex_file: Path, work_dir: Path) -> Path | None:
        """LaTeXをコンパイル（uplatex + dvipdfmx）"""
        import os

        tex_dir = tex_file.parent
        tex_name = tex_file.name
        basename = tex_file.stem

        # TeXのパス設定（既存の環境変数を継承してPATHを追加）
        tex_bin = Config.TEX_BIN_PATH
        env = os.environ.copy()
        if tex_bin:
            env["PATH"] = f"{tex_bin}:{env.get('PATH', '/usr/local/bin:/usr/bin:/bin')}"

        # Step 1: uplatex でDVIを生成（shell-escape必須、2回実行で相互参照を解決）
        uplatex_cmd = ["uplatex", "-shell-escape", "-interaction=nonstopmode", tex_name]
        for i in range(2):
            try:
                result = subprocess.run(
                    uplatex_cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(tex_dir),
                    timeout=120,
                    env=env
                )
                if result.returncode != 0 and i == 1:
                    # 2回目で失敗したらエラー
                    logger.error("uplatex error: %s", result.stderr)
                    return None
            except subprocess.TimeoutExpired:
                return None

        # DVIファイル確認
        dvi_path = tex_dir / f"{basename}.dvi"
        if not dvi_path.exists():
            return None

        # Step 2: dvipdfmx でPDFを生成
        dvipdfmx_cmd = ["dvipdfmx", f"{basename}.dvi"]
        try:
            result = subprocess.run(
                dvipdfmx_cmd,
                capture_output=True,
                text=True,
                cwd=str(tex_dir),
                timeout=60,
                env=env
            )
            if result.returncode != 0:
                logger.error("dvipdfmx error: %s", result.stderr)
                return None
        except subprocess.TimeoutExpired:
            return None

        # PDFファイルを確認
        pdf_path = tex_dir / f"{basename}.pdf"

        # 中間ファイル削除
        self._cleanup_tex_artifacts(tex_dir, basename)

        if pdf_path.exists():
            return pdf_path

        return None

    def _cleanup_tex_artifacts(self, directory: Path, basename: str):
        """TeXの中間ファイルを削除"""
        extensions = ['.aux', '.log', '.dvi', '.synctex.gz', '.out', '.toc']
        for ext in extensions:
            artifact = directory / f"{basename}{ext}"
            if artifact.exists():
                artifact.unlink()


class WorksheetPanel(QWidget):
    """添削用紙出力パネル"""

    def __init__(self):
        super().__init__()
        self._roster: ClassRoster | None = None
        self._worker: LatexCompileWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("添削用紙出力")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # 設定
        settings_group = QGroupBox("出力設定")
        settings_layout = QHBoxLayout(settings_group)

        settings_layout.addWidget(QLabel("学期:"))
        self.term_combo = QComboBox()
        self.term_combo.addItems(["前期", "後期"])
        self.term_combo.setFixedWidth(100)
        settings_layout.addWidget(self.term_combo)

        settings_layout.addSpacing(16)

        settings_layout.addWidget(QLabel("週:"))
        self.week_combo = QComboBox()
        self.week_combo.addItems([f"{i:02d}" for i in range(1, 23)])
        self.week_combo.setFixedWidth(80)
        settings_layout.addWidget(self.week_combo)

        settings_layout.addSpacing(16)

        settings_layout.addWidget(QLabel("クラス:"))
        self.class_input = QLineEdit()
        self.class_input.setPlaceholderText("A")
        self.class_input.setFixedWidth(60)
        settings_layout.addWidget(self.class_input)

        settings_layout.addStretch()
        layout.addWidget(settings_group)

        # テンプレートディレクトリ
        template_group = QGroupBox("テンプレート")
        template_layout = QHBoxLayout(template_group)

        self.template_path = QLineEdit()
        self.template_path.setText(str(Config.TEMPLATES_PATH))
        self.template_path.setReadOnly(True)
        template_layout.addWidget(self.template_path, 1)

        browse_btn = QPushButton("変更")
        browse_btn.clicked.connect(self._browse_template)
        template_layout.addWidget(browse_btn)

        layout.addWidget(template_group)

        # 名簿ステータス
        roster_group = QGroupBox("名簿")
        roster_layout = QVBoxLayout(roster_group)

        self.roster_status = QLabel("名簿が読み込まれていません")
        self.roster_status.setStyleSheet("color: #9b9a97;")
        roster_layout.addWidget(self.roster_status)

        layout.addWidget(roster_group)

        # 出力ボタン
        self.generate_btn = QPushButton("添削用紙を生成")
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 14px 28px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2496c4; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._generate)
        layout.addWidget(self.generate_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 進捗
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # ログ
        log_group = QGroupBox("ログ")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("font-family: monospace; font-size: 12px;")
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)
        layout.addStretch()

    def _browse_template(self):
        """テンプレートディレクトリを選択"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "テンプレートディレクトリを選択",
            self.template_path.text()
        )
        if dir_path:
            self.template_path.setText(dir_path)

    def set_roster(self, roster: ClassRoster):
        """名簿をセット"""
        self._roster = roster
        self.roster_status.setText(
            f"読み込み済み: {roster.year} {roster.class_name} "
            f"({len(roster.get_active_students())} 名)"
        )
        self.roster_status.setStyleSheet("color: #0f7b0f; font-weight: bold;")
        self.generate_btn.setEnabled(True)

        # クラス名からクラスコードを自動抽出（例: "高2英語A" → "A", "高2英語U4" → "U4"）
        class_name = roster.class_name
        if class_name and class_name.startswith("高2英語"):
            # "高2英語" を削除してクラスコードを抽出
            self.class_input.setText(class_name.replace("高2英語", ""))
        else:
            self.class_input.setText(class_name)

    def _generate(self):
        """添削用紙を生成"""
        if not self._roster:
            QMessageBox.warning(self, "エラー", "名簿を先に読み込んでください")
            return

        template_dir = Path(self.template_path.text())
        if not template_dir.exists():
            QMessageBox.warning(self, "エラー", "テンプレートディレクトリが見つかりません")
            return

        term = self.term_combo.currentText()
        week = int(self.week_combo.currentText())
        class_code = self.class_input.text() or "A"

        self.log_text.clear()
        self._log(f"生成開始: {term} 第{week:02d}週 クラス{class_code}")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # インデターミネート
        self.generate_btn.setEnabled(False)

        self._worker = LatexCompileWorker(
            template_dir=template_dir,
            term=term,
            week=week,
            class_code=class_code,
            roster=self._roster
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _log(self, message: str):
        """ログに追加"""
        self.log_text.append(message)

    def _on_progress(self, message: str):
        """進捗更新"""
        self._log(message)

    def _on_finished(self, pdf_path: str):
        """完了"""
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        self._log(f"出力完了: {pdf_path}")

        QMessageBox.information(
            self,
            "生成完了",
            f"添削用紙を生成しました:\n{pdf_path}"
        )

        # Finderで開く
        subprocess.run(["open", "-R", pdf_path], check=False)

    def _on_error(self, error: str):
        """エラー"""
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        self._log(f"エラー: {error}")

        QMessageBox.critical(self, "エラー", f"生成に失敗しました:\n{error}")
