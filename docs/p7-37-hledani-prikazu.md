# P7.37 — najít příkaz v dílu a sestavě

Autor po uzavřené P8.5 vybral pokračování **Ovládání a pracovní postupy**.
Rozsáhlé nabídky dílu a sestavy dosud neměly společné hledání. Nové
**Najít příkaz…** je v záhlaví pásu hlavního okna a v liště sestavy;
také **Nápověda → Najít příkaz…** v dílu, **Úpravy → Najít příkaz…** v sestavě.
Obě okna používají **Ctrl+Shift+P**, na Macu **⌘+Shift+P**.

Napiš část názvu, například `ulozit`, `vybrane hrany` nebo `parametry`.
Hledání nerozlišuje velikost písmen a diakritiku. Více slov musí být přítomných
v názvu nebo cestě nabídky; shody přímo v názvu mají přednost. Seznam ukazuje
původní název, nabídku a skutečnou systémovou zkratku. Šipky nahoru/dolů mění
výběr, Enter nebo **Spustit** provede příkaz, Esc nebo **Zavřít** hledání zavře.
Příkaz lze spustit i dvojklikem. Nenalezený výraz má vysvětlení a vypnuté Spustit.

## Chování a meze

- Hledání používá původní `QAction`, včetně stavu, klávesy a obsluhy.
  Nevytváří druhý způsob ukládání, přepočtu či změny dokumentu.
- Příkazy jsou z aktuálních nabídek a v dílu také z pásu nástrojů. Opakovaný
  odkaz na stejnou akci se objeví jednou. Kontextové nabídky mimo hlavní nabídku
  a vnitřní tlačítka právě otevřeného editoru se samostatně neindexují.
- Nedostupný příkaz zůstává dohledatelný s vysvětlením, ale nejde spustit.
  Platí i zákaz nadřazené nabídky. Dostupnost se znovu ověří před zavřením
  hledání i těsně před provedením; skrytá nebo zaniklá akce se nespustí.
- Nejprve se zavře hledání a pak se jednou zavolá původní příkaz. Jeho
  standardní potvrzení, výběr souboru, náhled a Zpět/Znovu zůstávají platné.
- Procházení seznamu a jeho zrušení samo nemění dokument, výsledek, historii
  ani kameru. Není to vyhledávání prvků modelu, parametrů či souborů.
  Není zde nový formát, závislost, síťový požadavek ani ukládání historie hledání.

## Ověření

`tests/test_command_search.py` ověřuje cesty a deduplikaci, hledání bez diakritiky,
více slov a nulové výsledky, šipky/Enter/Esc, stav nadřazené nabídky, změnu
dostupnosti během dialogu, zánik externí akce a opětovnou kontrolu po zavření.
Skutečný callback musí být zavolán jednou a až po zavření modálního hledání;
checkable akce přepne stav jednou. Testy oken dílu i sestavy hlídají izolaci
dokumentu a původního výsledku.

Do self-testu skutečně stažené aplikace je přidané **Hledání příkazů (díl/sestava)**:
nativní zkratka, psaní bez diakritiky, šipky, Esc bez změny receptu, výsledku,
historie a kamery a Enter s jediným přepnutím existujícího pohledového příkazu.
Místní Cocoa ověření se skutečnými OCCT prohlížeči prošlo v obou oknech;
snímky světlého/tmavého režimu jsou v ignorovaném `out/ux-command-search/`.
Úplné CI a ověření nových balíčků Windows/macOS jsou samostatná podmínka vydání
této dávky; úspěchy vydané P8.5 je nenahrazují.
