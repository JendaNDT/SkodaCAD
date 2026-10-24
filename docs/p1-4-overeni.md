# P1.4 — implementace a ověření

Autor 24. 10. 2026 schválil [E1–E9, E.1–E.4 a E01–E22](p1-4-navrh-exportu-a-ndt-pri-chybe.md)
slovy „ok, schvaluji“. Implementace běží ve větvi `codex/p1-4-safe-outputs`
nad schváleným návrhem z PR #38 (`c2d0e97`); produkční základ je `main / f5fbe2c`.
Do main se bez dalšího pokynu autora neslučuje.

## Postup

| Krok | Stav |
|---|---|
| E.1 | Společná kontrola historie/tělesa, aktuálnosti session, exportu dílu a řezu. CLI zachovává označenou diagnostiku mezistavu, ale neexportuje a vrací 1. Nových 20 regresí; cílená sada 102 prošla / 12,03 s, Ruff OK. Celá místní sada **1 471 prošlo / 427,75 s**, 0 chyb, selhání a přeskočení. |
| E.2 | Čeká: NDT studie, výpočty, výsledky, přímé NDT příkazy CLI, přenos a zprávy. |
| E.3 | Čeká: okno, diagnostický náhled AI a obnova. |
| E.4 | Čeká: konečná matice, baseline, obě celé CI, balíčky a dostupné nativní zkoušky. |

Výchozí baseline P0 vznikla před změnou zdrojů, zahřátí + 3 opakování;
vstupy a fyzické podpisy zůstávají pro závěrečné srovnání. Formát je 22,
závislosti ani worker protokol se nemění. Odborná NDT-17 se neprohlašuje za hotovou.
