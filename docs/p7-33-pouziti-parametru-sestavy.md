# P7.33 — přehled použití parametrů sestavy

V editoru **Parametry sestavy…** vyber řádek. Dolní tabulka ukáže všechna místa,
která na vybrané hodnotě přímo nebo přes další parametry závisejí:

- jiný parametr a jeho výraz;
- konkrétní komponentu (jméno i id), osu posunu v mm nebo otočení ve stupních;
- vzdálenostní vazbu (jméno i id), její výraz a cestu závislosti.

Například `polovina = 6,25`, `mezera = polovina * 2` a vzdálenost vazby `mezera`:
u vybrané **poloviny** se zobrazí přímý odkaz do parametru **mezera** a nepřímý
odkaz do vazby **přes mezera**. Nepoužitá hodnota má výslovnou zprávu.

P7.35 přidává [výběr místa jedním kliknutím](p7-35-vyber-z-pouziti-parametru.md):
komponentu nebo vazbu vybere ve stromu a zvýrazní ve 3D, parametr v horní tabulce.
Editor a jeho pracovní změny zůstávají otevřené. Skryté díly se samy nezobrazují.

## Pravidla a meze

`assembly_parameter_usage.parameter_usage` pouze čte recept. Název pozná podle
syntaktického stromu výrazu, nikoli podřetězcem (`d` není `delsi`); názvy volaných
funkcí nejsou parametry. Prochází návaznosti bez závislosti na pořadí řádků.
Cyklus hledání nezacyklí. Každé místo se ukáže jednou, s nejkratší nalezenou cestou;
přímý odkaz má před nepřímým přednost.

Parametry se čtou z aktuální pracovní tabulky po dokončení buňky. Polohy a vazby
pocházejí z pracovní kopie sestavy, kterou P7.34 aktualizuje také při přejmenování.
Duplicitní/prázdný nový název se při přejmenování odmítne. Při neplatném obsahu
načtené tabulky nebo prázdné hodnotě se ukáže nedostupnost přehledu;
nečitelný výraz označí přehled za neúplný. Ověření hodnot a přijetí celé dávky
zůstává stejné jako v P7.32.

Přehled nečte zdrojové soubory ani parametry vnitřních podsestav. Zahrnuje ovšem
polohu celé podsestavy v této úrovni. Ukazuje odkazy ve výrazech, nepředpovídá
přesuny ostatních dílů řešičem vazeb. Prohlížení, přepínání řádků a změna pracovního
výrazu nemění model, výsledek, kameru, zdrojové soubory ani historii. Formát,
geometrické jádro a závislosti se nemění.

## Ověření

`tests/test_assembly_parameter_usage.py` prověřuje všech šest os polohy/otočení,
vzdálenostní vazbu, dlouhé i vícecestné návaznosti, přesné názvy a české znaky,
funkce, cyklus, nečitelný výraz, stejné názvy komponent rozlišené id, nezávislý
kontext podsestav a nulové čtení chybějících zdrojů. Okno ověřuje návaznosti
pracovní tabulky, přepínání výběru, opravu chyby, duplicitní názvy, mazání všech
řádků a zrušení při zachovaném modelu a historii.

Nativní self-test **Použití parametrů sestavy** skutečně vybere řádek myší a ověří
přímý odkaz do parametru i nepřímý do vzdálenostní vazby. Navazující potvrzení dál
ověřuje fyzický zdvih víčka 12,5 mm, sedm splněných vazeb, Zpět/Znovu a kameru.
Scénář běží také ve stažených aplikacích obou systémů. Místní evidence a snímek
jsou v `out/assembly-parameter-usage/`; úplné kontroly jsou v implementačním PR.
