"""Desktop web-scraping application.

Usage:
    1. Install dependencies (virtualenv recommended):
       pip install -r requirements.txt

    2. (Optional) Install Playwright browsers if you need dynamic scraping:
       playwright install

    3. Run the application:
       python -m app.main

Requirements (requirements.txt):
    PyQt6
    requests
    beautifulsoup4
    lxml
    playwright
    selenium
    openpyxl
    python-docx
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.export_utils import export_csv, export_docx, export_html, export_text, export_xlsx
from app.models import ScrapeResult, SelectorConfig
from app.scraping import ScrapeProgress, Scraper

LOG_FILE = Path("scraper_app.log")


@dataclass
class ScrapeJob:
    """Container for a scrape run."""

    urls: List[str]
    selectors: SelectorConfig
    mode: str


class ScrapeWorker(QThread):
    """Worker thread to keep UI responsive during scraping."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, job: ScrapeJob, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.scraper = Scraper()

    def run(self) -> None:
        def update(progress: ScrapeProgress) -> None:
            self.progress.emit(progress.message)

        results = self.scraper.scrape_urls(
            self.job.urls,
            self.job.selectors,
            self.job.mode,
            progress=update,
        )
        self.finished.emit(results)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cross-Platform Web Scraper")
        self.resize(1200, 700)

        self.results: List[ScrapeResult] = []

        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Idle")
        self.setStatusBar(self.status_bar)

        self._build_ui()

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_results_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)
        layout.addWidget(self._build_exports())

        self.setCentralWidget(container)

    def _build_controls(self) -> QWidget:
        group = QGroupBox("Targets & Rules")
        layout = QVBoxLayout(group)

        url_label = QLabel("Target URLs (one per line):")
        self.url_text = QTextEdit()
        self.url_text.setPlaceholderText("https://example.com\nhttps://example.org")
        self.url_text.setText("https://example.com")

        mode_layout = QHBoxLayout()
        mode_label = QLabel("Scraping Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Static (requests)", "Dynamic (Selenium/Playwright)"])
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)

        selectors_group = QGroupBox("Extraction Selectors (CSS or XPath)")
        selectors_layout = QGridLayout(selectors_group)

        self.title_selector = QLineEdit("title")
        self.content_selector = QLineEdit("body")
        self.price_selector = QLineEdit(".price")
        self.links_selector = QLineEdit("a")

        selectors_layout.addWidget(QLabel("Title"), 0, 0)
        selectors_layout.addWidget(self.title_selector, 0, 1)
        selectors_layout.addWidget(QLabel("Content"), 1, 0)
        selectors_layout.addWidget(self.content_selector, 1, 1)
        selectors_layout.addWidget(QLabel("Price"), 2, 0)
        selectors_layout.addWidget(self.price_selector, 2, 1)
        selectors_layout.addWidget(QLabel("Links"), 3, 0)
        selectors_layout.addWidget(self.links_selector, 3, 1)

        self.start_button = QPushButton("Start Scraping")
        self.start_button.clicked.connect(self.start_scraping)

        layout.addWidget(url_label)
        layout.addWidget(self.url_text)
        layout.addLayout(mode_layout)
        layout.addWidget(selectors_group)
        layout.addWidget(self.start_button)
        layout.addStretch(1)

        return group

    def _build_results_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["URL", "Title", "Content", "Price", "Links"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self.show_details)

        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("Select a row to view full details.")

        layout.addWidget(QLabel("Scraped Results:"))
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Details:"))
        layout.addWidget(self.detail_view)

        return panel

    def _build_exports(self) -> QWidget:
        group = QGroupBox("Export")
        layout = QHBoxLayout(group)

        self.export_csv_button = QPushButton("Export to Spreadsheet")
        self.export_csv_button.clicked.connect(self.export_spreadsheet)

        self.export_doc_button = QPushButton("Export to Document")
        self.export_doc_button.clicked.connect(self.export_document)

        self.export_text_button = QPushButton("Export to Notepad Text")
        self.export_text_button.clicked.connect(self.export_text)

        layout.addWidget(self.export_csv_button)
        layout.addWidget(self.export_doc_button)
        layout.addWidget(self.export_text_button)
        layout.addStretch(1)

        return group

    def start_scraping(self) -> None:
        urls = self.url_text.toPlainText().splitlines()
        selectors = SelectorConfig(
            title=self.title_selector.text().strip(),
            content=self.content_selector.text().strip(),
            price=self.price_selector.text().strip(),
            links=self.links_selector.text().strip(),
        )
        mode = self.mode_combo.currentText()
        job = ScrapeJob(urls=urls, selectors=selectors, mode=mode)

        self.status_bar.showMessage("Starting...")
        self.start_button.setEnabled(False)

        self.worker = ScrapeWorker(job)
        self.worker.progress.connect(self.status_bar.showMessage)
        self.worker.finished.connect(self.on_scrape_finished)
        self.worker.start()

    def on_scrape_finished(self, results: List[ScrapeResult]) -> None:
        self.results = results
        self.start_button.setEnabled(True)
        self.status_bar.showMessage("Done")
        self.populate_table()

    def populate_table(self) -> None:
        self.table.setRowCount(len(self.results))
        for row_index, result in enumerate(self.results):
            self.table.setItem(row_index, 0, QTableWidgetItem(result.url))
            self.table.setItem(row_index, 1, QTableWidgetItem(result.title))
            self.table.setItem(row_index, 2, QTableWidgetItem(result.content))
            self.table.setItem(row_index, 3, QTableWidgetItem(result.price))
            self.table.setItem(row_index, 4, QTableWidgetItem(result.links_text()))
        self.table.resizeColumnsToContents()

    def show_details(self, row: int, _column: int) -> None:
        if row >= len(self.results):
            return
        result = self.results[row]
        details = (
            f"URL: {result.url}\n\n"
            f"Title: {result.title}\n\n"
            f"Content: {result.content}\n\n"
            f"Price: {result.price}\n\n"
            f"Links: {result.links_text()}"
        )
        self.detail_view.setPlainText(details)

    def export_spreadsheet(self) -> None:
        if not self._ensure_results():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Spreadsheet",
            "scraped_data.csv",
            "CSV Files (*.csv);;Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".xlsx"):
                export_xlsx(Path(path), self.results)
            else:
                export_csv(Path(path), self.results)
            self.status_bar.showMessage("Exported spreadsheet")
        except Exception as exc:  # noqa: BLE001
            logging.exception("Spreadsheet export failed")
            QMessageBox.warning(self, "Export Error", str(exc))

    def export_document(self) -> None:
        if not self._ensure_results():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Document",
            "scraped_data.docx",
            "DOCX Files (*.docx);;HTML Files (*.html)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".docx"):
                export_docx(Path(path), self.results)
            else:
                export_html(Path(path), self.results)
            self.status_bar.showMessage("Exported document")
        except Exception as exc:  # noqa: BLE001
            logging.exception("Document export failed")
            QMessageBox.warning(self, "Export Error", str(exc))

    def export_text(self) -> None:
        if not self._ensure_results():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Text",
            "scraped_data.txt",
            "Text Files (*.txt)",
        )
        if not path:
            return
        try:
            export_text(Path(path), self.results)
            self.status_bar.showMessage("Exported text")
        except Exception as exc:  # noqa: BLE001
            logging.exception("Text export failed")
            QMessageBox.warning(self, "Export Error", str(exc))

    def _ensure_results(self) -> bool:
        if not self.results:
            QMessageBox.information(self, "No Data", "Run a scrape before exporting.")
            return False
        return True


def setup_logging() -> None:
    """Configure application logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    """Entry point for the GUI application."""

    setup_logging()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
