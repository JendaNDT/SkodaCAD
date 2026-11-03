# Ukončení Windows testů — diagnostika a životnost oken

Vydávací běh `41670049215`, job `126035672098`, dokončil 3. 11. 2026 všech
2 856 testů za 1 939,90 s. Proces se po souhrnu neukončil a narazil na 35min limit.
Nešlo o neúspěšný test. Podobný starší výskyt jednou při opakování zmizel; to
neprokázalo opravu. Další nezměněné opakování tohoto vydání se proto neprovedlo.

Oddělená diagnostika `41677930266`, job `126063464532`, přidala pozorování hranic
pytest, atexit a GC, výpisy Python vláken a minidump vlastního procesu. Záměrně
skončila chybou při zaseknutí, bez nuceného úspěšného ukončení. Artefakt
`13253117556` (`windows-exit-diagnostic`) obsahuje původní důkazy. Jeho SHA-256:
`5acced94ed27fdd261216afd9380ea01ee443e5c8fc9f46ed3c51fee4ce1129c`.

## Co bylo skutečně zachyceno

- Znovu 2 856 passed, tentokrát za 1 892,78 s.
- `SESSIONFINISH_LEAVE`, `UNCONFIGURE_LEAVE`, dokončené GC a `PYTEST_RETURN`, kód 0.
- Poslední značka `ATEXIT_LATE_REGISTERED`; starší atexit značka už nepřišla.
- Žádné aktivní multiprocessing potomky; pět daemon vláken `step-result` čekalo
  v příjmu roury. Jejich přítomnost sama nevysvětluje hlavní nativní zásobník.
- Po 90 s dohled pořídil platný minidump a ukončil pouze vlastní strom procesů.
  Celý diagnostický běh zůstal neúspěšný.

Minidump lze na místním Macu číst LLDB. Po doplnění odpovídajících Windows DLL
z oficiálních wheelů PySide6 Essentials a shiboken6 **6.11.3** ukazuje hlavní vlákno:

```text
PySide::SignalManager::retrieveMetaObject
PySide::SignalManager::handleMetaCallError
QObject::~QObject
QObjectPrivate::deleteChildren
QWidget::~QWidget
PySide::destroyQCoreApplication
Shiboken::BindingManager::visitAllPyObjects
PySide::destroyQCoreApplication
PySide::runCleanupFunctions
```

Jsou vynechány rámce bez přesných interních symbolů (QtGui/QtWidgets `.pyd`).
Prokázaná fáze je pozdní rušení Qt objektů při úklidu aplikace; není to běžící
zkouška ani nedokončený pytest. Přesná nejnižší příčina uvnitř DLL není prokázána,
stejně jako případná chyba PySide. Zdroj
[PySide 6.11.3](https://github.com/pyside/pyside-setup/blob/v6.11.3/sources/pyside6/libpyside/pyside.cpp)
potvrzuje, že tato cesta při ukončení obchází a ničí dosud vlastněné QObject objekty.

## Oprava vlastnictví v testech

Dosavadní GUI fixtures zavíraly okna přes `close()`. To obvykle pouze skryje QWidget;
nezruší jeho nativní objekt. Regrese výslovně ověřuje, že okno i akce po close
zůstávají platné, i když Python stále drží reference/cyklus signálu. Přenechávání
těchto testovacích objektů až pozdnímu úklidu aplikace odpovídá zachycené cestě.

Nová funkční autouse fixture si zapamatuje již existující vrcholová okna. Po
dokončení ostatních fixtures zavře pouze nová testová okna běžným `closeEvent`,
naplánuje `deleteLater()` a výslovně doručí `DeferredDelete`, dokud je QApplication
i Python živý. Neuložený testový model už po testu nevyvolává potvrzovací dialog.
Předchozí okna zachová, potomky zruší s rodičem a ověří neplatnost zrušených
wrapperů. Bez Qt aplikace nedělá nic; Qt se kvůli běžnému testu nově neimportuje.

Nejde o `os._exit`, vypnutí signálů/testů ani zvýšení vydávacího timeoutu.
Produkční `src`, geometrie, formát a závislosti se nemění. Dva nové testy hlídají
zrušení při živých Python referencích i zachování dřívějšího okna. Cílené Windows
workflow nejprve ověřuje tento životní cyklus a návrat skutečného procesu.
Původní úplná diagnostická reprodukce se kvůli každé úpravě neopakuje.

Místně prošlo osm cílených Qt zkoušek přes diagnostický wrapper, včetně změny
parametru a čtyř kombinací zániku starých akcí během náhledu, s normálním návratem 0.
Zvlášť byl ověřen skutečně selhaný test (kód 1) a umělé čekání v atexit (timeout 124).
Před sloučením musí uspět cílený Windows běh, běžná úplná sada a build i self-test
stažených aplikací na obou systémech. Místní úspěch sám nedokazuje odstranění
vzácného Windows zaseknutí. Oprava se týká správy oken v testech, netvrdí změnu
produkčního CAD algoritmu ani absenci všech možných budoucích chyb ukončování.
