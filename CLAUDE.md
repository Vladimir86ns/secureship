## Rad sa .ai fajlovima (OBAVEZNO)

Izvor istine je specifikacija zadatka: docs/SecureShip-5Week-Program.md.
Ako se plan ili prompt sudara sa specifikacijom, specifikacija ima prednost: stani i javi.

Folder .ai/ (u .gitignore, nikad se ne komituje):
- .ai/CLAUDE_PLAN.md — trenutni plan (samo jedan plan u fajlu)
- .ai/CLAUDE_SUMMARY.md — rezime poslednje implementacije
Prazan .ai fajl je normalno stanje.

Nova sesija PRVO pročita CLAUDE.md, pa oba .ai fajla.

### Zadatak "PLAN"
- NE menjaj kod.
- PRVO isprazni .ai/CLAUDE_PLAN.md, pa upiši SAMO novi plan. SUMMARY ne diraj.
- Plan sadrži: koje stavke iz sekcije 8 i koje sekcije/Epic-e specifikacije pokriva,
  audit postojećeg stanja (fajl:linija), mane i bagove, predlog, šemu / migracije,
  korake (mali, svaki može zasebno da se pregleda), testove, rizike,
  i na kraju OTVORENA PITANJA za vlasnika.
- Na kraju u terminalu samo jedna rečenica: "PLAN <naziv> spreman".

### Zadatak "kreni" (implementacija)
- CLAUDE_PLAN.md ne diraj, osim kad vlasnik kaže da dopišeš §0 sa njegovim odlukama
  (one imaju prednost nad planom).
- PRVO isprazni .ai/CLAUDE_SUMMARY.md.
- Radi korak po korak. Posle SVAKOG koraka provere: pytest (backend), build (frontend),
  i npx orval ako se promenila backend šema. Nijedan test ne zove pravu Ollamu
  (lažni klijent). Ako bilo šta padne i ne možeš da popraviš — STANI i javi.
- Ne radi git commit ni push; to radi vlasnik. Verzija u package.json ostaje 1.0.0.
- Na kraju upiši SUMMARY: šta je urađeno po koraku, menjani fajlovi, provere i rezultat,
  odstupanja od plana i zašto, kako se pokreće lokalno, šta vlasnik ručno testira,
  i predlog commit poruke.

### Opšta pravila
- Nikad ne menjaj kod bez izričitog "kreni".
- U terminalu kratko; detalji su u SUMMARY.
