from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QTextEdit, QMenu
from PySide6.QtGui import QPixmap, QAction, QPainter
from PySide6.QtCore import Qt, QPoint
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

# 尝试导入 PDF 组件（可能在某些环境不可用）
try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
    HAS_PDF = True
except Exception:
    QPdfDocument = None  # type: ignore
    QPdfView = None  # type: ignore
    HAS_PDF = False


class DocumentViewer(QDialog):
    """简单文档阅读器：支持 pdf/txt/常见图片。
    右键菜单：打印、最大化/还原。
    """
    def __init__(self, file_path: str, filename: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"阅读 - {filename}")
        self.setMinimumSize(900, 700)
        self._kind = 'unknown'
        self._text_widget: QTextEdit | None = None
        self._pix: QPixmap | None = None
        self._pdf_doc: QPdfDocument | None = None  # type: ignore
        self._pdf_view = None

        # 统一滚动条样式
        self.setStyleSheet(
            """
            QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; border-radius: 5px; }
            QScrollBar::handle:vertical { background: #cfd8dc; min-height: 40px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #90caf9; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal { height: 10px; background: transparent; margin: 2px; border-radius: 5px; }
            QScrollBar::handle:horizontal { background: #cfd8dc; min-width: 40px; border-radius: 5px; }
            QScrollBar::handle:horizontal:hover { background: #90caf9; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            """
        )

        layout = QVBoxLayout(self)

        ext = (filename or '').lower().rsplit('.', 1)
        ext = ('.' + ext[-1]) if len(ext) == 2 else ''

        if ext == '.pdf' and HAS_PDF:
            self._pdf_doc = QPdfDocument(self)
            self._pdf_doc.load(file_path)
            self._pdf_view = QPdfView(self)
            self._pdf_view.setDocument(self._pdf_doc)
            self._pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            layout.addWidget(self._pdf_view)
            self._kind = 'pdf'
            return

        if ext in ('.txt', '.log', '.md', '.json', '.csv'):
            text = ''
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except Exception:
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        text = f.read()
                except Exception:
                    text = '无法以文本模式打开该文件。'
            editor = QTextEdit(self)
            editor.setReadOnly(True)
            editor.setPlainText(text)
            layout.addWidget(editor)
            self._text_widget = editor
            self._kind = 'text'
            return

        if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'):
            pix = QPixmap(file_path)
            label = QLabel(self)
            label.setAlignment(Qt.AlignCenter)
            label.setPixmap(pix)
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            container = QWidget()
            v = QVBoxLayout(container)
            v.addWidget(label)
            scroll.setWidget(container)
            layout.addWidget(scroll)
            self._pix = pix
            self._kind = 'image'
            return

        tip = QLabel("该文件类型暂不支持内置阅读，请使用下载后本地应用打开。", self)
        tip.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip)

    # 右键菜单：打印/最大化
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_print = QAction('打印...', self)
        act_print.triggered.connect(self._print_current)
        menu.addAction(act_print)
        if self.isMaximized():
            act_max = QAction('还原', self)
        else:
            act_max = QAction('最大化', self)
        act_max.triggered.connect(self._toggle_maximize)
        menu.addAction(act_max)
        menu.exec(event.globalPos())

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _print_current(self):
        if self._kind == 'text' and self._text_widget is not None:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() == QPrintDialog.Accepted:
                self._text_widget.document().print(printer)
            return
        if self._kind == 'image' and self._pix is not None:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() == QPrintDialog.Accepted:
                painter = QPainter(printer)
                # 居中等比缩放
                page_rect = printer.pageRect()
                img = self._pix
                img_size = img.size()
                img_size.scale(page_rect.size(), Qt.KeepAspectRatio)
                x = page_rect.x() + (page_rect.width() - img_size.width()) // 2
                y = page_rect.y() + (page_rect.height() - img_size.height()) // 2
                painter.drawPixmap(x, y, img.scaled(img_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                painter.end()
            return
        if self._kind == 'pdf':
            # 暂不直接支持 PDF 打印（可后续扩展为逐页渲染）
            tip = QLabel("当前环境暂不支持直接打印 PDF，请先下载后再打印。", self)
            tip.setWindowFlag(Qt.Tool)
            tip.show() 