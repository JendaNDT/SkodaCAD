# P7.7 – otevírání modelů z Dokumentů na macOS

Datum: **1. 11. 2026**. Navazuje na zjištění při průchodu P7.6.

## Příčina a změna

Při spuštění sestavené aplikace přes Launch Services výběr pracovního JSONu
z Dokumentů v dialogu Qt skončil čekáním na čtení. Vzorek procesu ukazuje
hlavní vlákno v Python `FileIO` → systémový `open`; záznam `tccd` obsahuje
žádost ŠkodaCADu o `SystemPolicyDocumentsFolder`. Stejný model z vlastního
balíčku aplikace šel otevřít. Nešlo o čekání na modelování OCCT.

Sdílené `gui/file_dialogs.FILE_OPTIONS` už na macOS nevynucuje
`DontUseNativeDialog`. Díly, sestavy, importy i výstupy znovu používají
systémové Open/Save panely. Ty předávají aplikaci přístup k uživatelem
vybranému souboru. Formát JSON, kontroly obsahu, přípony a historie modelu
se nemění; Windows už používal stejnou nulovou volbu.

Starší náhrada dialogem Qt vznikla při P5.5 kvůli omezení ovládání nativního
panelu přes přístupnost. Nemá se obnovovat jako plošné řešení automatizačních
potíží: nepřebírá systémové předání přístupu. Nová knihovna ani změna
oprávnění v Nastavení systému nejsou součástí opravy.

Opora pro volbu: [Apple NSOpenPanel](https://developer.apple.com/documentation/appkit/nsopenpanel),
[Apple – What’s new in privacy, NSOpenPanel](https://developer.apple.com/videos/play/wwdc2023/10053/)
a [Qt QFileDialog, nativní panely a DontUseNativeDialog](https://doc.qt.io/qt-6/qfiledialog.html).

## Ověření

Rozhodující je spustit hotovou aplikaci přes Launch Services, vybrat v systémovém
panelu skutečný pracovní soubor z Dokumentů, zkontrolovat model, uložit kopii
a znovu ji otevřít. Spuštění z vývojového terminálu s jeho zděděným přístupem
k Dokumentům samotné tento problém neověřuje. U nativního panelu se vybírá
konkrétní řádek souboru; pouhé zadání cesty bez dokončení výběru není přijetí.

Referenční deska `examples/deska_workflow.json` má 80 × 50 × 10 mm, čtyři
průchozí Ø6 a čtyři rohy R2. Očekávaný objem je **39840 − 320π =
38834,690351 mm³**, jedno platné těleso. Původní recept musí zůstat beze změny.

Regrese okna/sestav a výstupních guardů: `tests/test_gui.py`,
`tests/test_assembly_gui.py`, `tests/test_output_gui.py`, `tests/test_p34_step_gui.py`.
Skutečný výběr v systémovém panelu se nedokazuje jeho nahrazením ve fixture;
lokální průchod a jeho meze se evidují samostatně v implementačním PR.
Úplná sada a kontrola staženého balíčku běží před sloučením na Windows i macOS.
Místní artefakty jsou v `out/p7-documents-access/`.
