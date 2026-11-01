# P7.9 – podsestava s díly v jiné složce

Datum: **1. 11. 2026**. Navazuje na [P7.8](p7-8-sestavy-dokumenty-macos.md).

## Nález a oprava

P7.8 navrhovalo společnou složku podle přímých odkazů hlavní sestavy.
Hlavní sestava ve `sestavy/` mohla odkazovat na `moduly/podsestava.json`,
zatímco podsestava používala `../../dily/deska.json`. Výběr `sestavy/`
kontrola přijala, přestože složka `dily/` nebyla pokrytá. Regresní test
`test_subassembly_requires_its_external_part_folder_before_open` na původním
kódu selhal: otevření smělo pokračovat bez potřebného přístupu.

`gui/assembly_access.py` nyní před sestavením prochází i vnořené odkazy.
Před prvním systémovým výběrem čte jen uživatelem vybraný JSON. Potom vypisuje
složky a čte zdroje pouze uvnitř vybraného projektu. Vnější cíl vyvolá nový
systémový výběr širší složky dříve, než se vypíše jeho adresář nebo otevře recept.
Kontrola se provádí i u dříve vybraného projektu, takže změněný odkaz podsestavy
nevyužije starý souhlas pro menší složku.

Zachováno je hledání s rozdílnou velikostí písmen a ověření skutečných cílů
symbolických odkazů. Sdílený zdroj se prohlíží jednou, cykly nevedou k nekonečné
kontrole; hlídá se počet navštívených komponent a hloubka podle mezí sestav.
Vadné či chybějící recepty dále vyhodnocuje běžné sestavení. Kontrola přístupu
nemodeluje geometrii, nemění recept, polohy ani formát souboru.

Zrušení následného výběru nebo opětovná volba příliš úzké složky zachová původní
okno a model. Větší složka se pamatuje pouze v procesu. Nemění se oprávnění
v Nastavení systému ani mechanismus otevírání ve Windows/Linuxu.

## Referenční projekt a očekávaný výsledek

Projekt pro místní zkoušku je v `out/p7-subassembly-documents/projekt/`:

- `sestavy/hlavni.json`: dvě kopie téhož modulu, jedna posunutá a otočená o 90°;
- `sestavy/moduly/podsestava.json`: odkazy `../../dily/…`;
- `dily/deska.json`: kvádr 30 × 20 × 10 mm;
- `dily/valecek.json`: válec Ø10 × 10 mm, oddělený od kvádru;
- `kopie/`: cílová složka pro Uložit jako v rámci celého projektu.

Očekává se **6 komponent ve stromu, 4 platné díly ve 3D**, objem
**2 × (30 × 20 × 10 + π × 5² × 10) = 12000 + 500π = 13570,796327 mm³**
a obálka **(0, 0, 0) až (100, 100, 30) mm**. Uložení hlavní sestavy do
`kopie/` musí přepočítat její relativní odkazy a ponechat soubory podsestavy
i dílů bajtově stejné. Opětovné otevření musí najít tytéž zdroje a geometrii.

Regrese pokrývají obě okna, zrušení, rozšíření i zapamatovaný úzký projekt,
nepovolené čtení před následným panelem, velikost písmen, symlink, sdílené
podsestavy, cyklus, meze a vadné zdroje. Výsledky skutečného místního průchodu,
snímek a meze automatizace se zaznamenávají samostatně v PR a místních artefaktech.
