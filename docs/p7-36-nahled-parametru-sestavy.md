# P7.36 — náhled změn parametrů sestavy před potvrzením

V **Parametry sestavy…** uprav hodnoty, výrazy nebo názvy a stiskni **Náhled změn**.
Otevře se vlastní 3D okno s výsledkem řešiče vazeb a růžově zvýrazněnými komponentami,
kterým se změnila poloha nebo otočení. Například `polovina = 6,25`, `vule = polovina*2`
zvedne víčko o 12,5 mm; tabulka ukáže Z z 32 na 44,5 mm a stav sedmi vazeb.

- **Zobrazit původní sestavu pro porovnání** přepíná dvě spočítaná zobrazení bez
  přizpůsobování kamery při každém přepnutí. Náhled můžeš otáčet a přibližovat obvyklým
  ovládáním 3D. Dvojklik přizpůsobí právě zobrazenou sestavu oknu.
- **Zpět k parametrům** (také Esc nebo zavření okna náhledu) ponechá rozepsané hodnoty
  i plán přejmenování v editoru. Další Náhled změn vypočítá novou variantu.
- **Použít změny** v náhledu potvrdí celou dávku a zavře obě pracovní okna; je to
  jediný krok Zpět. Stejná tlačítka Použít/Zrušit v editoru fungují dál i bez náhledu.
- **Zrušit** v editoru zahodí pracovní tabulku. Náhled nikdy nekreslí do hlavního
  zobrazení, takže není třeba původní model ani kameru zpětně opravovat.

## Co se ověřuje

Původní sestava musí být úplná a mít všechny zdroje načtené. Náhled používá stejnou
kontrolu výrazů, přejmenování, poloh, otočení a vzdálenostních vazeb jako potvrzení.
Spor vazeb, neznámý parametr, neplatné použití nebo neúplný výsledek se odmítne
s důvodem; původní model zůstane beze změny. Při syntakticky chybném výrazu jsou
tlačítka Náhled i Použít vypnutá. Chybný návrh se nevydává za platný 3D náhled.

Tabulka porovnává vyhodnocené posuny a otočení komponent v této úrovni sestavy
po vyřešení vazeb, ne samotný text výrazu. Přejmenování bez změny fyzické polohy
proto nevytváří falešný posun. Podsestavy se počítají ve svém kontextu jako dosud;
změna polohy nadřazené podsestavy je změnou této komponenty.

Vlastní 3D zobrazení respektuje původní skrytí, izolaci a míru průhlednosti. Tabulka
uvádí všechny změněné komponenty této úrovně, i když je některá skrytá. Přepínač
původního stavu ani pohyb kamery náhledu nemění výběr, kameru nebo vzhled hlavního
okna. Kolize a vůle se tímto náhledem samostatně neanalyzují; stav vazeb není kontrola
průniků. Parametry zdrojových dílů se neupravují, nové závislosti ani formát nejsou.

## Oddělení a zastarání

`AssemblySession.preview_parameters` pracuje na hluboké kopii sestavy a vlastní
session. `Cache.fork` sdílí hotové zdrojové tvary, ale odděluje mapy a frontu čekání;
náhled proto nemaže frontu práce hlavního okna. Úprava v náhledu nemění původní
model, výsledek, Zpět/Znovu, dirty, skupinu úprav, zprávu, audit ani zdrojové soubory.
Výpočet je ručně vyžádaný a synchronní stejně jako dnešní potvrzení parametrů;
automatický živý přepočet při každém znaku není součástí této dávky.

Před potvrzením se ověří identita a recept původní sestavy, její výsledek a cesta
i SHA-256 bajtů zdrojů včetně podsestav. Potom se znovu provedou stejné kontroly
a výpočet; před přijetím se znovu ověří zdroje a shoda řešeného receptu s náhledem.
Starý náhled se nikdy nepoužije přes novější model nebo změněný soubor. Zastaralost
ponechá okno otevřené s vysvětlením a vypne Použít; návrat k editoru zachová pracovní
hodnoty. Pokud se změnil i otevřený model, jeho přepsání blokuje také přímé Použít
z původního editoru. Nezměněná dávka nevytváří krok Zpět.

## Ověření

`tests/test_assembly_parameter_preview.py` měří skutečný zdvih víčka a řešení vazeb,
závislý výraz a přejmenování, opakované náhledy, jediný Zpět/Znovu, nulovou změnu
hlavní historie, cache a zdrojů, nesplnitelné vazby a neplatné hodnoty. Ověřuje také
zastarání po úpravě modelu, přepočtu, změně cesty či souboru, změnu zdroje během
potvrzování a zachování novější práce po návratu ze zastaralého náhledu. Skutečné
kliknutí v okně testuje porovnání, návrat, potvrzení, převzetí rozepsané buňky,
izolaci, skrytí a průhlednost.

Nativní scénář **Náhled parametrů sestavy** otevírá skutečný editor i vlastní OCCT
prohlížeč. Ověřuje víčko +12,5 mm, sedm vazeb, přejmenování, porovnání původní/nové,
návrat i Zrušit bez změny hlavního modelu/výsledku/historie/kamery/zdrojů, potvrzení
jedním Zpět/Znovu a odmítnutí chybného výrazu i zastaralého náhledu. Běží také ve
stažených aplikacích Windows a macOS. Evidence a snímek jsou v
`out/assembly-parameter-preview/`.
