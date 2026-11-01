# P7.17 – hromadný výběr komponent sestavy

Datum: **1. 11. 2026**. Navazuje na P7.13–P7.16.

## Ovládání

Ve stromu klik vybere jednu komponentu, **Ctrl+klik** (macOS **⌘+klik**) přidá
nebo ubere řádek a **Shift+klik** vybere rozsah. **Ctrl/⌘+A** vybere všechny
komponenty, včetně vnořených; vazby do tohoto výběru nepatří. **Esc** jej zruší.
Zkratky platí pouze ve stromu, takže zadávání textu v editoru zůstává běžné.

Ve 3D zůstává výběr ploch a hran pro vazby: Ctrl/⌘+klik plochu přidá nebo ubere.
Komponenty všech vybraných ploch se současně vyberou ve stromu a zvýrazní ve 3D.
Více ploch stejného dílu znamená jednu vybranou komponentu. Prázdný klik výběr
zruší. Kliky na skryté tvary se odmítají a neodkrývají je zvýrazněním.

Panel oznámí počet vybraných komponent. **H** skryje celý výběr, pokud je vše
ručně viditelné; jinak vše vybrané zobrazí. **I** izoluje sjednocení vybraných
větví a dál respektuje ruční skrytí. Ukončení izolace zachová ruční stav.
**T** vypne průhlednost, pokud je všude zapnutá, jinak ji všude zapne. Každý díl
si přitom pamatuje svou míru. Pole procent ukazuje společné číslo nebo **Různé**;
zadání čísla sjednotí celý výběr včetně skrytých dílů.

Vybraný rodič zahrnuje potomky; současně vybraný potomek se při hromadné operaci
nezpracuje podruhé. Kopie téhož souboru zůstávají nezávislé podle cesty id.
Změna názvu, polohy, natočení, pevnosti, zdroje, smazání a otevření dílu vyžadují
jedinou komponentu. Vazba se vybírá samostatně a její editor funguje jako dříve.

## Data a přepočet

Výběr i izolace jsou pouze stav okna. Nemění recept, geometrii, historii, součty,
kontroly, kusovník ani úplný STEP. H/T/procenta provedou jednu společnou aktualizaci,
ne samostatný přepočet pro každý díl. Pouhá změna vzhledu zachová kameru, rozepsaná
pole a plochy pro vazby. Skrytí/izolace plochy vazeb vyčistí jako dříve.

Přepočet, Zpět/Znovu a Uložit jako zachovají existující cesty výběru a izolace.
Odstraněné cesty se vyřadí, zbylé zůstanou vybrané/izolované. Zánik posledního
kořene izolaci ukončí. Zpět neobnovuje dřívější výběr odstraněného id.
Neúspěšné nebo zrušené otevření stav zachová. Úspěšné otevření/založení sestavy
vyčistí výběr i pravidla pohledu. Formát ani závislosti se nemění.

## Ověření

Regrese používají skutečné Qt kliky/klávesy ve stromu a náhradní renderer pro
kontrolu sjednocení vybraných kopií, smíšených stavů, ochrany editace a životnosti.
Ověřují fyzický objem a počet těles viditelné podmnožiny i úplného exportu STEP,
nezměněnou historii/recept, opakované použití řádků a stávající výběr vazeb.

Nativní self-test aplikace navíc provede Ctrl/⌘, Shift, A/Esc, společných 60 %,
H **6→4→6**, I **2/6**, skutečné přidání a ubrání ploch přes OCCT, zachování
ploch pro vazby po T a stálou kameru/objem/recept/historii. Samostatné nativní
okno otevře a vybere oba díly ještě před prvním paintem: pozdější inicializace
3D musí zachovat výběr komponent. `selection_cleared` se vysílá jen pro prázdný
klik nebo výslovné zrušení; technické vyčištění ploch při vykreslení jej nevysílá.
Nativní ověření se vyžaduje také ze stažených balíčků Windows i macOS.
Protokoly a snímek: `out/p7-multi-selection/`; konečné výsledky CI patří do PR.
P7.4 (autorská přejímka celého prostředí) zůstává otevřená.
