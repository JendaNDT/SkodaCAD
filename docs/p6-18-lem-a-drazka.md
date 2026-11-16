# P6.18 – Lem a drážka při rozříznutí: návrh a provedení

*Datum 15. 11. 2026, navazuje na [P6.17](p6-17-rozriznuti.md) (pokyn „další rozšíření
modelování“, výběr nechán na mně). Víčko krabičky se musí do základny **zasunout**, jinak se po
tisku na ní jen posouvá. Lem na základně a drážka ve víčku to řeší.*

## Rozhodnutí: lem je součást rozříznutí, ne samostatný prvek

První návrh byl prvek, který by lem vedl po **vybrané ploše** (odkaz na plochu + pojistka původu
jako u úkosu). Zamítnul jsem ho: po změně výšky řezu nebo mezery mezi částmi se víčko posune
a odkaz na plochu přestane souhlasit („vyber plochu znovu“), takže by parametrické víčko
nefungovalo. Lem a drážka se proto **odvodí přímo z obrysu řezu** (průřezu stěn rovinou), který
`split` stejně počítá. Žádné odkazy na plochy, žádný výběr ve 3D, při změně `V`, `M`, `W` nebo
`H` se vše přepočítá samo. Formát zůstává **37** (jen rozšíření prvku `split`).

## Jak lem a drážka fungují (L1–L7)

- **L1 Zadání.** U `keep: both` jde přidat `lip_width` (šířka pásu), `lip_height` (výška),
  `lip_side` (`inner` = u dutiny, `outer` = vnější okraj; výchozí `inner`) a `lip_clearance`
  (vůle, výchozí 0,2 mm). Bez `lip_width` žádný lem. Ostatní `lip_*` bez šířky nebo lem bez
  `both` se odmítnou.
- **L2 Lem.** Pás šířky `lip_width` podél okraje řezu na straně `lip_side`, vytažený o `lip_height`
  do prostoru víčka a spojený se základnou. Přidaný objem se ověří: plocha pásu × výška.
- **L3 Drážka.** Tentýž pás o `lip_clearance` širší, vytažený o `lip_height + lip_clearance`
  ode dna víčka a odečtený od víčka.
- **L4 Obrysy.** Pásy vznikají přesným odsazením obrysu dutiny (ostré rohy zůstanou ostré,
  zaoblené zůstanou oblouky). Zaoblená dutina: přírůstek plochy je obvod × šířka + π × šířka².
- **L5 Žádné tiché selhání.** Lem, který je stejně široký jako stěna (i s vůlí), drážka hlubší
  než stěna víčka, řez bez dutiny pro vnitřní lem a neplatné hodnoty se **odmítnou** česky.
  Počet těles se u každé části zachová, objemy se kontrolují.
- **L6 Zapadnutí.** Test přiloží víčko na základnu (mezera 0) a ověří, že se lem a víčko
  **nepřekrývají** (průnik je prázdný) pro vnitřní i vnější lem; kontrola s víčkem zasunutým
  o 1 mm dolů ukáže, že měření průniku něco odhalí.
- **L7 Okno.** Pole „Šířka lemu“, „Výška lemu“, „Strana lemu“ a „Vůle drážky“ v kartě
  *Rozříznutí rovinou* (viditelná jen při „obě části“).

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_split.py` (52) | lem a drážka podle vzorce (vnitřní, vnější), zaoblená dutina podle obvodu × šířka + π × šířka², lem následuje výšku řezu, zapadnutí bez průniku, odmítnutí (celá stěna, stěna s vůlí, příliš hluboká drážka, bez dutiny, špatné hodnoty), klíče a parametry, výchozí vůle |
| ukázka [`rozriznuta_krabicka.json`](../examples/rozriznuta_krabicka.json) | základna 18 693,78 mm³ (dno, stěny, lem 881,28), víčko 13 587,21 mm³ (drážka 1 100,29) |
| nativní self-test | „✓ Rozříznutí s lemem“ |

Snímek okna: [základna s lemem a víčko nad ní](p6-17-snimky/rozriznuta-krabicka.png).

## Meze

- Lem vede po **celém** obrysu řezu (všechny stěny). Přerušovaný lem, zámky (klip) a zaoblení
  hran lemu nejsou součástí této verze.
- Lem a drážka se počítají jen při `both`; pro jednu část se nepoužívají.
- Vůle 0,2 mm je běžná pro FDM, ne záruka lícování – výsledek na tiskárně je třeba ověřit.
- Neověřeno na vlastním dílu autora ani vytištěno.
