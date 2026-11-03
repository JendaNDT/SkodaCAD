# P7.35 — výběr dílu nebo vazby z použití parametru

V **Parametry sestavy…** klikni v dolním přehledu na libovolnou buňku místa použití.
Komponenta (i nadřazená podsestava) se vybere ve stromu a zvýrazní ve 3D. U vazby
se rozbalí skupina vazeb, vybere správný záznam a zvýrazní jeho referenční plochy.
Odkaz na další parametr ho vybere v horní tabulce. Funguje také **Enter** na řádku
přehledu. Pod tabulkou je potvrzení, které místo se vybralo.

## Zachování rozpracované práce

Modální editor zůstane otevřený. Není třeba přijmout ani zahodit rozepsané hodnoty,
výrazy nebo přejmenování. Přehled stále používá pracovní kopii, zatímco zvýraznění
ukazuje současnou spočítanou sestavu; prohlížení nesimuluje budoucí přesun.
**Použít změny** dál přijímá celou dávku jedním krokem Zpět. **Zrušit** zahodí
úpravy parametrů a ponechá výběr jako změnu pohledu.

Výběr nepřepočítává model a nemění výsledek, kameru, historii, zdrojové soubory,
viditelnost, izolaci ani průhlednost. Skrytá komponenta se vybere ve stromu, ale
sama se nezobrazí. Plochy vazby při izolaci nebo skrytí komponent zůstávají podle
stávajících pravidel bez překryvu, aby neodhalily skryté části. Chybějící díl lze
vybrat jako záznam ve stromu i bez tělesa. Na cíl, který už není dostupný, editor
upozorní a výběr nezmění.

## Provedení a ochrany

Každé místo nese samostatný `UsageTarget(kind, id)`; výběr neparsuje český popisek,
nehledá podle nejednoznačného jména a nespoléhá na pořadí přehledu. Vnitřní obsah
podsestav se nečte. Pracovní přejmenování nemění id komponent ani vazeb.
Zpětné volání ověřuje původní objekt sestavy i existenci id a položky stromu:
odkaz starého editoru nesmí vybrat stejně pojmenované id v jiném modelu.

Úspěšný výběr zruší rozpracované tažení a výběr osy/středu otočení. Zvýší také
revizi ovládání pohybu, aby se staré uvolnění myši odmítlo i při opětovném výběru
stejného dílu. Neplatný cíl tyto stavy nemění. Enter má vlastní klávesovou zkratku;
kliknutí se nezpracovává současně jako aktivace jiného řádku po obnově tabulky.
Formát souborů, geometrické jádro ani závislosti se nemění.

## Ověření

`tests/test_assembly_parameter_navigation.py` ověřuje skutečná kliknutí ve všech
sloupcích, komponentu, vazbu a navazující parametr, oba Entery, pracovní přejmenování
a desetinnou čárku, zachování modelu/výsledku/historie/zdrojů, rozbalení stromu,
izolaci a skrytí, chybějící díl, neplatné a zastaralé cíle a odmítnutí starého tahu.

Nativní self-test **Výběr z použití parametru sestavy** otevře skutečný modální editor,
přidá závislý parametr, přejmenuje `mezera → vule` a zadá `12,5`. Klikne na komponentu,
vazbu a parametr a ověří strom, skutečné 3D zvýraznění, sedm splněných vazeb,
odmítnutí starého tahu a zachovaný model, výsledek, kameru, historii i zdroje.
Zrušení změny zahodí a ponechá jen výběr. Tento scénář běží i ve stažených aplikacích
Windows a macOS. Místní evidence je v `out/assembly-parameter-navigation/`.
