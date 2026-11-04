# P8.3 — obnova vzhledu stromu sestavy

Autor 3. 11. 2026 schválil navazující doporučení odpovědí „ok, udělej to“.
Výchozí vydané P8.2 je `93843f4790ef13b518b10fea26e3e794ff0d79bf`.
Tato dávka mění jedinou produkční metodu, `AssemblyWindow._refresh_tree_visibility`.
Nemění geometrii, výpočty objemu, formát, závislosti, měřiče P8.1/P8.2 ani ovládání.

## Zásah a platnost mezivýsledků

Dříve každý řádek stromu dvakrát sestavoval množinu rodičů a procházel všechny
stavy sestavy: pro kurzívu průhledných větví a pro rozsah procent v popisku.
Nově se listy projdou jednou a předají svým předkům trojici: alespoň jeden průhledný
list, nejnižší a nejvyšší procento. Při omezené hloubce sestavy je tato část
úměrná počtu listů krát hloubce, místo počtu řádků krát počtu stavů.

Slovník existuje pouze uvnitř jediného volání. Po návratu se zahodí; žádná trvalá
cache, invalidace ani nový stav okna nevzniká. Výběr listů používá přesně dosavadní
pravidlo `_branch_values`: stav bez potomků je list, včetně prázdné nebo chybějící
podsestavy. Řádky bez odpovídajících stavů mají dosavadní vlastní hodnotu.
Ruční viditelnost, izolace, skutečný počet viditelných dílů, zděděná průhlednost
a obnovení původního blokování signálů zůstávají zachované.

## Místní srovnání na Apple M4

Nezměněný `tests/profile_p8.py --cases gui-assembly --repeats 3`, Python 3.12.14,
stejné prostředí a vstupy, vždy čerstvý proces pro control i spans. Každá operace
má jedno nezapočítané zahřátí a tři vzorky. Nativní okna před i po byla prohlédnuta.
Oba režimy zachovaly 800 instancí, 0 vazeb, objem 800000 mm³, výběr `c799`
a návrat z náhledu bez změny modelu.

| Operace / oblast | Před | Po |
|---|---:|---:|
| Celé otevření 800 kopií — control, medián | 363,68 ms | 305,54 ms |
| Výběr poslední kopie — control, medián | 41,37 ms | 39,77 ms |
| Otevření a návrat z náhledu — control, medián | 750,21 ms | 772,51 ms |
| Obnova vzhledu stromu při otevření — spans, průměr self | 89,92 ms | 21,61 ms |

V tomto běhu klesla obnova stromu o 68,30 ms (76 %) a celé otevření o 58,15 ms
(16 %). Náhled naopak vyšel o 22,30 ms pomalejší; jeho zrychlení netvrdíme.
Pevné pořadí před/potom a tři vzorky nejsou statistická studie ani záruka rychlosti
na jiném zařízení. GUI zahrnuje Qt události a čekání; není to FPS ani latence kliknutí.
Self je čas na hodinách včetně nativní práce, nikoli čistý CPU/GPU čas.

Surové, neupravované protokoly:
[před](baselines/p8-3-macos-arm64-before.json) a
[po](baselines/p8-3-macos-arm64-after.json). Oba uvádějí výchozí commit `93843f4`:
měření „po“ proběhlo nad tehdy necommitnutou změnou, jejíž skutečnou identitu dokládá
SHA-256 souboru `assembly_window.py` `464c05ca2fa99b4d89b1221c786aec63b67d6cb808bdc0a908409db2b586e8ac`
oproti původnímu `68f00b512414c5f6c66da1af8386df7daad456d191f9acfca5695557d428f22d`.
Všechny ostatní otisky zdrojů, ukázek a tří měřičů se přesně shodují.
Původní baseline P8.1/P8.2 se nepřepisuje.

## Regrese a kontrola důkazů

Tři nové GUI regrese porovnávají všechny popisky a kurzívu s původním nezměněným
pravidlem `_branch_values`. Ověřují jediné čtení procenta pro každý plochý list,
beze změny modelu/výsledku/historie/geometrie, smíšená procenta, skrytí/izolaci,
prázdné/chybějící vnořené větve a jejich nový výsledek po načtení, reset i obnovení
blokování signálů při výjimce. Dotčený celý GUI modul, fyzikální reference P8.1,
účetnictví P8.2 a Qt cleanup: **129 testů prošlo za 32,40 s**, normální konec.
Sedm zkoušek srovnávače přijímá platný záznam a odmítá jiné vstupy, neúplný běh,
změněný měřič, chybné účetnictví, počet volání nebo geometrii.

`tests/compare_p83.py` kontroluje shodné prostředí, úplné otisky, právě jeden
povolený změněný zdroj, nativní okna, výsledky, zahřátí/vzorky a rozdělení self
intervalů s tolerancí měřiče. Inclusive intervaly se nesčítají. Nevyžaduje předem
vymyšlený rychlostní práh a zveřejňuje i zpomalení ostatních operací.

Původní workflow `p83-tree-appearance.yml` porovnával na každém OS na témže runneru
pevný základ `93843f4` a tehdejší sestavení v oddělených procesech. Při změně dalších
produkčních souborů v P8.5 srovnávač správně odmítl tento již nesrovnatelný pár.
Nešlo o překročení rychlostního prahu; kontrola vyžaduje jediný změněný zdroj.

Navazující workflow proto vytváří kontrolovanou referenci ze skutečného aktuálního
commitu. Jen metodu `AssemblyWindow._refresh_tree_visibility` nahradí její původní
verzí z pevného `93843f4`; všechny ostatní současné metody, produkční soubory,
vstupy a měřiče ponechá totožné. Reference dostane skutečný místní Git commit
s aktuálním kandidátem jako jediným rodičem. Kontrola rozdílu vyžaduje právě
`assembly_window.py` a původní nezměněný srovnávač dále kontroluje všechny otisky.
Výsledek tak izoluje obnovu vzhledu stromu i po pozdějších opravách P8.4/P8.5.

`p83-baseline-context.json` uchovává oba commity, strom a rodiče reference,
původ historické metody a otisky obou metod. Surový report „před“ uvádí nový
skutečný commit reference, nikoli identitu starého vydání. `PYTHONPATH` vybírá
příslušný zdroj; na Macu se sestaví přístupnost obou checkoutů. Artefakt uchovává
kontext, oba neupravované JSONy, srovnání, procesní protokoly a nativní snímky.
Příprava reference prošla místním ověřením Git stromu, rodiče a přesné shody všeho
mimo uvedenou metodu s LF i CRLF. Nové úplné nativní porovnání obou OS ještě čeká
na CI; historické výsledky a baselines výše se nepřepisují.

Požadavkem původní dávky byly úplné kontroly Windows/macOS (**2872 případů**),
build, pět sestavových scénářů self-testu stažené aplikace, STEP a nové srovnání
před/po obou OS. Potom je nutné stejně ověřit skutečné vydání z main a nové ZIPy.
P8.4 dlouhý provoz a P8.5 autorské přijetí tato dávka neprohlašuje za provedené.
