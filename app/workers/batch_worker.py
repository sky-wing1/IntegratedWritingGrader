"""バッチ処理ワーカー"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config
from app.utils.qr_parser import find_dynamiks_output, parse_dynamiks_csv
from app.workers.pipeline_worker import PipelineWorker


class BatchScanWorker(QThread):
    """複数PDFのQRコードスキャンワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    job_scanned = pyqtSignal(int, dict)   # job_index, student_info
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, pdf_paths: list[Path], parent=None):
        super().__init__(parent)
        self.pdf_paths = pdf_paths
        self._is_cancelled = False

    def run(self):
        """スキャン実行"""
        try:
            total = len(self.pdf_paths)

            for i, pdf_path in enumerate(self.pdf_paths):
                if self._is_cancelled:
                    return

                self.progress.emit(i, total, f"スキャン中: {pdf_path.name}")

                # PipelineWorkerを同期的に実行
                worker = PipelineWorker(str(pdf_path))

                # 同期実行のための待機
                worker.start()
                worker.wait()

                # 結果を取得
                if worker.students:
                    first_student = worker.students[0]
                    student_info = {
                        "year": first_student.year,
                        "term": first_student.term,
                        "week": first_student.week,
                        "class_name": first_student.class_name,
                        "page_count": len(worker.students),
                    }
                    self.job_scanned.emit(i, student_info)
                else:
                    # QRコードが検出できなかった場合
                    self.job_scanned.emit(i, {"page_count": 0})

            self.progress.emit(total, total, "スキャン完了")
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True


class BatchGradeWorker(QThread):
    """複数PDFの一括採点ワーカー"""

    progress = pyqtSignal(int, int, str)           # current, total, message
    job_progress = pyqtSignal(int, int, int)       # job_index, page, total_pages
    job_finished = pyqtSignal(int, list)           # job_index, results
    finished = pyqtSignal(list)                     # all_results
    error = pyqtSignal(str)

    def __init__(self, jobs: list[dict], parent=None):
        """
        Args:
            jobs: ジョブリスト。各ジョブは以下のキーを持つ:
                - pdf_path: str
                - year: int
                - term: str
                - week: int
                - class_name: str
        """
        super().__init__(parent)
        self.jobs = jobs
        self._is_cancelled = False

    def run(self):
        """採点実行"""
        try:
            from app.workers.grading_worker import GradingWorker

            total_jobs = len(self.jobs)
            all_results = []

            for job_idx, job in enumerate(self.jobs):
                if self._is_cancelled:
                    return

                pdf_path = job["pdf_path"]
                self.progress.emit(
                    job_idx, total_jobs,
                    f"採点中 ({job_idx + 1}/{total_jobs}): {Path(pdf_path).name}"
                )

                # 現在の週を設定
                Config.set_current_week(
                    job.get("year"),
                    job.get("term"),
                    job.get("week"),
                    job.get("class_name")
                )

                # GradingWorkerを同期的に実行
                grading_worker = GradingWorker(pdf_path)

                # 進捗コールバック
                def on_progress(current, total, msg):
                    self.job_progress.emit(job_idx, current, total)

                grading_worker.progress.connect(on_progress)

                # 同期実行
                grading_worker.start()
                grading_worker.wait()

                # 結果を取得
                results = grading_worker._results
                self.job_finished.emit(job_idx, results)

                # 結果を保存
                if results:
                    Config.save_results(results)
                    all_results.append({
                        "pdf_path": pdf_path,
                        "year": job.get("year"),
                        "term": job.get("term"),
                        "week": job.get("week"),
                        "class_name": job.get("class_name"),
                        "results": results,
                    })

            self.progress.emit(total_jobs, total_jobs, "一括採点完了")
            self.finished.emit(all_results)

        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True
