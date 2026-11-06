# P7.47 – srozumitelná hláška u *Ukázat jho* (MT)

Na pokyn autora z 6. 11. 2026 („ok, uděláme tu srozumitelnější hlášku u Ukázat jho
v MT“). Navazuje na zkoušku vydání etapy 12 z 19. 10. 2026
([návrh etapy 12](ndt/21-navrh-etapa-12.md)): autor u kraje desky v pohledu
*pole 90°* klikl na místo, stiskl *Ukázat jho* a nic se nenakreslilo. Panel
ukázal jen důvod pro jho se středem v místě, bez souvislosti s mapou.

## Co se změnilo

- Když místo **zvolený směr pole nemá** (v mapě toho směru není zelené), *Ukázat
  jho* už jho nehledá a do panelu napíše například:

  > Pole 90°: toto místo ho nemá – pól nemá kam dosednout – ve vzdálenosti 50 mm
  > od místa už není povrch (okraj). … Místo má platné směry pole 0°, 22,5°, 45°,
  > 112,5°, 135°, 157,5°. Přepni zobrazení na „celkem“ (nebo na jeden z platných
  > směrů) a stiskni Ukázat jho znovu.

  Důvod je **stejná věta, jakou mapa uvádí u místa** (`MtSample.failures`), takže
  hláška a mapa si nemohou odporovat. Směry jsou ve stejném rámu místa jako
  přepínač mapy.
- Když místo **nemá žádný platný směr**, hláška to řekne a odkáže na důvody u místa.
- V pohledu *celkem* se jho ukáže pro první platný směr; když místo má jen nejisté
  směry, použije se první nejistý (dřív se v takovém případě zkoušelo 0°).
- Jinak beze změny: platný směr nakreslí jho jako dosud. Vše je jen pohled –
  model, studie ani historie se nemění. Hláška zmizí s novým jhem, *Skrýt jho*
  i se změnou dílu.

## Jak to funguje

- `ndt/mt.py` – `MtMap.yoke_direction(index, view)` vrátí směr pro hledání jha,
  nebo `(None, věta)`. Bez okna, testovatelné na umělých datech.
- `ModelSession.ndt_mt_yoke_at` při `None` jho nehledá, zruší zobrazené jho
  a větu drží v `ndt_yoke_note` (platí jen pro tutéž mapu a studii jako jho).
- Panel NDT ukáže `ndt_yoke_note` v řádku jha místo nápovědy.

## Ověření

- `tests/test_ndt_mt.py`: čtyři testy jádra (platný směr, chybějící směr s výčtem
  platných a radou, místo bez směru, nejisté směry) a kontrola `self_check`.
- `tests/test_ndt_mt_session.py`: skutečná mapa desky – místo na horní ploše bez
  pole 90° dá větu a žádné jho, *celkem* jho ukáže a větu smaže, *Skrýt jho*
  i změna parametru větu zruší, model beze změny.
- `tests/test_gui.py::test_mt_panel_settings_map_views_pick_yoke_and_export`:
  klik na takové místo, přepínač *pole 90°*, *Ukázat jho* → věta v panelu, žádné jho
  ve 3D, bez chyby; *celkem* → jho se nakreslí.
- Self-test balíčku: kontrola MT („MT jho: OK … Ukázat jho vysvětlí chybějící
  směr“) ověří větu i ve stažených balíčcích Windows a macOS.
- Úplná sada testů v cloudu (měněno `session.py`).
