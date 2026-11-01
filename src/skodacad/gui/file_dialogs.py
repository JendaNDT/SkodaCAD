"""Jednotná volba souborových dialogů dílu i sestavy."""

from PySide6.QtWidgets import QFileDialog

# Systémový panel macOS předá i přístup k vybranému souboru v chráněné složce.
# Widgetový dialog Qt (DontUseNativeDialog) toto předání nenahrazuje.
FILE_OPTIONS = QFileDialog.Option(0)
