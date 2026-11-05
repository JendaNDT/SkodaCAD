# P8.5 — uzavření ověřeného vydání

[PR #119](https://github.com/JendaNDT/SkodaCAD/pull/119) byl sloučen squash commitem
[`e7f5e6d7bc14b3d9f7ddaedf90fe87bd79920a1d`](https://github.com/JendaNDT/SkodaCAD/commit/e7f5e6d7bc14b3d9f7ddaedf90fe87bd79920a1d).
Strom je `31eac12d45fb71e30b5ddef495ccc74e529bd307`, jediný rodič
`60666433d496c9272e8935240dc7c41e8a242876`. Všech 150 měřených zdrojů
(LF i CRLF) a tři generované vstupy odpovídají místnímu snapshotu `b9df458`.
Ten není publikovaným předkem PR: pluginový commit má konsolidovaného rodiče
a jiná metadata. Čísla starších kandidátů nejsou vydávána za výsledky nového.

## Dokončené kontroly

Před sloučením prošlo všech osm požadovaných workflow PR a jejich podrobné
důkazy. Po sloučení prošlo všech pět nových push workflow nad skutečným `e7f5e6d`:

| Kontrola MAIN | Běh | Ověřený rozsah |
|---|---|---|
| Windows aplikace | [41916027256](https://github.com/JendaNDT/SkodaCAD/actions/runs/41916027256) | 2982 úspěšných + 2 přesně vymezené Mac RSS skips; Ruff, P0, skutečné PE/DLL a stažený self-test |
| macOS aplikace | [41916027494](https://github.com/JendaNDT/SkodaCAD/actions/runs/41916027494) | 2984 úspěšných bez skips; Ruff, P0, arm64, codesign a stažený self-test |
| P8.5 Windows | [41916026888](https://github.com/JendaNDT/SkodaCAD/actions/runs/41916026888) | všech 23 mezí; 2 zahřívací + 20 měřených cyklů, 180 úplných bodů, fyzika, Qt, RSS a běžné zavření |
| P8.3 oba OS | [41916027064](https://github.com/JendaNDT/SkodaCAD/actions/runs/41916027064) | původní striktní porovnání, řízený historický základ, zdroje, vstupy, geometrie a prohlédnuté snímky |
| P8.4 oba OS | [41916027796](https://github.com/JendaNDT/SkodaCAD/actions/runs/41916027796) | 2 + 20 cyklů, 180 bodů, původní runtime validace, PID/RSS a prohlédnuté snímky |

Self-testy skutečně stažených aplikací ověřily pět parametrických scénářů
včetně celého 3D náhledu a čtyři případy nativního životního cyklu.
P6 shell/guide a čtyři STEP úlohy prošly nad aktuálním PR. Jejich workflow nemají
push trigger; nebyly znovu ručně spouštěny ani označeny za nové MAIN běhy.

## Skutečné veřejné balíčky

Oba soubory byly staženy, ověřeny proti API SHA-256 a porovnány s testovanou aplikací.
Oba tagy byly v okamžiku ověření **lightweight**, přímo na `e7f5e6d`, nikoliv
annotated tagy. Odkazy „nejnovejsi“ jsou pohyblivé; následující identity patří
tomuto ověřenému vydání, nikoli libovolnému budoucímu stažení.

| OS | Release / asset ID | Velikost ZIP | SHA-256 |
|---|---|---:|---|
| Windows | 434501153 / 711083061 | 187403389 B | `efd5657b259d7c71ddd254f190e0c07b7e6d68b160a54e5f96f5dca35d1a8d80` |
| macOS | 434496541 / 711069653 | 163735718 B | `58de5b942a4af925c5882f8ca25a8d71387a007b5a8b2a3c26da38d0095e8b8e` |

Windows: všech 6917 rozbalených souborů přesně odpovídalo testované MAIN aplikaci.
Mac ZIP odpovídal bajt po bajtu testovanému vnitřnímu ZIPu.
[Windows ZIP](https://github.com/JendaNDT/SkodaCAD/releases/download/nejnovejsi/SkodaCAD-windows.zip),
[macOS ZIP](https://github.com/JendaNDT/SkodaCAD/releases/download/nejnovejsi-mac/SkodaCAD-macos.zip).
Úplné raw, API odpovědi, logy a ZIPy jsou zachované v ignorovaném
`out/p8-5-budgets/`; závěrečný souhrn je `lifecycle-final-verified-release.json`.

## Rozsah a navazující rozhodnutí

Hostovaný Mac **výkon** zůstává vynechaný pokynem autora; správnost, sestavení,
stažený self-test a P8.3/P8.4 obou OS prošly. Místní M4 přejímka má 1130
průběžných RSS odběrů, z nichž tři neobsahují celé RSS workerů; všech 180
kontrolních bodů je úplných. MAIN P8.4 Mac má jeden neúplný průběžný odběr
z 2458 a všech 180 bodů úplných. Příčina chybějících odběrů se nedovozuje.
Součet vzorkovaného RSS není unikátní RAM ani GPU paměť. Dvacet cyklů
neprokazuje absenci úniků, celodenní stabilitu ani reprezentativní NDT zátěž.

Po vydání autor doporučenou automatickou přejímku na reprezentativní NDT úloze
přeskočil slovy **„tu přejímku přeskočíme“**. Zůstává neprovedená a neblokuje
další vývoj; odborná validace NDT-17 tím není hotová. Monitor vydání byl po
ověření odstraněn, sledování P8.5 skončilo. Další vybraná oblast je
**Ovládání a pracovní postupy** (5. 11. 2026).
