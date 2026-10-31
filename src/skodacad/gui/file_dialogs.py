"""Jednotná volba souborových dialogů dílu i sestavy."""

import sys

from PySide6.QtWidgets import QFileDialog

# macOS 27.2: nativní panely při ovládání přes přístupnost odmítají platný JSON/CSV.
# Qt dialog zachovává stejné filtry a umožňuje otevření i uložení z klávesnice.
FILE_OPTIONS = (QFileDialog.Option.DontUseNativeDialog if sys.platform == "darwin"
                else QFileDialog.Option(0))
