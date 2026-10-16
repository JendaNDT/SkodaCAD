# Návrh: první verze ŠkodaCAD pro macOS (Apple Silicon)

> Provedení závazného požadavku `05-podpora-macos.md`. Cíl: MacBook Air M4 (16 GB), stažení
> z GitHub Releases a spuštění bez instalace Pythonu. **Dokud to neověříš na skutečném Macu,
> kompatibilita není zajištěná.**

Stav: návrh 16. 10. 2026 · **rozhodnuto:** nejdřív sladit UT, pak Mac; balíček **ZIP se
`SkodaCAD.app`**; nastavení a log v **`~/SkodaCAD`** jako ve Windows · **kroky 1–3 hotové**,
čeká se na ruční test na MacBooku.

## 0. Výsledek na Macu GitHubu (16. 10. 2026, `macos-15`, Apple Silicon)

- Instalace jen z hotových kol, ruff a všech 658 testů prošlo; `SkodaCAD.app` se sestavila,
  podepsala „ad-hoc“ a z rozbaleného ZIPu prošel celý self-test (**VÝSLEDEK: OK**): 14 ukázek
  a 8 referenčních dílů NDT se stejnými objemy jako ve Windows, exporty, kreslení všech značek,
  výběr kliknutím, měření, mapa tloušťky (13 490 bodů za 1,5 s), řez, skicář (slvs), AI bez
  sítě, NDT studie i sonda, přepočet na pozadí v pomocném procesu (5,2 s i se startem).
- První běh: virtuál bez grafické karty nevytvořil OpenGL („NSOpenGLContext creation failed“)
  a při zavírání okna proces spadl. Oprava: na Macu záložní **softwarové OpenGL** (Apple
  Software Renderer 2.1) a nepovedené objekty OCCT se neruší dřív než okno – druhý běh prošel.
- Na virtuálu je obrazovka bez Retiny (poměr myši 1,00) – **Retina, trackpad a skutečná
  grafika se ověří až na MacBooku.**

## 1. Audit knihoven (ověřeno 16. 10. 2026 na PyPI)

| Knihovna (zamčená verze) | macOS arm64 |
|---|---|
| jádro OCCT – `cadquery-ocp-novtk` 8.0.1.1.0 | ✓ kolo `cp313 macosx_11_0_arm64`, obsahuje `OCP.Cocoa` (okno pro Mac) |
| build123d 0.13.0, anthropic 1.15.0 | ✓ čistý Python |
| PySide6 6.11.2 | ✓ `universal2`, vyžaduje **macOS 13+** (MacBook Air M4 má novější) |
| slvs 3.2 (řešič vazeb) | ✓ `cp313 macosx_11_0_arm64` |
| PyInstaller 6.22.3 | ✓ `universal2` |

Celá sada 82 balíčků (`.[gui,build]`) jde pro macOS arm64 nainstalovat jen z hotových kol
(`uv pip compile … --python-platform aarch64-apple-darwin --only-binary :all:` a zkušební
instalace) → **žádná verze se nemění**.

## 2. Co se změní (Windows a Linux zůstanou, jak jsou)

| Oblast | Dnes (Windows) | macOS |
|---|---|---|
| 3D okno | `WNT_Window` z HWND (PyCapsule) | `Cocoa_Window` z NSView, které vrací Qt `winId()` – stejně jako PyCapsule |
| Klik myší | souřadnice × `devicePixelRatioF` | poměr **skutečné velikosti okna OCCT** k velikosti v Qt – sedí pro 125–150 % ve Windows i pro Retina 2×, ať OCCT na Macu počítá v bodech, nebo v pixelech |
| Posun pohledu | prostřední/pravé tlačítko | navíc **Shift + tažení** (trackpad nemá prostřední tlačítko); výběr dalších ploch Cmd+klik (Qt bere Cmd jako Ctrl) |
| Balíček | složka `SkodaCAD` s `SkodaCAD.exe`, ZIP | `SkodaCAD.app` (PyInstaller, podpis „ad-hoc“), ZIP přes `ditto` (zachová práva a odkazy uvnitř .app) |
| Sestavení | `windows.yml` | **nový samostatný** `macos.yml` na `macos-15` (Apple Silicon): ruff, pytest, .app, self-test **staženého** balíčku, vydání `nejnovejsi-mac` jako předběžné – odkaz pro Windows (`releases/latest`) se nezmění |
| Data a log | `~/SkodaCAD` | `~/SkodaCAD` (rozhodnuto) |
| Texty | „SkodaCAD\nastaveni.json“ | cesty podle systému |

Přepočet na pozadí už používá `spawn` (výchozí i na Macu) a `freeze_support()` – ověří ho
self-test v zabaleném .app, včetně zastavení.

## 3. Rizika a nejistoty

- **3D na sestavovacím Macu GitHubu** – je to virtuál bez grafické karty; nevím, jestli tam
  OpenGL z OCCT nakreslí. Když ne, self-test to napíše a 3D se ověří až na tvém MacBooku.
- Qt 6 má na Macu okna „s vrstvou“ (layer-backed NSView), OCCT do nich kreslí přes
  `NSOpenGLContext` – může být potřeba úprava, kterou ukáže až první běh.
- Apple OpenGL od roku 2018 jen udržuje (neodstraňuje) – OCCT na něm na Macu stojí.
- **Gatekeeper:** aplikace není podepsaná vývojářským certifikátem ani notarizovaná. Od macOS 15
  už nefunguje „pravý klik → Otevřít“; při prvním spuštění *Nastavení systému → Soukromí
  a zabezpečení → Přesto otevřít*. Záloha v Terminálu: `xattr -dr com.apple.quarantine
  /Applications/SkodaCAD.app`. Podepsání a notarizace (placený účet Apple Developer) až při
  rozhodnutí o distribuci.
- **AI a data:** model odchází společnosti Anthropic jen po tvém dotazu v panelu AI a jen
  s vloženým klíčem. Bez klíče (např. na prezentaci) nic neodchází – v README to bude výslovně.

## 4. Postup (malé kroky, po každém ruff + pytest)

1. Prohlížeč: větev `Cocoa_Window`, poměr pro klik myší, Shift + tažení, texty cest + testy.
2. Balení `.app` (`packaging/skodacad.spec`) a `macos.yml` → první běh na GitHubu, opravy podle
   logu (self-test zapisuje ovladač OpenGL a zásobník při pádu).
3. README: stažení a první spuštění na Macu, známá omezení.
4. **Tvůj ruční test na MacBooku** (seznam níže); výsledky a omezení zapíšu sem a do CLAUDE.md.

## 5. Ruční test na MacBooku (podmínky dokončení z `05-podpora-macos.md`)

- [ ] stáhnout ZIP, rozbalit, přetáhnout do Aplikací, povolit v Nastavení a spustit
- [ ] otevřít ukázku (příruba), otočit, přiblížit, posunout (Shift + tažení)
- [ ] kliknout na plochu – vybere se ta pod kurzorem (Retina)
- [ ] změnit parametr, přepočet, Zpět
- [ ] měření (tloušťka stěny), export STEP
- [ ] mapa tloušťky (trubka), řez modelem
- [ ] NDT: Deska se žebrem → panel NDT → Přiložit sondu sem
- [ ] dlouhý přepočet a Zastavit
- [ ] stejný model otevřený na Windows i Macu dává stejný objem
